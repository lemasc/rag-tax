"""E1, the ranking ablation: which of dense, sparse and hybrid puts chunks that answer the question near the top?

For each content question (normal and multi-turn; the behavioural kinds test the answer, not the chunks) the pool is the
union of the top TOP chunks of the three modes, about 21 per question. The judge panel grades every pool chunk 0/1/2 once,
on the rubric's chunk-relevance scale, in shuffled batches that hide the mode and rank a chunk came from (the prompt and
the batching are those of rag.depth). A mode's score is then computed from where it ranked the graded chunks, so one
grading serves all three modes. Grades are kept per (question, chunk id, chunk text hash): a later variant (a reranker,
k = 10) only grades the chunks that are new to the pool.
Plan and decisions: docs/plans/ablation-plan-retrieval-context-generator.md, E1.

Metrics per mode (a 2 is the panel median, or all three judges when strict):
  hit@5        share of questions with a 2 in the top 5
  precision@5  share of the top 5 graded 2
  MRR@10       1 / rank of the first 2 in the top 10
  nDCG@10      the 0/1/2 grades discounted by rank, against the best order of the pool
  recall@10    share of the pool's 2s in the mode's top 10 (relative to the pool, not to the corpus)
A question with no 2 in the pool counts 0 for hit and MRR and is left out of recall and nDCG (no mode can score there);
`no_two` lists them. Differences between modes are paired by question, with a bootstrap interval.

Output: rag/out/pooled/pool.jsonl (the pool and each mode's top TOP), judgments/<judge>.jsonl, summary.json
Run   : uv run python -m rag.pooled --dry     # build the pool, print its size and the number of judge calls
        uv run python -m rag.pooled           # grade what is not graded yet with the panel, and report
        uv run python -m rag.pooled --report  # report from the saved judgments, no LLM
"""

import argparse
import hashlib
import json
import math
import random
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from pathlib import Path

import numpy as np

from rag import chunk_version, evaluate, llm
from rag.answer import retrieval_query
from rag.chunk import OUT as CHUNKS, read_jsonl
from rag.depth import SEED, batches, grade_batch
from rag.panel import DEFAULT_PANEL, median
from rag.questions import BEHAVIOURAL, Question, dev, history, load

ROOT = Path(__file__).parent.parent
OUT = ROOT / "rag" / "out" / "pooled"
MODES = ("dense", "sparse", "hybrid")
TOP = 10  # each mode's ranking is cut here before pooling, and scored here
BOOTSTRAP = 2000
GRADINGS = (("median", False), ("strict", True))  # a 2 is the panel median / all three judges


# ---------------------------------------------------------------- the pool


def content_questions(qs: list[Question]) -> list[Question]:
    return [q for q in qs if q.kind not in BEHAVIOURAL]


def build(retriever, qs: list[Question], all_qs: list[Question], dev_ids: set[str]) -> list[dict]:
    """One item per question: each mode's top TOP chunk ids, and the pool (their union) with each chunk's text hash."""
    chunks = retriever.chunks
    out = []
    for q in qs:
        earlier = history(q, all_qs)
        query = retrieval_query(q, earlier)
        dense, sparse, fused = retriever.rankings(query)
        tops = dict(dense=dense[:TOP], sparse=sparse[:TOP], hybrid=[i for i, _ in fused[:TOP]])
        pool = sorted({i for r in tops.values() for i in r})
        out.append(dict(
            id=q.id, category=q.category, kind=q.kind, dev=q.id in dev_ids, question=q.text, earlier=[p.text for p in earlier],
            query=query, rankings={m: [chunks[i]["chunk_id"] for i in r] for m, r in tops.items()},
            pool=[dict(chunk_id=chunks[i]["chunk_id"], text_sha1=hashlib.sha1(chunks[i]["text"].encode()).hexdigest()[:12]) for i in pool],
        ))
    return out


# ---------------------------------------------------------------- grading


