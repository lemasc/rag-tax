"""E3 end-to-end context ablation: the panel's answer scores per variant, on the questions every variant has.

Each variant is a run scored by the panel (rag.evaluate per judge, then rag.panel). A question some judge could not score
in some variant is dropped from every variant (rag.panel --drop-unscored lists it), so all rows cover the same questions.
Variants not scored yet are skipped and named.

Rows per variant (means over answers; rubric items 0-2, faithfulness and answer relevance 0-1):
  all          grounded, correct, useful over every question
  content      normal and multi-turn: also faithfulness and answer relevance
  behavioural  ask-back and misconception: rubric, and how many answers showed the behaviour
Faithfulness and answer relevance are not pooled over behavioural questions (an ask-back has few claims and reads as
noncommittal). A variant without retrieval has no faithfulness, and its grounded means "supported by the reference run's
sources"; it is shown in parentheses.

Output: rag/out/e3/table.md, rag/out/e3/table.json
Run   : uv run python -m rag.e3
"""

import json
from pathlib import Path

from rag import evaluate
from rag.chunk import OUT, read_jsonl
from rag.labels import RUNS
from rag.panel import PANEL
from rag.questions import BEHAVIOURAL

VARIANTS = [  # (label, run id), in table order
    ("no retrieval", "20261023-ablation-typhoon-none-n1-sr3"),
    ("dense k = 5 (baseline)", "20261023-ablation-typhoon-dense-k5-v1-sr3"),
    ("dense k = 10", "20261023-ablation-typhoon-dense-k10-v1-sr3"),
]
E3 = OUT / "e3"
ITEMS = ("grounded", "correct", "useful")


def panel_scores(run: str) -> tuple[list[dict], dict] | None:
    d = evaluate.out_dir(RUNS / run, PANEL)
    if not (d / "scores.jsonl").exists():
        return None
    return read_jsonl(d / "scores.jsonl"), json.loads((d / "scores_config.json").read_text(encoding="utf-8"))


def no_sources(run: str) -> bool:
    return not any(r["hits"] for r in read_jsonl(RUNS / run / "answers.jsonl"))


def group(rows: list[dict], content: bool) -> dict:
    out = dict(n=len(rows)) | {f: evaluate.mean(r["rubric"][f] for r in rows) for f in ITEMS}
    if content:
        out |= dict(faithfulness=evaluate.mean(r["faithfulness"]["score"] for r in rows),
                    relevance=evaluate.mean(r["relevance"]["score"] for r in rows))
    else:
        out["behaviour_yes"] = sum(r["rubric"]["behaviour"] == "yes" for r in rows)
    return out


def table(variants=VARIANTS) -> dict:
    scored = {label: (run, s) for label, run in variants if (s := panel_scores(run))}
    skipped = [label for label, _ in variants if label not in scored]
    all_ids = set().union(*({r["id"] for r in s[0]} for _, s in scored.values()))
    common = set.intersection(*({r["id"] for r in s[0]} for _, s in scored.values()))
    rows = {}
    for label, (run, (scores, _)) in scored.items():
        rs = [r for r in scores if r["id"] in common]
        rows[label] = dict(run=run, no_sources=no_sources(run),
                           all=group(rs, content=False) | dict(behaviour_yes=None),
                           content=group([r for r in rs if r["kind"] not in BEHAVIOURAL], content=True),
                           behavioural=group([r for r in rs if r["kind"] in BEHAVIOURAL], content=False))
    dropped = sorted(all_ids - common | {q for _, (_, cfg) in scored.values() for q in cfg.get("dropped", [])})
    return dict(n_common=len(common), dropped=dropped, skipped=skipped, rows=rows)


def fmt(x, paren: bool = False) -> str:
    if x is None:
        return "–"
    s = f"{x:.2f}"
    return f"({s})" if paren else s


def markdown(t: dict) -> str:
    lines = ["| Variant | Group | n | Grounded | Correct | Useful | Faithfulness | Answer relevance | Behaviour shown |",
             "|---|---|---|---|---|---|---|---|---|"]
    for label, v in t["rows"].items():
        ns = v["no_sources"]
        for name in ("all", "content", "behavioural"):
            g = v[name]
            beh = "" if g.get("behaviour_yes") is None else f"{g['behaviour_yes']} of {g['n']}"
            lines.append(f"| {label if name == 'all' else ''} | {name} | {g['n']} | {fmt(g['grounded'], ns)} | {fmt(g['correct'])} | "
                         f"{fmt(g['useful'])} | {fmt(g.get('faithfulness')) if name == 'content' else ''} | "
                         f"{fmt(g.get('relevance')) if name == 'content' else ''} | {beh} |")
    notes = [f"{t['n_common']} questions common to every scored variant."]
    if t["dropped"]:
        notes.append(f"Dropped (some judge could not score them in some variant): {', '.join(t['dropped'])}.")
    if t["skipped"]:
        notes.append(f"Not scored yet: {', '.join(t['skipped'])}.")
    if any(v["no_sources"] for v in t["rows"].values()):
        notes.append("Grounded in parentheses: a run without retrieval, judged against the reference run's sources.")
    return "\n".join(lines) + "\n\n" + " ".join(notes) + "\n"


def main() -> None:
    t = table()
    E3.mkdir(parents=True, exist_ok=True)
    (E3 / "table.json").write_text(json.dumps(t, ensure_ascii=False, indent=1), encoding="utf-8")
    md = markdown(t)
    (E3 / "table.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"-> {E3}/table.md")


if __name__ == "__main__":
    main()
