"""Top-50 diagnostic: for the questions retrieval missed, is a chunk that answers them anywhere in the candidates?

For each `retrieval_miss` question of the dev run (out-of-scope questions excluded: a miss is the intended outcome there)
and for control questions that went well, the pool is every chunk the hybrid retriever's two rankings (dense top 50, sparse
top 50) found: at most 100, the whole fused list. The judge panel grades every pool chunk 0/1/2 against the question on the
rubric's chunk-relevance scale, in shuffled batches so the retrieval rank cannot bias the grade. The best-ranked chunk
graded 2 puts the question in one class:
  A  hybrid rank 1-5      retrieval was fine; the miss tag was about the answer or the labelling
  B  hybrid rank 6-50     ranking problem: the chunk is found, but too low (reranker, tax-year boost)
  C  hybrid rank 51+      fusion problem: only one ranking found it, and it fell below the 50 best
  D  no chunk graded 2    corpus or wording problem. "None in the pool" is not "none in the corpus": check by hand.
Decided before the run (docs/plans/generation-and-eval.md, *Top-50 diagnostic*): most of the questions in B and C means
ranking work next; most in D means corpus and query work; otherwise report it as mixed. Each class is reported twice, with
a 2 meaning the panel median is 2 (lenient; the judges grade about 0.2 above the people) and meaning all three judges say 2.

Human check (rag/depth_review.py): the panel's 2s on the miss questions were too lenient on a hand read, so a person
grades, per question, the best-ranked chunk the panel gave a 2, and the next one only if that is not a 2 (at most
CANDIDATES). The labels go to rag/eval/labels/<reviewer>/depth.csv; the class of a question is then the hybrid rank of
the first candidate a person graded 2, or D when none is.

Output: rag/out/depth/pool.jsonl (the pool and each chunk's ranks), judgments/<judge>.jsonl, summary.json
Run   : uv run python -m rag.depth --dry     # build the pool, print its size and the number of judge calls
        uv run python -m rag.depth           # grade with the panel (cached by rag.llm) and report
        uv run python -m rag.depth --report  # report from the saved judgments, no LLM
"""

import argparse
import hashlib
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from rag import evaluate, labels, llm
from rag.answer import source_block
from rag.chunk import OUT as CHUNKS, read_jsonl
from rag.panel import DEFAULT_PANEL, median
from rag.retrieve import cap_per_doc
from rag.questions import BEHAVIOURAL

ROOT = Path(__file__).parent.parent
OUT = ROOT / "rag" / "out" / "depth"
BASE_RUN = "20261020-dev-gpt-mini-hybrid-k5-v1"
CAP_RUN = "20261022-dev-gpt-mini-hybrid-k5-cap2-v1"
SEED = 20261022
N_CONTROLS = 10
BATCH = 10
CAP = 2
KS = (5, 10, 20, 50)
CLASSES = "ABCD"
CANDIDATES = 3  # chunks a person grades per question, at most
DEPTH_FIELDS = ["question_id", "chunk_id", "relevance", "note", "labelled_at"]
LABEL_FILES = {1: "depth.csv", 2: "depth_r2.csv"}  # one file per round of the human check
# Round 2 (added after round 1): chunks no one graded for the questions round 1 left at D. In the pool, the panel gave
# them a 2 but round 1 stopped at three candidates; outside it, a keyword search over every chunk found them.
ROUND2 = {
    "Q0078": ["62149#005", "551~001"],
    "Q0223": ["63908#008"],
    "Q0240": ["553~001"],
    "Q0301": ["552~001", "c14fb88f7fbe~001"],
    "Q0329": ["555~002", "5937#042"],
}
OUTSIDE = 101  # the rank a chunk outside the pool counts as: below the top 50 of both rankings