def earlier_turns(item: dict) -> str:
    """The earlier questions of a multi-turn set. The answers are not given: this experiment generates none."""
    return "".join(f"\n\nบทสนทนาก่อนหน้า\nคำถาม: {t}" for t in item["earlier"])


def missing(items: list[dict], done: list[dict]) -> dict[str, list[str]]:
    """{question: chunk ids} of the pool pairs without a grade for the same chunk text."""
    have = {(r["id"], r["chunk_id"], r["text_sha1"]) for r in done}
    return {it["id"]: ids for it in items if (ids := [e["chunk_id"] for e in it["pool"] if (it["id"], e["chunk_id"], e["text_sha1"]) not in have])}


def grade(judge_name: str, items: list[dict], done: list[dict], chunks: dict[str, dict]) -> list[dict]:
    """The judge's grades for the pairs not in `done` (rows of id, chunk_id, text_sha1, grade); a batch it fails twice is skipped."""
    ask = evaluate.make_ask(llm.profile(judge_name))
    by_id = {it["id"]: it for it in items}
    todo = missing(items, done)
    jobs = [(q, ids) for q, all_ids in todo.items() for ids in batches(all_ids, q)]
    sha = {(it["id"], e["chunk_id"]): e["text_sha1"] for it in items for e in it["pool"]}

    def run(job):
        q, ids = job
        it = by_id[q]
        try:
            return q, grade_batch(ask, dict(question=it["question"]), earlier_turns(it), [chunks[c] for c in ids])
        except ValueError as e:  # a reply unusable twice: leave the batch for the next run, keep the others
            print(f"{judge_name}: {q} batch of {len(ids)} not graded: {e}")
            return q, {}

    with ThreadPoolExecutor(evaluate.WORKERS) as ex:
        got = list(ex.map(run, jobs))
    return [dict(id=q, chunk_id=c, text_sha1=sha[q, c], grade=g) for q, rows in got for c, g in rows.items()]


def panel_grades(per_judge: dict[str, list[dict]], items: list[dict], strict: bool) -> dict[str, dict[str, int]]:
    """{question: {chunk: grade}} over the current pool only: the median of the judges' grades, or the lowest when strict."""
    keep = {(it["id"], e["chunk_id"], e["text_sha1"]) for it in items for e in it["pool"]}
    by: dict[tuple[str, str], list[int]] = {}
    for rows in per_judge.values():
        for r in rows:
            if (r["id"], r["chunk_id"], r["text_sha1"]) in keep:
                by.setdefault((r["id"], r["chunk_id"]), []).append(r["grade"])
    out: dict[str, dict[str, int]] = {}
    for (q, c), g in by.items():
        out.setdefault(q, {})[c] = min(g) if strict else median(g)
    return out


def judge_grades(per_judge: dict[str, list[dict]], items: list[dict]) -> dict[str, dict[tuple[str, str], int]]:
    """Each judge's own grades, {judge: {(question, chunk): grade}}, over the current pool only."""
    keep = {(it["id"], e["chunk_id"], e["text_sha1"]) for it in items for e in it["pool"]}
    return {j: {(r["id"], r["chunk_id"]): r["grade"] for r in rows if (r["id"], r["chunk_id"], r["text_sha1"]) in keep}
            for j, rows in per_judge.items()}


def contested(item: dict, by_judge: dict[str, dict[tuple[str, str], int]]) -> list[str]:
    """The pool chunks two judges grade two points apart (a 0 and a 2): the ones a person should read."""
    out = []
    for e in item["pool"]:
        g = [by_judge[j][item["id"], e["chunk_id"]] for j in by_judge]
        if max(g) - min(g) == 2:
            out.append(e["chunk_id"])
    return out


# ---------------------------------------------------------------- metrics


