"""Answer evaluation with a fixed LLM judge: RAGAS-style faithfulness and answer relevance, and the human rubric.

Metrics, per answer (all definitions implemented directly, see generation-and-eval.md step 5):
  faithfulness  the judge splits the answer into claims, then checks each against the sources the generator saw
                (and earlier turns of a multi-turn set). Score = supported claims / claims; None when the answer
                makes no factual claim (an ask-back, a "not in the sources").
  relevance     the judge writes RELEVANCE_N questions the answer would answer; score = mean cosine similarity
                (bge-m3) to the real question; 0 when the judge calls the answer noncommittal.
  rubric        one call with the same 0/1/2 rubric the human reviewers use (docs/plans/review-rubric.md,
                rag/labels.py): grounded, correct, useful, behaviour, failure tags, and a relevance for each source.
                Because the scales are the same, `--compare` can set the judge against the human labels.

The judge is the `judge` profile, one prompt version (JUDGE_VERSION), for every run: changing either invalidates
earlier scores. Calls are cached by rag.llm, so re-scoring is free. Faithfulness and relevance are meant for
normal and multi-turn questions; behavioural questions (ask-back, misconception, out of scope) are summarised by
the rubric's behaviour item, and their faithfulness/relevance are stored but kept out of the content table.

Output: rag/out/runs/<run_id>/scores.jsonl, scores_config.json, scores_summary.json
Run   : uv run python -m rag.evaluate [--run RUN_ID] [--limit N]    # default: the newest run
        uv run python -m rag.evaluate --run RUN_ID --compare         # judge against the human labels
"""

import argparse
import json
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from rag import llm
from rag.answer import source_block
from rag.chunk import OUT, read_jsonl
from rag.index import DEFAULT_MODEL, embed, load_model
from rag.labels import RUNS, TAGS, answer_labels, chunk_labels, is_complete, reviewers, runs
from rag.questions import BEHAVIOURAL

JUDGE_VERSION = "v1"
JUDGE_PROFILE = "judge"
RELEVANCE_N = 3
WORKERS = 4
CURRENT_TAX_YEAR = 2568  # the newest year in the corpus; the judge needs it to tell an old figure from a current one

Ask = Callable[[list[dict], Callable[[dict], object]], tuple[object, list[dict]]]

# ---------------------------------------------------------------- prompts (Thai, like the generator's)

CLAIMS_SYSTEM = """คุณเป็นผู้ตรวจคำตอบ งานของคุณคือแยกคำตอบเป็นข้อความย่อย (claim) ที่ตรวจสอบได้ทีละข้อ

กติกา
- แต่ละข้อเป็นประโยคเดียวที่เข้าใจได้ในตัวเอง (ไม่ใช้คำว่า "ดังกล่าว" "ข้างต้น" "ดังนั้น") และมีตัวเลข ปี เงื่อนไข ครบเท่าที่คำตอบกล่าวไว้
- เก็บเฉพาะข้อความที่อ้างข้อเท็จจริงหรือหลักเกณฑ์ ไม่ต้องใส่คำถามที่ถามกลับ คำทักทาย หรือการบอกว่าไม่พบข้อมูลในเอกสาร
- ตัดเครื่องหมายอ้างอิง เช่น [1] ออก ไม่ต้องตรวจว่าเลขอ้างอิงถูกหรือไม่
- ตอบเป็น JSON เท่านั้น: {"claims": ["...", "..."]} ถ้าไม่มีข้อความที่ตรวจสอบได้ ให้ตอบ {"claims": []}"""