SYSTEM = f"""คุณเป็นผู้ตรวจว่าเอกสารแต่ละฉบับตอบคำถามภาษีเงินได้บุคคลธรรมดาของไทยได้หรือไม่
ปีภาษีล่าสุดที่ใช้ตัดสินว่าตัวเลขเป็น "ปัจจุบัน" คือ {evaluate.CURRENT_TAX_YEAR}

ให้คะแนนความเกี่ยวข้องของแต่ละเอกสารกับ "คำถาม" แต่ละฉบับแยกกัน ไม่เทียบกับฉบับอื่น
2 = มีสิ่งที่ต้องใช้ตอบ (หรือส่วนที่จำเป็น) | 1 = อยู่ในหัวข้อเดียวกันแต่ไม่ได้ตอบ เช่น กฎข้างเคียง ตัวเลขของปีอื่น ความรู้พื้นหลัง | 0 = ไม่เกี่ยวข้อง

ตอบเป็น JSON เท่านั้น: {{"relevance": {{"1": 2, "2": 0}}}}
relevance ต้องมีครบทุกหมายเลขเอกสาร"""


# ---------------------------------------------------------------- choosing the questions


def miss_ids(records: dict[str, dict]) -> list[str]:
    """Questions any person or the panel tagged retrieval_miss, on either run, minus the behavioural ones."""
    hit: set[str] = set()
    for r in labels.reviewers():
        hit |= {q for (run, q), lab in labels.answer_labels(r).items() if run == BASE_RUN and "retrieval_miss" in (lab.get("tags") or "")}
    for run in (BASE_RUN, CAP_RUN):
        for s in panel_scores(run):
            if "retrieval_miss" in s["rubric"]["tags"]:
                hit.add(s["id"])
    return sorted(q for q in hit if records[q]["kind"] not in BEHAVIOURAL)


def panel_scores(run: str) -> list[dict]:
    return read_jsonl(labels.RUNS / run / "judges" / "panel" / "scores.jsonl")


def control_ids(records: dict[str, dict], misses: list[str], n: int = N_CONTROLS, seed: int = SEED) -> list[str]:
    """Questions that went well: a content question, not tagged, scored 2 on grounded, correct and useful by the panel
    on the base run. A seeded sample of them, so the choice is repeatable."""
    ok = sorted(
        s["id"] for s in panel_scores(BASE_RUN)
        if s["kind"] not in BEHAVIOURAL and s["id"] not in misses and not s["rubric"]["tags"]
        and all(s["rubric"][f] == 2 for f in ("grounded", "correct", "useful"))
    )
    return sorted(random.Random(seed).sample(ok, min(n, len(ok))))


# ---------------------------------------------------------------- the pool


def build_pool(dense: list[int], sparse: list[int], fused: list[int], doc_ids: list[str], returned: set[int], cap: int = CAP) -> list[dict]:
    """One entry per chunk in the fused list, with its rank in each ranking (None when the ranking did not find it)."""
    d = {i: r for r, i in enumerate(dense, 1)}
    s = {i: r for r, i in enumerate(sparse, 1)}
    capped = {i: r for r, i in enumerate(cap_per_doc(fused, doc_ids, cap), 1)}
    return [dict(idx=i, hybrid_rank=r, dense_rank=d.get(i), sparse_rank=s.get(i), capped_rank=capped.get(i), returned=i in returned)
            for r, i in enumerate(fused, 1)]


def build(retriever, records: dict[str, dict], ids: list[str], group: dict[str, str]) -> list[dict]:
    doc_ids = [c["doc_id"] for c in retriever.chunks]
    out = []
    for q in ids:
        rec = records[q]
        dense, sparse, fused = retriever.rankings(rec["retrieval_query"])
        returned = {i for i, c in enumerate(retriever.chunks) if c["chunk_id"] in {h["chunk_id"] for h in rec["hits"]}}
        entries = build_pool(dense, sparse, [i for i, _ in fused], doc_ids, returned)
        for e in entries:
            c = retriever.chunks[e.pop("idx")]
            e.update(chunk_id=c["chunk_id"], doc_id=c["doc_id"], text_sha1=hashlib.sha1(c["text"].encode()).hexdigest()[:12])
        out.append(dict(id=q, group=group[q], kind=rec["kind"], question=rec["question"], query=rec["retrieval_query"], pool=entries))
    return out


# ---------------------------------------------------------------- grading


def batches(chunk_ids: list[str], qid: str, size: int = BATCH, seed: int = SEED) -> list[list[str]]:
    """The pool in a shuffled order that depends only on the question, cut into batches."""
    order = list(chunk_ids)
    random.Random(f"{seed}-{qid}").shuffle(order)
    return [order[i:i + size] for i in range(0, len(order), size)]