def question_metrics(ranking: list[str], grades: dict[str, int]) -> dict[str, float | None]:
    """One mode's scores on one question; `grades` covers the whole pool. None: no 2 in the pool, so nothing to find."""
    top = ranking[:TOP]
    g = [grades[c] for c in top]
    first = next((r for r, x in enumerate(g, 1) if x == 2), None)
    n_two = sum(v == 2 for v in grades.values())
    ideal = sum(x / math.log2(r + 1) for r, x in enumerate(sorted(grades.values(), reverse=True)[:TOP], 1))
    dcg = sum(x / math.log2(r + 1) for r, x in enumerate(g, 1))
    return dict(
        hit5=float(2 in g[:5]), precision5=sum(x == 2 for x in g[:5]) / 5, mrr10=1 / first if first else 0.0,
        ndcg10=dcg / ideal if ideal else None, recall10=sum(x == 2 for x in g) / n_two if n_two else None,
    )


def metrics_by_question(items: list[dict], grades: dict[str, dict[str, int]]) -> dict[str, dict[str, dict]]:
    """{mode: {question: metrics}}."""
    return {m: {it["id"]: question_metrics(it["rankings"][m], grades[it["id"]]) for it in items} for m in MODES}


def mean_of(values: list[float | None]) -> float | None:
    vs = [v for v in values if v is not None]
    return sum(vs) / len(vs) if vs else None


def paired_difference(a: dict[str, float | None], b: dict[str, float | None], seed: int = SEED) -> dict:
    """Mean of a - b over the questions both have a value for, with a 95% bootstrap interval over questions."""
    d = np.array([a[q] - b[q] for q in a if a[q] is not None and b[q] is not None])
    if not len(d):
        return dict(mean=None, lo=None, hi=None, n=0)
    boot = d[np.random.default_rng(seed).integers(0, len(d), (BOOTSTRAP, len(d)))].mean(axis=1)
    lo, hi = np.percentile(boot, [2.5, 97.5])
    return dict(mean=float(d.mean()), lo=float(lo), hi=float(hi), n=len(d))


def compare_modes(item: dict, grades: dict[str, dict[str, int]], a: str = "dense", b: str = "hybrid") -> str:
    """Which of two modes has a 2 in its top 5 on this question: 'both', 'a only', 'b only', 'neither', or
    'no 2 in pool' (nothing any mode found answers it: a corpus or wording problem, not ranking)."""
    g = grades[item["id"]]
    if not any(v == 2 for v in g.values()):
        return "no 2 in pool"
    ha, hb = (any(g[c] == 2 for c in item["rankings"][m][:5]) for m in (a, b))
    return "both" if ha and hb else f"{a} only" if ha else f"{b} only" if hb else "neither"


def hybrid_top5_sources(items: list[dict], grades: dict[str, dict[str, int]]) -> dict[str, list[int]]:
    """The grades of the chunks in hybrid's top 5, by which rankings had the chunk in their own top TOP: 'both',
    'dense only', 'sparse only', or 'neither' (the fusion lifted it from rank TOP+1 or below in one of them)."""
    out: dict[str, list[int]] = {k: [] for k in ("both", "dense only", "sparse only", "neither")}
    for it in items:
        d, s = it["rankings"]["dense"], it["rankings"]["sparse"]
        for c in it["rankings"]["hybrid"][:5]:
            out["both" if c in d and c in s else "dense only" if c in d else "sparse only" if c in s else "neither"].append(grades[it["id"]][c])
    return out


def summarise(items: list[dict], per_judge: dict[str, list[dict]]) -> dict:
    out = {}
    for name, strict in GRADINGS:
        grades = panel_grades(per_judge, items, strict)
        by_q = metrics_by_question(items, grades)
        fields = list(next(iter(next(iter(by_q.values())).values())))
        subsets = {"all": items, "without_dev": [it for it in items if not it["dev"]]} | {
            f"category:{c}": [it for it in items if it["category"] == c] for c in sorted({it["category"] for it in items})}
        res = {}
        for label, sub in subsets.items():
            ids = [it["id"] for it in sub]
            res[label] = dict(
                n=len(ids),
                modes={m: {f: mean_of([by_q[m][q][f] for q in ids]) for f in fields} for m in MODES},
                no_two=[q for q in ids if not any(v == 2 for v in grades[q].values())],
            )
            if label in ("all", "without_dev"):  # a bootstrap on a category of six questions would mean little
                res[label]["differences"] = {
                    f"{a}-{b}": {f: paired_difference({q: by_q[a][q][f] for q in ids}, {q: by_q[b][q][f] for q in ids}) for f in fields}
                    for a, b in combinations(MODES[::-1], 2)  # hybrid-sparse, hybrid-dense, sparse-dense
                }
        out[name] = res
    return out