VERIFY_SYSTEM = """คุณเป็นผู้ตรวจว่าข้อความแต่ละข้อมีอยู่ในเอกสารอ้างอิงหรือไม่ โดยไม่ใช้ความรู้ภายนอก

กติกา
- supported = true ก็ต่อเมื่อเอกสารอ้างอิง (หรือบทสนทนาก่อนหน้า ถ้ามี) ระบุข้อความนั้นไว้ตรง ๆ หรือสรุปได้โดยตรง รวมถึงตัวเลข ปี และเงื่อนไข
- ถ้าเอกสารไม่พูดถึง พูดไม่ครบ หรือขัดแย้ง ให้ supported = false แม้ข้อความนั้นจะถูกต้องตามกฎหมายจริง
- ตอบเป็น JSON เท่านั้น เรียงตามลำดับข้อความ: {"verdicts": [{"id": 1, "supported": true, "reason": "สั้น ๆ"}, ...]}"""

QUESTIONS_SYSTEM = f"""คุณจะได้รับคำตอบของระบบถามตอบภาษีเงินได้บุคคลธรรมดา จงเขียนคำถาม {RELEVANCE_N} ข้อที่คำตอบนี้ตอบได้ตรงที่สุด โดยไม่ต้องรู้คำถามจริง
และประเมินว่าคำตอบนี้ "ไม่ชัดเจน" (noncommittal) หรือไม่: ไม่ชัดเจนคือหลบ ตอบวนเวียน ปฏิเสธว่าไม่ทราบหรือไม่พบข้อมูล หรือเพียงถามกลับโดยไม่ให้สาระ
ตอบเป็น JSON เท่านั้น: {{"questions": ["..."], "noncommittal": false}}"""

RUBRIC_SYSTEM = f"""คุณเป็นผู้ตรวจคำตอบของระบบถามตอบภาษีเงินได้บุคคลธรรมดาของไทย ให้คะแนนตามเกณฑ์เดียวกับผู้ตรวจที่เป็นคน
ปีภาษีล่าสุดที่ใช้ตัดสินว่าตัวเลขเป็น "ปัจจุบัน" คือ {CURRENT_TAX_YEAR}

ความเกี่ยวข้องของแต่ละเอกสารอ้างอิงกับ "คำถาม" (ไม่ใช่กับคำตอบ)
2 = มีสิ่งที่ต้องใช้ตอบ (หรือส่วนที่จำเป็น) | 1 = อยู่ในหัวข้อเดียวกันแต่ไม่ได้ตอบ เช่น กฎข้างเคียง ตัวเลขของปีอื่น ความรู้พื้นหลัง | 0 = ไม่เกี่ยวข้อง

คะแนนคำตอบ (0, 1 หรือ 2) ตัดสินจากเอกสารอ้างอิงและความรู้ของคุณเรื่องกฎหมายภาษีเงินได้บุคคลธรรมดาปัจจุบัน
- grounded (ไม่แต่งเพิ่ม): 2 = ทุกข้อความมีในเอกสาร | 1 = รายละเอียดเล็กน้อยไม่มีในเอกสาร | 0 = ข้อความ ตัวเลข หรือเงื่อนไขสำคัญไม่มีในเอกสารหรือขัดกับเอกสาร
- correct (ถูกต้อง): 2 = ถูกต้องสำหรับปีภาษีปัจจุบัน รวมตัวเลขและเงื่อนไข | 1 = หลักถูกแต่ตัวเลขเก่า ขาดเงื่อนไข หรือไม่ระบุปีในจุดที่สำคัญ | 0 = ผิด หรือทำให้ผู้เสียภาษีเข้าใจผิด
- useful (ตอบตรง): 2 = ตอบคำถามตามที่ถาม | 1 = ตอบบางส่วน หรือซ่อนคำตอบ | 0 = ไม่ตอบ
คำตอบที่ตรงกับเอกสารแต่เอกสารล้าสมัยได้ grounded = 2 แต่ correct ต่ำ ให้ให้คะแนนสองข้อนี้แยกกัน

behaviour (ระบบทำสิ่งที่ประเภทคำถามต้องการหรือไม่):
- "na" = คำถามไม่ต้องการพฤติกรรมพิเศษ (คำถามทั่วไปส่วนใหญ่)
- "yes" = ถามกลับเมื่อข้อมูลไม่ครบ / แก้ความเข้าใจผิด / บอกว่าเอกสารไม่ครอบคลุม ตามที่คำถามต้องการ
- "no" = ควรทำแล้วไม่ทำ หรือทำทั้งที่ไม่ควร

แท็กความล้มเหลว (เลือกได้หลายข้อ หรือไม่เลือกเลย):
{chr(10).join(f"- {k}: {v}" for k, v in TAGS.items())}

ตอบเป็น JSON เท่านั้น:
{{"relevance": {{"1": 2, "2": 0}}, "grounded": 2, "correct": 2, "useful": 2, "behaviour": "na", "tags": [], "note": "เหตุผลสั้น ๆ"}}
relevance ต้องมีครบทุกหมายเลขเอกสารอ้างอิง"""