def check_grades(n: int):
    def check(d: dict) -> dict[int, int]:
        rel = {int(k): int(v) for k, v in d["relevance"].items()}
        if sorted(rel) != list(range(1, n + 1)) or not set(rel.values()) <= {0, 1, 2}:
            raise ValueError(f"relevance for {sorted(rel)}: {rel}")
        return rel

    return check


def grade_batch(ask, rec: dict, context: str, chunks: list[dict]) -> dict[str, int]:
    sources = "\n\n".join(source_block(n, c) for n, c in enumerate(chunks, 1))
    user = f"เอกสารอ้างอิง\n\n{sources}{context}\n\nคำถาม: {rec['question']}"
    rel, _ = ask(evaluate._msgs(SYSTEM, user), check_grades(len(chunks)))
    return {c["chunk_id"]: rel[n] for n, c in enumerate(chunks, 1)}


def grade(judge_name: str, items: list[dict], records: dict[str, dict], chunks: dict[str, dict]) -> list[dict]:
    ask = evaluate.make_ask(llm.profile(judge_name))
    jobs = []
    for it in items:
        rec = records[it["id"]]
        context = evaluate.conversation(rec, records)
        for ids in batches([e["chunk_id"] for e in it["pool"]], it["id"]):
            jobs.append((it["id"], rec, context, [chunks[c] for c in ids]))
    with ThreadPoolExecutor(evaluate.WORKERS) as ex:
        done = list(ex.map(lambda j: (j[0], grade_batch(ask, j[1], j[2], j[3])), jobs))
    return [dict(id=q, chunk_id=c, grade=g) for q, got in done for c, g in got.items()]


# ---------------------------------------------------------------- reading the grades


def classify(best: int | None) -> str:
    """Class of a question from the hybrid rank of its best chunk graded 2 (None: there is none)."""
    if best is None:
        return "D"
    return "A" if best <= 5 else "B" if best <= 50 else "C"


def best_rank(pool: list[dict], grades: dict[str, int]) -> int | None:
    return min((e["hybrid_rank"] for e in pool if grades[e["chunk_id"]] == 2), default=None)


def recall_at(pool: list[dict], grades: dict[str, int], k: int) -> float | None:
    """Share of the pool's chunks graded 2 that the hybrid ranking has in its top k; None without any."""
    twos = [e for e in pool if grades[e["chunk_id"]] == 2]
    return sum(e["hybrid_rank"] <= k for e in twos) / len(twos) if twos else None


def panel_grades(per_judge: dict[str, list[dict]], strict: bool) -> dict[str, dict[str, int]]:
    """{question: {chunk: grade}}: the median of the judges' grades, or the lowest when `strict` (a 2 needs all three)."""
    by: dict[tuple[str, str], list[int]] = {}
    for rows in per_judge.values():
        for r in rows:
            by.setdefault((r["id"], r["chunk_id"]), []).append(r["grade"])
    out: dict[str, dict[str, int]] = {}
    for (q, c), g in by.items():
        out.setdefault(q, {})[c] = min(g) if strict else median(g)
    return out


def summarise(items: list[dict], per_judge: dict[str, list[dict]], records: dict[str, dict]) -> dict:
    summary = {}
    for name, strict in (("median", False), ("strict", True)):
        grades = panel_grades(per_judge, strict)
        rows = []
        for it in items:
            g = grades[it["id"]]
            b = best_rank(it["pool"], g)
            rows.append(dict(id=it["id"], group=it["group"], best_rank=b, cls=classify(b), n_twos=sum(v == 2 for v in g.values()),
                             pool=len(g), recall={k: recall_at(it["pool"], g, k) for k in KS}))
        summary[name] = dict(
            questions=rows,
            classes={grp: {c: sum(r["cls"] == c for r in rows if r["group"] == grp) for c in CLASSES} for grp in ("miss", "control")},
        )
    # does the new grading agree with the grades the panel gave the same chunks inside the answer scores?
    new, old = panel_grades(per_judge, False), {s["id"]: s for s in panel_scores(BASE_RUN)}
    pairs = [(new[it["id"]][h["chunk_id"]], old[it["id"]]["rubric"]["relevance"][str(n)])
             for it in items for n, h in enumerate(records[it["id"]]["hits"], 1)]
    summary["calibration"] = dict(pairs=len(pairs), exact=sum(a == b for a, b in pairs) / len(pairs),
                                  mean_new_minus_old=sum(a - b for a, b in pairs) / len(pairs))
    return summary


