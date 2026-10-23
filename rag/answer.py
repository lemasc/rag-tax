"""Answer generation: retrieve chunks, build a Thai prompt with numbered sources, ask the generator.

The prompt asks for answers from the sources only, with [n] citations; to say so when the sources do not cover the
question; to ask back when the question lacks facts the answer depends on; to correct a wrong premise; and to say
which tax year or document year a figure comes from (the corpus mixes 2560-2568 material, see rag-baseline.md).
Change PROMPT_VERSION whenever SYSTEM or the context format changes: it is part of every run's record.

No retrieval (`--mode none`, E3's lower bound): SYSTEM_NO_SOURCES keeps SYSTEM's rules except the sources-only and
citation ones, and the question goes without sources; NO_SOURCES_VERSION is its own prompt version. Any [n] in such
an answer is recorded as a bad citation.

Multi-turn sets: the retrieval query is the earlier questions of the set plus the current one; the generator sees
the earlier turns as a conversation (question and its own answer) and gets sources only for the current turn.

Output: rag/out/runs/<run_id>/answers.jsonl (one record per question) and config.json
Run   : uv run python -m rag.answer --subset dev --gen gpt-mini [--mode hybrid] [-k 5] [--max-per-doc 2]
        uv run python -m rag.answer --ids Q0045,Q0343 --gen gpt-mini
        uv run python -m rag.answer --subset ablation --gen typhoon --mode dense   # E3 baseline
        uv run python -m rag.answer --subset ablation --gen typhoon --mode none    # E3 no retrieval
"""

import argparse
import hashlib
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rag import llm
from rag.chunk import OUT
from rag.index import DEFAULT_MODEL
from rag.questions import Question, ablation, dev, history, load
from rag.retrieve import MODES

PROMPT_VERSION = "v1"
NO_SOURCES_VERSION = "n1"
NONE = "none"  # the mode that retrieves nothing
RUNS = OUT / "runs"
WORKERS = 4

SYSTEM = """คุณเป็นผู้ช่วยตอบคำถามเรื่องภาษีเงินได้บุคคลธรรมดาของไทย โดยอาศัยเอกสารอ้างอิงที่ให้มาเท่านั้น

กติกา
1. ใช้เฉพาะข้อมูลจากเอกสารอ้างอิง ห้ามใช้ความรู้อื่น อ้างอิงด้วยหมายเลขเอกสารในวงเล็บเหลี่ยมท้ายประโยคที่ใช้ข้อมูลนั้น เช่น [1] หรือ [2][3]
2. ถ้าเอกสารอ้างอิงไม่มีข้อมูลพอจะตอบ ให้บอกตรง ๆ ว่าไม่พบข้อมูลนี้ในเอกสารอ้างอิง อย่าเดา
3. ถ้าคำถามขาดข้อมูลที่จำเป็นต่อคำตอบ (เช่น รายได้ทั้งปี ประเภทเงินได้ สถานะสมรส) ให้ถามกลับว่าต้องการข้อมูลใด และอธิบายหลักเกณฑ์ที่เกี่ยวข้องจากเอกสารเท่าที่ทำได้
4. ถ้าคำถามตั้งอยู่บนความเข้าใจผิด ให้ชี้แจงให้ถูกต้องตามเอกสาร
5. เมื่อให้ตัวเลข วงเงิน หรืออัตรา ให้บอกปีภาษีหรือปีของเอกสารที่มาด้วย ถ้าเอกสารต่างปีให้ตัวเลขไม่ตรงกัน ให้บอกทั้งสองค่าและปีของแต่ละค่า
6. ตอบเป็นภาษาไทย กระชับ ตรงประเด็น"""

SYSTEM_NO_SOURCES = """คุณเป็นผู้ช่วยตอบคำถามเรื่องภาษีเงินได้บุคคลธรรมดาของไทย โดยอาศัยความรู้ของคุณเอง ไม่มีเอกสารอ้างอิงให้

กติกา
1. ถ้าไม่แน่ใจหรือไม่มีข้อมูลพอจะตอบ ให้บอกตรง ๆ อย่าเดา
2. ถ้าคำถามขาดข้อมูลที่จำเป็นต่อคำตอบ (เช่น รายได้ทั้งปี ประเภทเงินได้ สถานะสมรส) ให้ถามกลับว่าต้องการข้อมูลใด และอธิบายหลักเกณฑ์ที่เกี่ยวข้องเท่าที่ทำได้
3. ถ้าคำถามตั้งอยู่บนความเข้าใจผิด ให้ชี้แจงให้ถูกต้อง
4. เมื่อให้ตัวเลข วงเงิน หรืออัตรา ให้บอกปีภาษีที่ตัวเลขนั้นใช้ด้วย
5. ตอบเป็นภาษาไทย กระชับ ตรงประเด็น"""