KIND_NOTE = {
    "normal": "คำถามทั่วไป",
    "multi_turn": "คำถามหลายรอบ (ดูบทสนทนาก่อนหน้า)",
    "ask_back": "คำถามนี้ขาดข้อมูลที่จำเป็น คำตอบที่ดีควรถามกลับ",
    "misconception": "คำถามนี้ตั้งอยู่บนความเข้าใจผิด คำตอบที่ดีควรชี้แจงให้ถูก",
    "out_of_scope": "คำถามนอกขอบเขตของเอกสาร คำตอบที่ดีควรบอกว่าเอกสารไม่ครอบคลุม",
}

# ---------------------------------------------------------------- judge calls


def make_ask(judge: llm.Profile) -> Ask:
    """ask(messages, check) -> (checked reply, replies). A reply that is not JSON, or that `check` rejects, is asked
    again once without the cache (which also replaces the bad cached text)."""

    def ask(messages, check):
        err = None
        for attempt in (0, 1):
            try:
                data, r = llm.chat_json(judge, messages, use_cache=attempt == 0)
                return check(data), [r]
            except (ValueError, KeyError, TypeError) as e:
                err = e
        raise ValueError(f"judge reply unusable twice: {err}")

    return ask


def _msgs(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def check_claims(d: dict) -> list[str]:
    claims = [str(c).strip() for c in d["claims"]]
    return [c for c in claims if c]


def check_verdicts(n: int) -> Callable[[dict], list[dict]]:
    def check(d: dict) -> list[dict]:
        v = d["verdicts"]
        if len(v) != n:
            raise ValueError(f"{len(v)} verdicts for {n} claims")
        return [dict(supported=bool(x["supported"]), reason=str(x.get("reason", ""))) for x in v]

    return check


def faithfulness(ask: Ask, context: str, answer: str) -> tuple[dict, list]:
    claims, replies = ask(_msgs(CLAIMS_SYSTEM, f"คำตอบ\n{answer}"), check_claims)
    if not claims:
        return dict(score=None, claims=[]), replies
    listing = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, 1))
    verdicts, more = ask(_msgs(VERIFY_SYSTEM, f"{context}\n\nข้อความที่ต้องตรวจ\n{listing}"), check_verdicts(len(claims)))
    rows = [dict(claim=c) | v for c, v in zip(claims, verdicts)]
    return dict(score=sum(r["supported"] for r in rows) / len(rows), claims=rows), replies + more


def check_questions(d: dict) -> dict:
    qs = [str(q).strip() for q in d["questions"] if str(q).strip()]
    if not qs:
        raise ValueError("no questions")
    return dict(questions=qs[:RELEVANCE_N], noncommittal=bool(d["noncommittal"]))


def relevance(ask: Ask, embedder: Callable[[list[str], bool], np.ndarray], question: str, answer: str) -> tuple[dict, list]:
    got, replies = ask(_msgs(QUESTIONS_SYSTEM, f"คำตอบ\n{answer}"), check_questions)
    if got["noncommittal"]:
        return dict(score=0.0, **got), replies
    q = embedder([question], True)[0]
    g = embedder(got["questions"], True)
    return dict(score=float(np.mean(g @ q)), **got), replies


