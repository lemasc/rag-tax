"""E2, do neighbouring text help?: does the text next to a chunk make a "on topic, not enough" chunk answer the question?

The chunks are the ones E1 left graded 1 (panel median) in the dense or hybrid top 5, in two strata reported separately:
  clause       origin "clause" (a ข้อ, an (N) item of a legal instrument)
  later-part   a later part (part > 1) of a split statute or annex unit; the missing text is the part before it
plus a seeded sample of chunks graded 2 in the same strata, to see whether neighbours dilute a good chunk. Chunks only
sparse found, boilerplate (a decree's closing มาตรา on who enforces it) and chunks with no neighbour that fits are left out.

Each sampled (question, chunk) is graded twice by the panel, in the batches of rag.depth and blind to the E1 grade:
  alone     the chunk as in E1: a control. A 1 turns into a 2 now and then just by asking again.
  expanded  the chunk plus its neighbours: the other parts of its unit, then sibling units, nearest first, at most
            EXTRA_TOKENS of them.
The effect is the share of 1s that are 2 expanded minus the share that are 2 alone (the noise floor), per stratum, per
source ranking, per judge, for the questions with no 2 in the E1 pool on their own, and per distinct chunk (a few chunks
come up under many questions). Dilution is the share of 2s that fall below 2, expanded minus alone.
Plan and decisions: docs/plans/ablation-plan-retrieval-context-generator.md, E2.

Output: rag/out/neighbours/sample.jsonl (the sample and the text each condition shows), judgments/<judge>.jsonl, summary.json
Run   : uv run python -m rag.neighbours --dry     # build the sample, print its size and the number of judge calls
        uv run python -m rag.neighbours           # grade what is not graded yet with the panel, and report
        uv run python -m rag.neighbours --report  # report from the saved judgments, no LLM
"""

import argparse
import hashlib
import json
import random
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from rag import chunk_version, evaluate, llm
from rag.chunk import OUT as CHUNKS, read_jsonl
from rag.depth import SEED, batches, grade_batch
from rag.pooled import BOOTSTRAP, GRADINGS, OUT as POOLED, PANEL, earlier_turns, panel_grades

ROOT = Path(__file__).parent.parent
OUT = ROOT / "rag" / "out" / "neighbours"
RANKED = ("dense", "hybrid")  # sparse found the worst chunks in E1: its top 5 is not sampled
TOP = 5
EXTRA_TOKENS = 512  # the most neighbouring text added to a chunk
N_TWOS = {"clause": 40, "later-part": 20}  # chunks graded 2 that are also expanded, per stratum
CONDITIONS = ("alone", "expanded")
NEIGHBOUR_MARK = "[ข้อความข้างเคียงในเอกสารเดียวกัน]"
BOILERPLATE_TOKENS = 120
BOILERPLATE_WORD = "รักษาการ"


# ---------------------------------------------------------------- neighbours


def units_by_doc(chunks: list[dict]) -> dict[str, list[dict]]:
    """{doc_id: units in document order}; a unit is {unit_id, origin, parent, parts} with its chunks ordered by part.
    `parent` is the header without its last segment when the unit sits under another one (an (N) item under its ข้อ)."""
    docs: dict[str, dict[str, dict]] = defaultdict(dict)
    for c in chunks:
        if not c["unit_id"]:
            continue
        u = docs[c["doc_id"]].setdefault(c["unit_id"], dict(unit_id=c["unit_id"], origin=c["origin"], parent=None, parts=[]))
        u["parts"].append(c)
    out = {}
    for doc, units in docs.items():
        for u in units.values():
            u["parts"].sort(key=lambda c: c["part"] or 1)
            h = u["parts"][0]["header"]
            u["parent"] = h.rsplit(" | ", 1)[0] if h.count(" | ") >= 2 else None
        out[doc] = list(units.values())
    return out