def print_summary(items: list[dict], s: dict) -> None:
    for name in ("median", "strict"):
        print(f"\n== a 2 means: {'panel median is 2' if name == 'median' else 'all three judges say 2'}")
        print(f"{'question':8s} {'group':8s} {'pool':>4s} {'twos':>4s} {'best':>5s} class  " + "  ".join(f"r@{k}" for k in KS))
        for r in s[name]["questions"]:
            rec = "  ".join("  - " if r["recall"][k] is None else f"{r['recall'][k]:4.2f}" for k in KS)
            print(f"{r['id']:8s} {r['group']:8s} {r['pool']:4d} {r['n_twos']:4d} {str(r['best_rank'] or '-'):>5s}   {r['cls']}    {rec}")
        for grp, c in s[name]["classes"].items():
            print(f"  {grp:8s} " + "  ".join(f"{k} {v}" for k, v in c.items()))
    c = s["calibration"]
    print(f"\nagainst the panel's grades of the same chunks in the dev run: {c['pairs']} pairs, exact {c['exact']:.0%}, "
          f"new - old {c['mean_new_minus_old']:+.2f}")


# ---------------------------------------------------------------- the human check


def candidates(pool: list[dict], grades: dict[str, int], n: int = CANDIDATES) -> list[dict]:
    """The chunks a person grades for one question: those the panel median gave a 2, best hybrid rank first."""
    return sorted((e for e in pool if grades[e["chunk_id"]] == 2), key=lambda e: e["hybrid_rank"])[:n]


def status(cands: list[dict], human: dict[str, int]) -> tuple[str, dict | None]:
    """Where a question stands, from its candidates and the human grade of each ({chunk: grade}, missing = not graded):
    ('pending', the candidate to grade next), ('found', the first candidate graded 2) or ('none', None)."""
    for e in cands:
        g = human.get(e["chunk_id"])
        if g is None:
            return "pending", e
        if g == 2:
            return "found", e
    return "none", None


def round2_candidates(items: dict[str, dict]) -> dict[str, list[dict]]:
    """Round 2's chunks per question, best rank first: the pool entry, or for a chunk outside the pool an entry with
    no ranks (hybrid_rank None)."""
    out = {}
    for q, ids in ROUND2.items():
        pool = {e["chunk_id"]: e for e in items[q]["pool"]}
        es = [pool.get(c, dict(chunk_id=c, hybrid_rank=None, dense_rank=None, sparse_rank=None, returned=False)) for c in ids]
        out[q] = sorted(es, key=lambda e: e["hybrid_rank"] or OUTSIDE)
    return out


def final_class(r1: tuple[str, dict | None], r2: tuple[str, dict | None] | None) -> str | None:
    """A question's class over both rounds, from each round's `status` (r2 None: round 2 has no chunk for it);
    None while a chunk it depends on is still to grade."""
    st, e = r1
    if st == "found":
        return classify(e["hybrid_rank"])
    if st == "pending":
        return None
    if r2 is None:
        return "D"
    st, e = r2
    if st == "pending":
        return None
    return classify(e["hybrid_rank"] or OUTSIDE) if st == "found" else "D"


def read_depth_labels(reviewer: str, rnd: int = 1) -> dict[tuple[str, str], dict]:
    return {(r["question_id"], r["chunk_id"]): r for r in labels._read(labels.LABELS / reviewer / LABEL_FILES[rnd])}


def human_grades(reviewers: list[str], rnd: int = 1) -> dict[tuple[str, str], int]:
    """{(question, chunk): grade}: the median of the reviewers' grades, the lower middle for an even number."""
    by: dict[tuple[str, str], list[int]] = {}
    for r in reviewers:
        for key, row in read_depth_labels(r, rnd).items():
            if row["relevance"] != "":
                by.setdefault(key, []).append(int(row["relevance"]))
    return {k: median(v) for k, v in by.items()}