def check_rubric(n_sources: int) -> Callable[[dict], dict]:
    def check(d: dict) -> dict:
        out = {}
        for f in ("grounded", "correct", "useful"):
            if int(d[f]) not in (0, 1, 2):
                raise ValueError(f"{f}={d[f]!r}")
            out[f] = int(d[f])
        if d["behaviour"] not in ("na", "yes", "no"):
            raise ValueError(f"behaviour={d['behaviour']!r}")
        rel = {str(k): int(v) for k, v in d["relevance"].items()}
        if sorted(rel) != sorted(str(i) for i in range(1, n_sources + 1)) or not set(rel.values()) <= {0, 1, 2}:
            raise ValueError(f"relevance for sources {sorted(rel)}: {rel}")
        tags = [t for t in d.get("tags", []) if t in TAGS]
        return out | dict(behaviour=d["behaviour"], relevance=rel, tags=tags, note=str(d.get("note", "")))

    return check


def rubric(ask: Ask, rec: dict, context: str) -> tuple[dict, list]:
    user = f"{context}\n\nประเภทคำถาม: {KIND_NOTE[rec['kind']]}\nคำถาม: {rec['question']}\n\nคำตอบที่ต้องให้คะแนน\n{rec['answer']}"
    return ask(_msgs(RUBRIC_SYSTEM, user), check_rubric(len(rec["hits"])))


# ---------------------------------------------------------------- scoring a run


def conversation(rec: dict, by_id: dict[str, dict]) -> str:
    """Earlier turns of the record's multi-turn set, as the generator saw them (question and its own answer)."""
    if not rec["set"]:
        return ""
    before = sorted((r for r in by_id.values() if r["set"] == rec["set"] and r["turn"] < rec["turn"]), key=lambda r: r["turn"])
    return "".join(f"\n\nบทสนทนาก่อนหน้า\nคำถาม: {r['question']}\nคำตอบ: {r['answer']}" for r in before)


def context_for(rec: dict, chunks: dict[str, dict], by_id: dict[str, dict]) -> str:
    sources = "\n\n".join(source_block(n, chunks[h["chunk_id"]]) for n, h in enumerate(rec["hits"], 1))
    return f"เอกสารอ้างอิง\n\n{sources}{conversation(rec, by_id)}"


def score_record(ask: Ask, embedder, rec: dict, chunks: dict, by_id: dict) -> dict:
    context = context_for(rec, chunks, by_id)
    f, r1 = faithfulness(ask, context, rec["answer"])
    rel, r2 = relevance(ask, embedder, rec["question"], rec["answer"])
    rub, r3 = rubric(ask, rec, context)
    new = [r.usage for r in r1 + r2 + r3 if not r.cached]
    return dict(id=rec["id"], category=rec["category"], kind=rec["kind"], faithfulness=f, relevance=rel, rubric=rub,
                judge_tokens=dict(prompt=sum(u.get("prompt_tokens", 0) for u in new),
                                  completion=sum(u.get("completion_tokens", 0) for u in new)))