def neighbours(c: dict, units: list[dict], cap: int = EXTRA_TOKENS) -> tuple[list[dict], list[dict]]:
    """The chunks that go with `c`, those before it and those after it, each in reading order: first the other parts of its own unit, then the units under the same
    parent (the document, for a top-level unit), nearest first and the next one before the previous one. A neighbour that
    would take the total over `cap` tokens is skipped, a smaller one further away may still fit."""
    at = next(i for i, u in enumerate(units) if u["unit_id"] == c["unit_id"])
    own = units[at]
    candidates = [p for p in sorted(own["parts"], key=lambda p: (abs((p["part"] or 1) - (c["part"] or 1)), (p["part"] or 1) < (c["part"] or 1)))
                  if p["chunk_id"] != c["chunk_id"]]
    sib = sorted((i for i, u in enumerate(units) if i != at and u["origin"] == own["origin"] and u["parent"] == own["parent"]),
                 key=lambda i: (abs(i - at), i < at))
    candidates += [p for i in sib for p in units[i]["parts"]]
    chosen, used = [], 0
    for p in candidates:
        if used + p["n_tokens"] <= cap:
            chosen.append(p)
            used += p["n_tokens"]
    where = {p["chunk_id"]: (i, p["part"] or 1) for i, u in enumerate(units) for p in u["parts"]}
    chosen.sort(key=lambda p: where[p["chunk_id"]])
    mine = where[c["chunk_id"]]
    return [p for p in chosen if where[p["chunk_id"]] < mine], [p for p in chosen if where[p["chunk_id"]] > mine]


def expanded_text(c: dict, before: list[dict], after: list[dict]) -> str:
    """The chunk's text with its neighbours around it in reading order; the neighbours are marked as such."""
    parts = [f"{NEIGHBOUR_MARK}\n{p['text']}" for p in before] + [c["text"]] + [f"{NEIGHBOUR_MARK}\n{p['text']}" for p in after]
    return "\n\n".join(parts)


def is_boilerplate(c: dict) -> bool:
    return c["n_tokens"] < BOILERPLATE_TOKENS and BOILERPLATE_WORD in c["text"]


def stratum(c: dict) -> str | None:
    if c["origin"] == "clause":
        return "clause"
    if c["origin"] in ("statute", "annex") and (c["part"] or 1) > 1 and (c["n_parts"] or 1) > 1:
        return "later-part"
    return None


# ---------------------------------------------------------------- the sample


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def build(items: list[dict], e1: dict[str, dict[str, int]], chunks: list[dict], seed: int = SEED) -> tuple[list[dict], dict]:
    """One row per sampled (question, chunk): its E1 grade, strata, rankings it was in the top 5 of, and the two texts.
    Also the counts of what was left out."""
    by_id = {c["chunk_id"]: c for c in chunks}
    units = units_by_doc(chunks)
    left = defaultdict(int)
    ones, twos = [], []
    for it in items:
        seen = set()
        for mode in RANKED:
            for cid in it["rankings"][mode][:TOP]:
                g = e1[it["id"]].get(cid)
                s = stratum(by_id[cid])
                if g not in (1, 2) or cid in seen:
                    continue
                if s is None:
                    left["other type"] += 1
                    seen.add(cid)
                    continue
                seen.add(cid)
                c = by_id[cid]
                if is_boilerplate(c):
                    left["boilerplate"] += 1
                    continue
                before, after = neighbours(c, units[c["doc_id"]])
                near = before + after
                if not near:
                    left["no neighbour fits"] += 1
                    continue
                no_two = not any(v == 2 for v in e1[it["id"]].values())
                row = dict(id=it["id"], chunk_id=cid, e1=g, stratum=s, no_two_question=no_two, kind=it["kind"], question=it["question"],
                           earlier=it["earlier"], in_dense=cid in it["rankings"]["dense"][:TOP], in_hybrid=cid in it["rankings"]["hybrid"][:TOP],
                           before=[p["chunk_id"] for p in before], after=[p["chunk_id"] for p in after], extra_tokens=sum(p["n_tokens"] for p in near),
                           text_sha1=dict(alone=sha1(c["text"]), expanded=sha1(expanded_text(c, before, after))))
                (ones if g == 1 else twos).append(row)
    rng = random.Random(seed)
    keep_twos = []
    for s, n in N_TWOS.items():
        pool = sorted((r for r in twos if r["stratum"] == s), key=lambda r: (r["id"], r["chunk_id"]))
        keep_twos += rng.sample(pool, min(n, len(pool)))
    left["2s not sampled"] = len(twos) - len(keep_twos)
    return sorted(ones + keep_twos, key=lambda r: (r["id"], r["chunk_id"])), dict(left)