KIND_TH = {
    "faq": "คำถาม-คำตอบ กรมสรรพากร", "article": "บทความ กรมสรรพากร", "ruling": "ข้อหารือภาษีอากร",
    "statute": "ประมวลรัษฎากร", "image": "อินโฟกราฟิก กรมสรรพากร", "index": "หน้าเว็บ กรมสรรพากร",
}
CITE = re.compile(r"\[(\d+)\]")
THINK_END = "</think>"


def strip_thinking(text: str) -> tuple[str, int]:
    """The answer without a reasoning model's <think> block, and the length of what was cut. Some chat templates open
    the block in the prompt, so the reply may hold only the closing tag; everything up to the last one is reasoning.
    Its [n] would otherwise count as citations."""
    if THINK_END not in text:
        return text, 0
    head, _, tail = text.rpartition(THINK_END)
    return tail, len(head) + len(THINK_END)


def year_label(c: dict) -> str:
    if c.get("tax_year"):
        return f"ปีภาษี {c['tax_year']}"
    if c.get("year"):
        return f"พ.ศ. {c['year']}"
    return "ไม่ระบุปี"


def source_block(n: int, c: dict) -> str:
    note = " (ถอดข้อความจากภาพ ยังไม่ได้ตรวจทาน)" if "unverified" in (c.get("flags") or []) else ""
    return f"[{n}] {c['header']}\nประเภท: {KIND_TH.get(c['kind'], c['kind'])} | {year_label(c)}{note}\n{c['text']}"


def user_message(question: str, hits: list[dict]) -> str:
    sources = "\n\n".join(source_block(n, c) for n, c in enumerate(hits, 1))
    return f"เอกสารอ้างอิง\n\n{sources}\n\nคำถาม: {question}"


def retrieval_query(q: Question, earlier: list[Question]) -> str:
    return "\n".join([p.text for p in earlier] + [q.text])


def messages_for(question: str, hits: list[dict] | None, turns: list[tuple[str, str]] = ()) -> list[dict]:
    """System prompt, earlier (question, answer) turns without their sources, then this turn with its sources.
    `hits` None: no retrieval, the no-sources prompt and the bare question."""
    msgs = [{"role": "system", "content": SYSTEM if hits is not None else SYSTEM_NO_SOURCES}]
    for q, a in turns:
        msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    return msgs + [{"role": "user", "content": user_message(question, hits) if hits is not None else question}]


def citations(answer: str, hits: list[dict]) -> tuple[list[str], list[int]]:
    """Chunk ids cited as [n], in order of first citation, and citation numbers that match no source."""
    nums = list(dict.fromkeys(int(n) for n in CITE.findall(answer)))
    return [hits[n - 1]["chunk_id"] for n in nums if 1 <= n <= len(hits)], [n for n in nums if not 1 <= n <= len(hits)]


def answer(gen: llm.Profile, question: str, hits: list[dict] | None, turns: list[tuple[str, str]] = ()) -> tuple[str, int, llm.Reply]:
    """The answer, the characters of reasoning cut from it (the raw reply stays in the cache) and the reply."""
    r = llm.chat(gen, messages_for(question, hits, turns))
    text, thinking = strip_thinking(r.text)
    return text.strip(), thinking, r


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def git_commit() -> str:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "rag/"], capture_output=True, text=True).stdout.strip()
    return r.stdout.strip() + ("+dirty" if dirty else "")