def next_pending(cands: dict[str, list[dict]], grades: dict[tuple[str, str], int], after: tuple[str, str] | None = None) -> tuple[str, str] | None:
    """The (question, chunk) to grade next: the pending candidate of each question not yet resolved (see `status`), the
    first one after `after` in question order, wrapping round; None when nothing is pending."""
    pend = []
    for q, cs in cands.items():
        st, e = status(cs, {c: g for (qq, c), g in grades.items() if qq == q})
        if st == "pending":
            pend.append((q, e["chunk_id"]))
    if not pend:
        return None
    order = [(q, e["chunk_id"]) for q, cs in cands.items() for e in cs]
    pos = order.index(after) if after in order else -1
    return next((p for p in pend if order.index(p) > pos), pend[0])


def save_depth_label(reviewer: str, question_id: str, chunk_id: str, relevance: int, note: str, rnd: int = 1) -> None:
    path = labels.LABELS / reviewer / LABEL_FILES[rnd]
    rows = [r for r in labels._read(path) if (r["question_id"], r["chunk_id"]) != (question_id, chunk_id)]
    rows.append(dict(question_id=question_id, chunk_id=chunk_id, relevance=relevance, note=note.strip(),
                     labelled_at=time.strftime("%Y-%m-%dT%H:%M:%S%z")))
    labels._write(path, DEPTH_FIELDS, rows)


def strip_position(rank: int | None) -> float:
    """Where a hybrid rank sits on a 0-100 strip. Ranks 1-5 (what the generator saw) get a quarter of it, 6-50 half,
    51 and below the last quarter, so the part that matters stays readable. None (outside the pool) is the far end."""
    if rank is None:
        return 99.0
    if rank <= 5:
        return (rank - 0.5) / 5 * 25
    if rank <= 50:
        return 25 + (rank - 5.5) / 45 * 50
    return 75 + (min(rank, 100) - 50.5) / 50 * 22  # stops short of the end, which is kept for outside the pool


# ---------------------------------------------------------------- run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="build the pool and count the calls; no LLM")
    ap.add_argument("--report", action="store_true", help="report from the saved judgments; no LLM")
    ap.add_argument("--judges", nargs="+", default=DEFAULT_PANEL)
    a = ap.parse_args()

    records = {r["id"]: r for r in read_jsonl(labels.RUNS / BASE_RUN / "answers.jsonl")}
    chunks = {c["chunk_id"]: c for c in read_jsonl(CHUNKS / "chunks.jsonl")}
    pool_path = OUT / "pool.jsonl"
    if pool_path.exists() and (a.report or not a.dry):
        items = read_jsonl(pool_path)
    else:
        from rag.retrieve import Retriever

        misses = miss_ids(records)
        controls = control_ids(records, misses)
        group = {q: "miss" for q in misses} | {q: "control" for q in controls}
        items = build(Retriever(), records, misses + controls, group)
        OUT.mkdir(parents=True, exist_ok=True)
        pool_path.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
    n_pairs = sum(len(i["pool"]) for i in items)
    n_calls = sum(len(batches([e["chunk_id"] for e in i["pool"]], i["id"])) for i in items)
    print(f"{len(items)} questions ({sum(i['group'] == 'miss' for i in items)} miss, {sum(i['group'] == 'control' for i in items)} control), "
          f"{n_pairs} pairs, {n_calls} calls per judge -> {pool_path}")
    if a.dry:
        print("misses  : " + " ".join(i["id"] for i in items if i["group"] == "miss"))
        print("controls: " + " ".join(i["id"] for i in items if i["group"] == "control"))
        return

    (OUT / "judgments").mkdir(exist_ok=True)
    per_judge = {}
    for j in a.judges:
        path = OUT / "judgments" / f"{j}.jsonl"
        if not a.report:
            rows = grade(j, items, records, chunks)
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
        per_judge[j] = read_jsonl(path)
    s = summarise(items, per_judge, records)
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(items, s)


if __name__ == "__main__":
    main()