# ---------------------------------------------------------------- grading


def missing(sample: list[dict], done: list[dict]) -> list[tuple[str, str, str]]:
    """(question, chunk, condition) without a grade for the same shown text."""
    have = {(r["id"], r["chunk_id"], r["condition"], r["text_sha1"]) for r in done}
    return [(r["id"], r["chunk_id"], cond) for r in sample for cond in CONDITIONS
            if (r["id"], r["chunk_id"], cond, r["text_sha1"][cond]) not in have]


def shown(row: dict, cond: str, by_id: dict[str, dict]) -> dict:
    c = by_id[row["chunk_id"]]
    return c if cond == "alone" else dict(c, text=expanded_text(c, [by_id[i] for i in row["before"]], [by_id[i] for i in row["after"]]))


def batches_of(q: str, ids: list[str], e1_batches: dict[str, set[frozenset]]) -> list[list[str]]:
    """The question's chunks cut into batches. A batch with the chunks of one of E1's batches (same question, so the same
    prompt for a judge on the same route) is put in the reverse order: otherwise a judge's cached E1 reply would come
    back as the "alone" grade and the control would be a copy of E1."""
    out = batches(sorted(ids), f"e2-{q}")
    return [b[::-1] if frozenset(b) in e1_batches.get(q, ()) else b for b in out]


def grade(judge_name: str, sample: list[dict], done: list[dict], by_id: dict[str, dict], e1_batches: dict[str, set[frozenset]]) -> list[dict]:
    """The judge's grades for what is not in `done`; a batch it fails twice is left for the next run. Both conditions
    batch the same chunks of a question in the same order (the shuffle depends on the question only), so they differ
    only in what is shown."""
    ask = evaluate.make_ask(llm.profile(judge_name))
    rows = {(r["id"], r["chunk_id"]): r for r in sample}
    todo = defaultdict(set)
    for q, cid, cond in missing(sample, done):
        todo[q, cond].add(cid)
    jobs = []
    for (q, cond), ids in todo.items():
        for batch in batches_of(q, ids, e1_batches):
            jobs.append((q, cond, batch))

    def run(job):
        q, cond, ids = job
        r0 = rows[q, ids[0]]
        try:
            got = grade_batch(ask, dict(question=r0["question"]), earlier_turns(r0), [shown(rows[q, c], cond, by_id) for c in ids])
            return [dict(id=q, chunk_id=c, condition=cond, text_sha1=rows[q, c]["text_sha1"][cond], grade=g) for c, g in got.items()]
        except ValueError as e:
            print(f"{judge_name}: {q} {cond} batch of {len(ids)} not graded: {e}")
            return []

    with ThreadPoolExecutor(evaluate.WORKERS) as ex:
        return [r for rs in ex.map(run, jobs) for r in rs]


# ---------------------------------------------------------------- reading the grades