class Embedder:
    """bge-m3 loaded on first use, so a fully cached re-score needs neither torch nor the GPU."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model_name, self.model = model, None
        self._lock = threading.Lock()

    def __call__(self, texts: list[str], query: bool) -> np.ndarray:
        with self._lock:  # the workers share one model; this also keeps two of them from loading it at once
            if self.model is None:
                self.model = load_model(self.model_name)
            return embed(self.model, self.model_name, texts, query)


def mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def summarise(scores: list[dict]) -> dict:
    """Means per group: 'content' (normal and multi-turn) overall and per category, 'behavioural' by kind."""
    def row(rows: list[dict]) -> dict:
        return dict(n=len(rows),
                    faithfulness=mean(r["faithfulness"]["score"] for r in rows),
                    relevance=mean(r["relevance"]["score"] for r in rows),
                    grounded=mean(r["rubric"]["grounded"] for r in rows),
                    correct=mean(r["rubric"]["correct"] for r in rows),
                    useful=mean(r["rubric"]["useful"] for r in rows),
                    behaviour={b: sum(r["rubric"]["behaviour"] == b for r in rows) for b in ("na", "yes", "no")})

    content = [s for s in scores if s["kind"] not in BEHAVIOURAL]
    by_cat, by_kind = defaultdict(list), defaultdict(list)
    for s in content:
        by_cat[s["category"]].append(s)
    for s in scores:
        if s["kind"] in BEHAVIOURAL:
            by_kind[s["kind"]].append(s)
    tags = defaultdict(int)
    for s in scores:
        for t in s["rubric"]["tags"]:
            tags[t] += 1
    return dict(content=row(content) if content else None, by_category={c: row(r) for c, r in sorted(by_cat.items())},
                behavioural={k: row(r) for k, r in sorted(by_kind.items())}, tags=dict(sorted(tags.items(), key=lambda x: -x[1])))


def fmt(x: float | None, nd: int = 2) -> str:
    return "  - " if x is None else f"{x:.{nd}f}"


def print_summary(s: dict) -> None:
    def line(name: str, r: dict) -> str:
        b = r["behaviour"]
        return (f"{name[:34]:34s} {r['n']:3d}  {fmt(r['faithfulness'])}  {fmt(r['relevance'])}  {fmt(r['grounded'])}  "
                f"{fmt(r['correct'])}  {fmt(r['useful'])}  {b['yes']}/{b['no']}")

    print(f"{'':34s} {'n':>3s}  faith  relev  grnd   corr   usef   behaviour yes/no")
    if s["content"]:
        print(line("content (normal + multi-turn)", s["content"]))
    for c, r in s["by_category"].items():
        print(line("  " + c, r))
    for k, r in s["behavioural"].items():
        print(line(k, r))
    if s["tags"]:
        print("tags: " + ", ".join(f"{t} {n}" for t, n in s["tags"].items()))


def run_dir(run_id: str | None) -> Path:
    run_id = run_id or (runs() or [None])[0]
    if not run_id or not (RUNS / run_id / "answers.jsonl").exists():
        raise SystemExit(f"no such run: {run_id!r}; known: {', '.join(runs())}")
    return RUNS / run_id


def evaluate(path: Path, judge_name: str = JUDGE_PROFILE, limit: int | None = None) -> list[dict]:
    judge = llm.profile(judge_name)
    ask = make_ask(judge)
    embedder = Embedder()
    records = read_jsonl(path / "answers.jsonl")
    by_id = {r["id"]: r for r in records}
    chunks = {c["chunk_id"]: c for c in read_jsonl(OUT / "chunks.jsonl")}
    todo = [r for r in records if r["in_subset"]][:limit]
    missing = {h["chunk_id"] for r in todo for h in r["hits"]} - set(chunks)
    if missing:
        raise SystemExit(f"{len(missing)} retrieved chunks are not in chunks.jsonl (rebuilt since the run?): {sorted(missing)[:3]}")

    with ThreadPoolExecutor(WORKERS) as pool:
        scores = list(pool.map(lambda r: score_record(ask, embedder, r, chunks, by_id), todo))

    with (path / "scores.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(s, ensure_ascii=False) + "\n" for s in scores)
    summary = summarise(scores)
    (path / "scores_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (path / "scores_config.json").write_text(json.dumps(dict(
        run_id=path.name, scored=time.strftime("%Y-%m-%dT%H:%M:%S%z"), judge_version=JUDGE_VERSION,
        judge=dict(profile=judge.name, backend=judge.backend, model=judge.model, base_url=judge.base_url, params=judge.params),
        embed_model=embedder.model_name, relevance_n=RELEVANCE_N, current_tax_year=CURRENT_TAX_YEAR, n_scored=len(scores),
        new_prompt_tokens=sum(s["judge_tokens"]["prompt"] for s in scores),
        new_completion_tokens=sum(s["judge_tokens"]["completion"] for s in scores),
    ), ensure_ascii=False, indent=1), encoding="utf-8")
    return scores


# ---------------------------------------------------------------- judge against the human labels


def agree(pairs: list[tuple[str, str]], numeric: bool) -> dict:
    """pairs of (judge, human) values. Exact share; for 0/1/2 scales also within one point and the mean judge - human."""
    pairs = [(a, b) for a, b in pairs if a != "" and b != ""]
    if not pairs:
        return dict(n=0)
    out = dict(n=len(pairs), exact=sum(a == b for a, b in pairs) / len(pairs))
    if numeric:
        d = [int(a) - int(b) for a, b in pairs]
        out |= dict(within_one=sum(abs(x) <= 1 for x in d) / len(d), bias=sum(d) / len(d))
    return out


def compare(path: Path, scores: list[dict]) -> dict[str, dict]:
    """Per reviewer and pooled: judge-human agreement on the rubric items and on chunk relevance. Pairs only
    where the reviewer's answer label is complete; chunks are matched by (question, chunk id)."""
    by_q = {s["id"]: s for s in scores}
    chunk_ids = {r["id"]: [h["chunk_id"] for h in r["hits"]] for r in read_jsonl(path / "answers.jsonl")}
    pooled: dict[str, list] = defaultdict(list)
    out = {}
    for rev in reviewers():
        al, cl = answer_labels(rev), chunk_labels(rev)
        pairs: dict[str, list] = defaultdict(list)
        for (rid, q), lab in al.items():
            if rid != path.name or q not in by_q or not is_complete(lab):
                continue
            rub = by_q[q]["rubric"]
            for f in ("grounded", "correct", "useful", "behaviour"):
                pairs[f].append((str(rub[f]), lab[f]))
            for n, cid in enumerate(chunk_ids[q], 1):
                if (q, cid) in cl:
                    pairs["relevance"].append((str(rub["relevance"][str(n)]), cl[(q, cid)]["relevance"]))
        for f, p in pairs.items():
            pooled[f] += p
        out[rev] = {f: agree(p, f != "behaviour") for f, p in pairs.items()}
    out["(all)"] = {f: agree(p, f != "behaviour") for f, p in pooled.items()}
    return out


