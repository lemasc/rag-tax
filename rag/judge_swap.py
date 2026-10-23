"""Judge swap check: can gpt-6-luna take gpt-6-sol's seat in the panel, from E1b on?

luna grades the whole E1 pool (rag.pooled --judges judge-luna-or); this compares it with sol on the same pairs, at two levels.
The rules were fixed before luna's grades existed (plan: "Judge swap"):
  pairs    luna's exact agreement with each of sol, haiku and DeepSeek is at least MIN_AGREE (the panel agrees 76-79% within
           itself), 2-point gaps are under MAX_GAP2, and luna's share of 2s is at most sol's plus MAX_MORE_TWOS.
  results  E1 recomputed with the new panel (luna, haiku, DeepSeek; a 2 is the median) ranks the three modes in the same
           order on every metric, and each new difference between modes lies inside the old one's 95% interval.
Only questions luna graded in full are used, for both panels, so a run cut off part way is still a fair comparison.

Output: rag/out/pooled/judge_swap.json
Run   : uv run python -m rag.judge_swap
"""

import json
from itertools import combinations

from rag.chunk import read_jsonl
from rag.pooled import MODES, OUT, PANEL, judge_grades, summarise

NEW = "judge-luna-or"
OLD = "judge-sol-or"
NEW_PANEL = [NEW, "judge-haiku", "judge-deepseek"]
MIN_AGREE = 0.72
MAX_GAP2 = 0.02
MAX_MORE_TWOS = 0.05
DIFFERENCES = ("hybrid-sparse", "hybrid-dense", "sparse-dense")


def fully_graded(items: list[dict], grades: dict[tuple[str, str], int]) -> list[dict]:
    return [it for it in items if all((it["id"], e["chunk_id"]) in grades for e in it["pool"])]


def pair_check(by_judge: dict[str, dict[tuple[str, str], int]], keys: list[tuple[str, str]]) -> dict:
    """Agreement of every two judges on `keys`, each judge's share of 2s, and whether luna passes."""
    agree = {}
    for a, b in combinations(by_judge, 2):
        same = sum(by_judge[a][k] == by_judge[b][k] for k in keys) / len(keys)
        gap2 = sum(abs(by_judge[a][k] - by_judge[b][k]) == 2 for k in keys) / len(keys)
        agree[f"{a} vs {b}"] = dict(exact=same, gap2=gap2)
    twos = {j: sum(g[k] == 2 for k in keys) / len(keys) for j, g in by_judge.items()}
    mine = {p: v for p, v in agree.items() if NEW in p}
    ok = all(v["exact"] >= MIN_AGREE and v["gap2"] < MAX_GAP2 for v in mine.values()) and twos[NEW] <= twos[OLD] + MAX_MORE_TWOS
    return dict(n_pairs=len(keys), agreement=agree, share_of_2s=twos, passes=ok)


def result_check(old: dict, new: dict) -> dict:
    """Mode order per metric and each new difference against the old interval, a 2 being the median."""
    o, n = old["median"]["all"], new["median"]["all"]
    fields = list(o["modes"]["dense"])
    order = {f: dict(old=sorted(MODES, key=lambda m: -o["modes"][m][f]), new=sorted(MODES, key=lambda m: -n["modes"][m][f])) for f in fields}
    inside = {}
    for d in DIFFERENCES:
        for f in fields:
            od, nd = o["differences"][d][f], n["differences"][d][f]
            inside[f"{d} {f}"] = dict(old=od["mean"], lo=od["lo"], hi=od["hi"], new=nd["mean"], inside=od["lo"] <= nd["mean"] <= od["hi"])
    ok = all(v["old"] == v["new"] for v in order.values()) and all(v["inside"] for v in inside.values())
    return dict(order=order, differences=inside, passes=ok)


def verdict(pairs_ok: bool, results_ok: bool) -> str:
    if pairs_ok and results_ok:
        return "swap: luna, haiku and DeepSeek grade E1b and E3; E1 is reported under both panels"
    if pairs_ok:
        return "swap, but E1's results move with the judge: report E1 under both panels and state only what holds under both"
    return "no swap: E1b keeps sol; E3 runs with haiku and DeepSeek, a 2 needing both, and sol scores a sample"


def main() -> None:
    items = read_jsonl(OUT / "pool.jsonl")
    per_judge = {j: read_jsonl(OUT / "judgments" / f"{j}.jsonl") for j in [*PANEL, NEW]}
    by_judge = judge_grades(per_judge, items)
    sub = fully_graded(items, by_judge[NEW])
    if not sub:
        raise SystemExit(f"{NEW} has not graded any question in full yet")
    keys = [(it["id"], e["chunk_id"]) for it in sub for e in it["pool"]]
    pairs = pair_check(by_judge, keys)
    old, new = summarise(sub, {j: per_judge[j] for j in PANEL}), summarise(sub, {j: per_judge[j] for j in NEW_PANEL})
    results = result_check(old, new)
    out = dict(questions=len(sub), of=len(items), rules=dict(min_agree=MIN_AGREE, max_gap2=MAX_GAP2, max_more_twos=MAX_MORE_TWOS),
               pairs=pairs, results=results, verdict=verdict(pairs["passes"], results["passes"]),
               modes=dict(old={g: old[g]["all"]["modes"] for g in old}, new={g: new[g]["all"]["modes"] for g in new}))
    (OUT / "judge_swap.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{len(sub)} of {len(items)} questions graded in full by {NEW}, {len(keys)} pairs")
    for p, v in pairs["agreement"].items():
        print(f"  {p:36s} exact {v['exact']:.3f}  2-point gaps {v['gap2']:.3f}")
    print("  share of 2s: " + ", ".join(f"{j} {v:.3f}" for j, v in pairs["share_of_2s"].items()))
    print(f"pairs pass: {pairs['passes']}")
    for f, v in results["order"].items():
        print(f"  {f:11s} old {' > '.join(v['old']):24s} new {' > '.join(v['new'])}")
    for k, v in results["differences"].items():
        print(f"  {k:26s} old {v['old']:+.3f} [{v['lo']:+.3f},{v['hi']:+.3f}]  new {v['new']:+.3f}{'' if v['inside'] else '  OUTSIDE'}")
    print(f"results pass: {results['passes']}\nverdict: {out['verdict']}")


if __name__ == "__main__":
    main()