def print_summary(s: dict) -> None:
    for name in ("median", "strict"):
        print(f"\n== a 2 means: {'panel median is 2' if name == 'median' else 'all three judges say 2'}")
        for label, r in s[name].items():
            if label.startswith("category:"):
                continue
            print(f"-- {label}: {r['n']} questions, {len(r['no_two'])} with no 2 in the pool")
            fields = list(r["modes"]["dense"])
            print(f"{'':8s}" + "".join(f"{f:>12s}" for f in fields))
            for m in MODES:
                print(f"{m:8s}" + "".join(f"{r['modes'][m][f]:12.3f}" if r["modes"][m][f] is not None else f"{'-':>12s}" for f in fields))
            for pair, d in r.get("differences", {}).items():
                cells = [f"{x['mean']:+.3f} [{x['lo']:+.3f},{x['hi']:+.3f}]" if x["mean"] is not None else "-" for x in d.values()]
                print(f"{pair:>15s} " + "  ".join(cells))
    print(f"\nper category: see summary.json ({len(s['median']) - 2} categories)")


# ---------------------------------------------------------------- run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="build the pool and count the calls; no LLM")
    ap.add_argument("--report", action="store_true", help="report from the saved judgments; no LLM")
    ap.add_argument("--rebuild", action="store_true", help="retrieve again even when pool.jsonl exists")
    ap.add_argument("--judges", nargs="+", default=DEFAULT_PANEL)
    a = ap.parse_args()

    pool_path = OUT / "pool.jsonl"
    chunks = {c["chunk_id"]: c for c in read_jsonl(CHUNKS / "chunks.jsonl")}
    if pool_path.exists() and not a.rebuild:
        items = read_jsonl(pool_path)
    else:
        from rag.retrieve import Retriever

        all_qs = load()
        items = build(Retriever(), content_questions(all_qs), all_qs, {q.id for q in dev(all_qs)})
        OUT.mkdir(parents=True, exist_ok=True)
        pool_path.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in items), encoding="utf-8")
        (OUT / "pool_config.json").write_text(json.dumps(dict(chunks_sha=chunk_version.current(), top=TOP, modes=MODES), indent=1), encoding="utf-8")
    sha = json.loads((OUT / "pool_config.json").read_text(encoding="utf-8"))["chunks_sha"]
    chunk_version.require(sha, "the pooled ranking pool")
    n_pairs = sum(len(i["pool"]) for i in items)
    print(f"{len(items)} questions ({sum(i['dev'] for i in items)} dev), {n_pairs} pairs ({n_pairs / len(items):.1f} per question) -> {pool_path}")

    (OUT / "judgments").mkdir(exist_ok=True)
    per_judge, to_grade = {}, 0
    for j in a.judges:
        path = OUT / "judgments" / f"{j}.jsonl"
        done = read_jsonl(path) if path.exists() else []
        todo = missing(items, done)
        calls = sum(len(batches(ids, q)) for q, ids in todo.items())
        to_grade += calls
        print(f"{j}: {n_pairs - sum(map(len, todo.values()))} pairs graded, {calls} calls to go")
        if not (a.dry or a.report) and todo:
            done += grade(j, items, done, chunks)
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in done), encoding="utf-8")
        per_judge[j] = done
    if a.dry or (a.report and to_grade):
        if a.report and to_grade:
            print("some pairs are not graded yet: run without --report")
        return
    if len(a.judges) < 3:
        print("fewer than three judges: graded and saved, but no report (a panel median needs three)")
        return
    s = summarise(items, per_judge)
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(s)


if __name__ == "__main__":
    main()