def print_compare(c: dict[str, dict]) -> None:
    if not any(c.values()):
        print("no complete human labels for this run yet")
        return
    for rev, fields in c.items():
        print(rev)
        for f, a in fields.items():
            extra = f"  within-one {a['within_one']:.2f}  bias {a['bias']:+.2f}" if "within_one" in a else ""
            print(f"  {f:10s} n={a['n']:3d}  exact {a['exact']:.2f}{extra}" if a["n"] else f"  {f:10s} n=0")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="run id under rag/out/runs (default: the newest)")
    ap.add_argument("--judge", default=JUDGE_PROFILE)
    ap.add_argument("--limit", type=int, help="score only the first N questions (a smoke test)")
    ap.add_argument("--compare", action="store_true", help="compare saved scores with the human labels; no judge calls")
    a = ap.parse_args()
    path = run_dir(a.run)
    if a.compare:
        scores = [json.loads(ln) for ln in (path / "scores.jsonl").read_text(encoding="utf-8").splitlines()]
        print_compare(compare(path, scores))
        return
    scores = evaluate(path, a.judge, a.limit)
    print_summary(summarise(scores))
    cfg = json.loads((path / "scores_config.json").read_text(encoding="utf-8"))
    print(f"{len(scores)} answers scored by {cfg['judge']['model']} -> {path}/scores.jsonl "
          f"(new tokens {cfg['new_prompt_tokens']} in + {cfg['new_completion_tokens']} out)")


if __name__ == "__main__":
    main()