def run(qs: list[Question], all_qs: list[Question], gen_name: str, mode: str, k: int, subset: str,
        embed_model: str = DEFAULT_MODEL, max_per_doc: int | None = None) -> Path:
    from rag.retrieve import Retriever

    gen = llm.profile(gen_name)
    if mode == NONE:
        run_id = f"{time.strftime('%Y%m%d')}-{subset}-{gen_name}-{NONE}-{NO_SOURCES_VERSION}"
    else:
        run_id = f"{time.strftime('%Y%m%d')}-{subset}-{gen_name}-{mode}-k{k}{f'-cap{max_per_doc}' if max_per_doc else ''}-{PROMPT_VERSION}"
    out = RUNS / run_id
    out.mkdir(parents=True, exist_ok=True)

    # earlier turns that are not in the subset are answered too: a later turn needs them as conversation
    need = {q.id: q for q in qs}
    for q in qs:
        need |= {p.id: p for p in history(q, all_qs)}
    todo = [q for q in all_qs if q.id in need]  # file order keeps turns in order

    retrieved = {q.id: (None, None) for q in todo}
    if mode != NONE:
        retriever = Retriever(embed_model)
        for q in todo:  # retrieval does not depend on answers, so it all runs first, on one thread
            query = retrieval_query(q, history(q, all_qs))
            retrieved[q.id] = (query, retriever.search(query, mode, k, max_per_doc))

    records: dict[str, dict] = {}
    in_subset = {q.id for q in qs}

    def do(group: list[Question]) -> None:  # one multi-turn set, or one single question
        turns: list[tuple[str, str]] = []
        for q in group:
            query, hits = retrieved[q.id]
            text, thinking, r = answer(gen, q.text, hits, turns)
            cited, bad = citations(text, hits or [])
            records[q.id] = dict(
                id=q.id, category=q.category, kind=q.kind, difficulty=q.difficulty, set=q.set, turn=q.turn,
                question=q.text, retrieval_query=query, in_subset=q.id in in_subset,
                hits=[dict(rank=h["rank"], chunk_id=h["chunk_id"], doc_id=h["doc_id"], score=round(h["score"], 4)) for h in hits or []],
                answer=text, thinking_chars=thinking, cited=cited, bad_citations=bad, served_model=r.model, usage=r.usage, seconds=r.seconds, cached=r.cached,
            )
            turns.append((q.text, text))

    groups: dict[str, list[Question]] = {}
    for q in todo:
        groups.setdefault(q.set or q.id, []).append(q)
    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(do, groups.values()))  # list() re-raises the first failure

    with (out / "answers.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(records[q.id], ensure_ascii=False) + "\n" for q in todo)
    usage = [r["usage"] for r in records.values() if not r["cached"]]
    config = dict(
        run_id=run_id, created=time.strftime("%Y-%m-%dT%H:%M:%S%z"), git=git_commit(), subset=subset,
        n_questions=len(qs), n_answered=len(todo),
        generator=dict(profile=gen.name, backend=gen.backend, model=gen.model, base_url=gen.base_url, params=gen.params,
                       served_models=sorted({r["served_model"] for r in records.values()})),
        prompt_version=NO_SOURCES_VERSION if mode == NONE else PROMPT_VERSION,
        system_prompt=SYSTEM_NO_SOURCES if mode == NONE else SYSTEM,
        retrieval=dict(mode=NONE) if mode == NONE else
        dict(mode=mode, k=k, max_per_doc=max_per_doc, embed_model=embed_model, chunks_sha=file_sha(OUT / "chunks.jsonl")),
        new_calls=len(usage), prompt_tokens=sum(u.get("prompt_tokens", 0) for u in usage),
        completion_tokens=sum(u.get("completion_tokens", 0) for u in usage),
    )
    (out / "config.json").write_text(json.dumps(config, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--subset", choices=("dev", "ablation", "all"))
    g.add_argument("--ids", help="comma-separated question ids")
    ap.add_argument("--gen", default="gpt-mini", help="generator profile in rag/models.toml")
    ap.add_argument("--mode", choices=(*MODES, NONE), default="hybrid", help=f"{NONE}: no retrieval, no sources")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--max-per-doc", type=int, help="at most this many chunks from one document (default: no cap)")
    a = ap.parse_args()
    all_qs = load()
    if a.ids:
        want = a.ids.split(",")
        qs, subset = [q for q in all_qs if q.id in want], "ids"
        if len(qs) != len(want):
            raise SystemExit(f"unknown ids: {sorted(set(want) - {q.id for q in qs})}")
    else:
        qs, subset = {"dev": dev, "ablation": ablation, "all": lambda x: x}[a.subset](all_qs), a.subset
    out = run(qs, all_qs, a.gen, a.mode, a.k, subset, max_per_doc=a.max_per_doc)
    c = json.loads((out / "config.json").read_text(encoding="utf-8"))
    print(f"{c['n_answered']} answers -> {out}")
    print(f"new calls {c['new_calls']}, tokens {c['prompt_tokens']} in + {c['completion_tokens']} out")


if __name__ == "__main__":
    main()