def combined(per_judge: dict[str, list[dict]], sample: list[dict], strict: bool) -> dict[tuple[str, str, str], int]:
    """{(question, chunk, condition): grade}: the median of the judges, or the lowest when strict; only for grades of the
    text the sample shows now, and only when all judges graded it."""
    keep = {(r["id"], r["chunk_id"], c, r["text_sha1"][c]) for r in sample for c in CONDITIONS}
    by = defaultdict(list)
    for rows in per_judge.values():
        for r in rows:
            if (r["id"], r["chunk_id"], r["condition"], r["text_sha1"]) in keep:
                by[r["id"], r["chunk_id"], r["condition"]].append(r["grade"])
    n = len(per_judge)
    return {k: min(v) if strict else sorted(v)[(len(v) - 1) // 2] for k, v in by.items() if len(v) == n}


def effect(rows: list[dict], grade_of, e1_grade: int, seed: int = SEED) -> dict:
    """For the sampled chunks with this E1 grade: share that are 2 expanded, share that are 2 alone, the difference with a
    95% bootstrap interval over questions, and the same difference averaged per distinct chunk. `grade_of(row, cond)`
    gives a grade or None; rows missing either grade are left out."""
    sel = [r for r in rows if r["e1"] == e1_grade and None not in (grade_of(r, "alone"), grade_of(r, "expanded"))]
    if not sel:
        return dict(n=0)
    exp = np.array([grade_of(r, "expanded") == 2 for r in sel], float)
    alone = np.array([grade_of(r, "alone") == 2 for r in sel], float)
    out = dict(n=len(sel), questions=len({r["id"] for r in sel}), chunks=len({r["chunk_id"] for r in sel}),
               expanded_is_2=float(exp.mean()), alone_is_2=float(alone.mean()), difference=float((exp - alone).mean()))
    qs = sorted({r["id"] for r in sel})
    per_q = np.array([[(exp - alone)[[i for i, r in enumerate(sel) if r["id"] == q]].sum(), sum(r["id"] == q for r in sel)] for q in qs])
    idx = np.random.default_rng(seed).integers(0, len(qs), (BOOTSTRAP, len(qs)))
    boot = per_q[idx, 0].sum(axis=1) / per_q[idx, 1].sum(axis=1)
    out["lo"], out["hi"] = (float(x) for x in np.percentile(boot, [2.5, 97.5]))
    chunk_diff = defaultdict(list)
    for r, d in zip(sel, exp - alone):
        chunk_diff[r["chunk_id"]].append(d)
    out["per_chunk_difference"] = float(np.mean([np.mean(v) for v in chunk_diff.values()]))
    out["chunks_that_gain"] = int(sum(np.mean(v) > 0 for v in chunk_diff.values()))
    return out


def summarise(sample: list[dict], per_judge: dict[str, list[dict]]) -> dict:
    out = {}
    for name, strict in GRADINGS:
        g = combined(per_judge, sample, strict)
        grade_of = lambda r, cond, g=g: g.get((r["id"], r["chunk_id"], cond))  # noqa: E731
        groups = {"all": sample} | {f"stratum:{s}": [r for r in sample if r["stratum"] == s] for s in N_TWOS} | {
            "no-2 questions": [r for r in sample if r["no_two_question"]],
            "in dense top 5": [r for r in sample if r["in_dense"]], "in hybrid top 5": [r for r in sample if r["in_hybrid"]]}
        res = {}
        for label, rows in groups.items():
            res[label] = dict(gain=effect(rows, grade_of, 1), dilution=_dilution(rows, grade_of))
        for j, rows in per_judge.items():
            by = {(r["id"], r["chunk_id"], r["condition"]): r["grade"] for r in rows}
            res[f"judge:{j}"] = dict(gain=effect(sample, lambda r, c, by=by: by.get((r["id"], r["chunk_id"], c)), 1))
        out[name] = res
    return out


def _dilution(rows: list[dict], grade_of) -> dict:
    """Among chunks graded 2 in E1: share below 2 expanded, share below 2 alone, and the difference."""
    sel = [r for r in rows if r["e1"] == 2 and None not in (grade_of(r, "alone"), grade_of(r, "expanded"))]
    if not sel:
        return dict(n=0)
    exp = np.mean([grade_of(r, "expanded") < 2 for r in sel])
    alone = np.mean([grade_of(r, "alone") < 2 for r in sel])
    return dict(n=len(sel), expanded_below_2=float(exp), alone_below_2=float(alone), difference=float(exp - alone))


def print_summary(s: dict) -> None:
    for name in ("median", "strict"):
        print(f"\n== a 2 means: {'panel median is 2' if name == 'median' else 'all three judges say 2'}")
        print(f"{'':20s}{'n':>5s}{'q':>5s}{'chunks':>7s}{'expanded':>10s}{'alone':>8s}{'diff':>8s}   95% interval          per chunk  gain  | dilution n, diff")
        for label, r in s[name].items():
            g = r["gain"]
            if not g["n"]:
                print(f"{label:20s}{0:5d}")
                continue
            d = r.get("dilution")
            dil = f"{d['n']:3d} {d['difference']:+.2f}" if d and d["n"] else ""
            print(f"{label:20s}{g['n']:5d}{g['questions']:5d}{g['chunks']:7d}{g['expanded_is_2']:10.2f}{g['alone_is_2']:8.2f}{g['difference']:+8.2f}"
                  f"   [{g['lo']:+.2f},{g['hi']:+.2f}]   {g['per_chunk_difference']:+.2f}  {g['chunks_that_gain']:3d}/{g['chunks']:<3d} | {dil}")


# ---------------------------------------------------------------- run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="build the sample and count the calls; no LLM")
    ap.add_argument("--report", action="store_true", help="report from the saved judgments; no LLM")
    ap.add_argument("--judges", nargs="+", default=PANEL)
    a = ap.parse_args()

    config = json.loads((POOLED / "pool_config.json").read_text(encoding="utf-8"))
    chunk_version.require(config["chunks_sha"], "the E1 pool")
    chunks = read_jsonl(CHUNKS / "chunks.jsonl")
    by_id = {c["chunk_id"]: c for c in chunks}
    items = read_jsonl(POOLED / "pool.jsonl")
    e1_rows = {j: read_jsonl(POOLED / "judgments" / f"{j}.jsonl") for j in PANEL}
    e1 = panel_grades(e1_rows, items, strict=False)
    sample, left = build(items, e1, chunks)
    e1_batches = {it["id"]: {frozenset(b) for b in batches([e["chunk_id"] for e in it["pool"]], it["id"])} for it in items}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sample.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in sample), encoding="utf-8")
    (OUT / "sample_config.json").write_text(json.dumps(dict(
        chunks_sha=config["chunks_sha"], extra_tokens=EXTRA_TOKENS, top=TOP, ranked=RANKED, n_twos=N_TWOS, seed=SEED, left_out=left,
        judges=a.judges), indent=1), encoding="utf-8")
    n1 = sum(r["e1"] == 1 for r in sample)
    print(f"{len(sample)} (question, chunk) pairs: {n1} graded 1 ({sum(r['stratum'] == 'clause' and r['e1'] == 1 for r in sample)} clause, "
          f"{sum(r['stratum'] == 'later-part' and r['e1'] == 1 for r in sample)} later-part), {len(sample) - n1} graded 2; "
          f"{len({r['id'] for r in sample})} questions; left out {left}")

    (OUT / "judgments").mkdir(exist_ok=True)
    per_judge, calls = {}, 0
    for j in a.judges:
        path = OUT / "judgments" / f"{j}.jsonl"
        done = read_jsonl(path) if path.exists() else []
        todo = defaultdict(set)
        for q, cid, cond in missing(sample, done):
            todo[q, cond].add(cid)
        n_calls = sum(len(batches_of(q, ids, e1_batches)) for (q, _), ids in todo.items())
        calls += n_calls
        print(f"{j}: {len(sample) * 2 - sum(map(len, todo.values()))} of {len(sample) * 2} graded, {n_calls} calls to go")
        if not (a.dry or a.report) and n_calls:
            done += grade(j, sample, done, by_id, e1_batches)
            path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in done), encoding="utf-8")
        per_judge[j] = done
    if a.dry:
        return
    if a.report and calls:
        print("some pairs are not graded yet: run without --report")
        return
    if len(a.judges) < 3:
        print("fewer than three judges: graded and saved, but no report (a panel median needs three)")
        return
    s = summarise(sample, per_judge)
    (OUT / "summary.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    print_summary(s)


if __name__ == "__main__":
    main()
