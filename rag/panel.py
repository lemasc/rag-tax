"""A panel of judges: combine the scores several judges gave the same run into one set of scores.

No LLM calls and no embedder: it reads each judge's saved scores (rag.evaluate writes them), so adding or changing
the aggregation costs nothing. The result is written like a judge's own scores, to runs/<id>/judges/panel/, so
`python -m rag.evaluate --compare --judge panel` compares it with the human labels.

Aggregation, per answer:
- grounded, correct, useful and each source's relevance: the median (the lower middle for an even number of judges);
- behaviour: the majority; a tie goes to the more severe value (no, then yes, then na);
- tags: those a majority of the judges chose;
- faithfulness and answer relevance: the mean of the judges' scores.
An answer is `contested` when two judges differ by two points on grounded, correct or useful; those are the ones a
person should look at. Every judge's own rubric stays in the record under `judges`.

Run: uv run python -m rag.panel --judges judge judge-haiku judge-deepseek
"""

import argparse
import json
import time
from collections import Counter

from rag import evaluate

DEFAULT_PANEL = ["judge", "judge-haiku", "judge-deepseek"]
PANEL = "panel"
ITEMS = ("grounded", "correct", "useful")
SEVERITY = {"no": 0, "yes": 1, "na": 2}  # lower sorts first on a tie in the behaviour vote


def median(xs: list[int]) -> int:
    xs = sorted(xs)
    return xs[(len(xs) - 1) // 2]


def majority(xs: list[str]) -> str:
    top = Counter(xs).most_common()
    return min((v for v, n in top if n == top[0][1]), key=SEVERITY.__getitem__)


def aggregate(per_judge: dict[str, dict]) -> dict:
    """One answer's panel record from {judge name: that judge's score record for the answer}."""
    recs = list(per_judge.values())
    rubs = [r["rubric"] for r in recs]
    n = len(rubs)
    out = {f: median([r[f] for r in rubs]) for f in ITEMS}
    out["behaviour"] = majority([r["behaviour"] for r in rubs])
    out["relevance"] = {k: median([r["relevance"][k] for r in rubs]) for k in rubs[0]["relevance"]}
    tags = Counter(t for r in rubs for t in r["tags"])
    out["tags"] = sorted(t for t, c in tags.items() if c > n / 2)
    out["note"] = ""
    spread = {f: max(r[f] for r in rubs) - min(r[f] for r in rubs) for f in ITEMS}
    first = recs[0]
    return dict(
        id=first["id"], category=first["category"], kind=first["kind"],
        faithfulness=dict(score=evaluate.mean(r["faithfulness"]["score"] for r in recs)),
        relevance=dict(score=evaluate.mean(r["relevance"]["score"] for r in recs)),
        rubric=out, spread=spread, contested=any(s >= 2 for s in spread.values()),
        judges={name: r["rubric"] for name, r in per_judge.items()},
        judge_tokens=dict(prompt=sum(r["judge_tokens"]["prompt"] for r in recs),
                          completion=sum(r["judge_tokens"]["completion"] for r in recs)),
    )


def load(path, judge: str) -> tuple[list[dict], dict]:
    d = evaluate.out_dir(path, judge)
    if not (d / "scores.jsonl").exists():
        raise SystemExit(f"{judge}: no scores in {d}; run `python -m rag.evaluate --judge {judge}` first")
    scores = [json.loads(ln) for ln in (d / "scores.jsonl").read_text(encoding="utf-8").splitlines()]
    return scores, json.loads((d / "scores_config.json").read_text(encoding="utf-8"))


def combine(path, judges: list[str]) -> list[dict]:
    if len(judges) < 3:
        raise SystemExit("a panel needs at least three judges, or the median is just one of them")
    loaded = {j: load(path, j) for j in judges}
    versions = {j: cfg["judge_version"] for j, (_, cfg) in loaded.items()}
    if len(set(versions.values())) > 1:
        raise SystemExit(f"judges were scored under different rubric versions: {versions}")
    by_judge = {j: {s["id"]: s for s in scores} for j, (scores, _) in loaded.items()}
    ids = [s["id"] for s in loaded[judges[0]][0]]
    missing = {j: sorted(set(ids) ^ set(by_id)) for j, by_id in by_judge.items() if set(ids) != set(by_id)}
    if missing:
        raise SystemExit(f"judges scored different answers: {missing}")
    scores = [aggregate({j: by_judge[j][q] for j in judges}) for q in ids]

    out = evaluate.out_dir(path, PANEL)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scores.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in scores), encoding="utf-8")
    (out / "scores_summary.json").write_text(json.dumps(evaluate.summarise(scores), ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "scores_config.json").write_text(json.dumps(dict(
        run_id=path.name, combined=time.strftime("%Y-%m-%dT%H:%M:%S%z"), judge_version=versions[judges[0]],
        judges={j: dict(model=cfg["judge"]["model"], base_url=cfg["judge"]["base_url"], params=cfg["judge"]["params"],
                        scored=cfg["scored"]) for j, (_, cfg) in loaded.items()},
        aggregation="median of grounded/correct/useful/relevance, majority of behaviour and tags, mean of faithfulness",
        n_scored=len(scores), n_contested=sum(s["contested"] for s in scores),
    ), ensure_ascii=False, indent=1), encoding="utf-8")
    return scores


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="run id under rag/out/runs (default: the newest)")
    ap.add_argument("--judges", nargs="+", default=DEFAULT_PANEL, help="judge profiles, each already scored with rag.evaluate")
    a = ap.parse_args()
    path = evaluate.run_dir(a.run)
    scores = combine(path, a.judges)
    evaluate.print_summary(evaluate.summarise(scores))
    contested = [s for s in scores if s["contested"]]
    print(f"\n{len(contested)} of {len(scores)} answers contested (two judges two points apart):")
    for s in contested:
        print(f"  {s['id']} {s['kind']:13s} " + "  ".join(f"{f} {s['spread'][f]}" for f in ITEMS if s["spread"][f] >= 2))
    print(f"panel of {', '.join(a.judges)} -> {evaluate.out_dir(path, PANEL)}/scores.jsonl")


if __name__ == "__main__":
    main()
