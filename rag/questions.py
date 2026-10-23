"""The evaluation question set (rag/eval/tax-questions-pass-1.csv): parsing, question kinds, multi-turn history, dev subset.

Kinds, from the category column:
- multi_turn    คำถามหลายรอบ: sets of turns tagged "[รอบ n: ชุด X]"; the tag is stripped from the text
- ask_back      โจทย์ข้อมูลไม่ครบ: the right answer asks for the missing facts
- misconception ความเข้าใจผิด: the right answer corrects the premise
- out_of_scope  นอกขอบเขต: the right answer declines or says the corpus does not cover it
- normal        everything else
Behavioural kinds (ask_back, misconception, out_of_scope) are scored on behaviour, not on retrieval.
KIND_OVERRIDES corrects the kind of a question whose category turned out wrong; the CSV keeps its category.

The dev subset is used while iterating; it is drawn once and saved, so every run uses the same questions:
2 per category (seeded), the out-of-scope question, and one whole multi-turn set.
The ablation subset (E3, E4) is drawn once from the questions not in dev: 6 per content category (seeded), every
multi-turn set and every behavioural question. See docs/plans/ablation-plan-retrieval-context-generator.md.

Run: uv run python -m rag.questions [--new-dev] [--new-ablation]
"""

import argparse
import csv
import random
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent
QUESTIONS = ROOT / "rag" / "eval" / "tax-questions-pass-1.csv"
DEV = ROOT / "rag" / "eval" / "dev_questions.txt"
ABLATION = ROOT / "rag" / "eval" / "ablation_questions.txt"

KINDS = {"คำถามหลายรอบ": "multi_turn", "โจทย์ข้อมูลไม่ครบ": "ask_back", "ความเข้าใจผิด": "misconception", "นอกขอบเขต": "out_of_scope"}
BEHAVIOURAL = {"ask_back", "misconception", "out_of_scope"}
# Q0369 (ล็อตเตอรี่): filed as out of scope, but มาตรา 42(11) and the ภ.ง.ด.94 FAQ answer it (government lottery
# prizes are exempt). Retrieval misses it because no chunk says ล็อตเตอรี่. Proposed 2026-10-21 for the reviewers
# to confirm (review-calibration-1.th.md, item 4); a normal question and a vocabulary-mismatch example.
KIND_OVERRIDES = {"Q0369": "normal"}
TURN_TAG = re.compile(r"\s*\[รอบ\s*(\d+)\s*:\s*ชุด\s*(\w+)\]\s*$")
DEV_PER_CATEGORY = 2
DEV_SEED = 20261020
ABLATION_PER_CATEGORY = 6
ABLATION_SEED = 20261023


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    difficulty: str | None
    text: str
    kind: str
    set: str | None = None
    turn: int | None = None


def parse(row: dict) -> Question:
    text, set_, turn = row["คำถาม"].strip(), None, None
    if m := TURN_TAG.search(text):
        text, turn, set_ = text[: m.start()].strip(), int(m.group(1)), m.group(2)
    kind = KIND_OVERRIDES.get(row["ID"], KINDS.get(row["หมวด"], "normal"))
    if (kind == "multi_turn") != (set_ is not None):
        raise ValueError(f"{row['ID']}: turn tag and category disagree ({row['หมวด']!r}, set {set_!r})")
    return Question(id=row["ID"], category=row["หมวด"], difficulty=row["ระดับความยาก"] or None, text=text, kind=kind,
                    set=set_, turn=turn)


def load(path: Path = QUESTIONS) -> list[Question]:
    qs = [parse(r) for r in csv.DictReader(path.open(encoding="utf-8-sig"))]
    if len({q.id for q in qs}) != len(qs):
        raise ValueError("question ids must be unique")
    for s in {q.set for q in qs if q.set}:
        turns = [q.turn for q in qs if q.set == s]
        if turns != list(range(1, len(turns) + 1)):
            raise ValueError(f"set {s}: turns {turns} are not 1..n in file order")
    return qs


def history(q: Question, qs: list[Question]) -> list[Question]:
    """Earlier turns of the same multi-turn set, in order; empty for single questions."""
    if q.set is None:
        return []
    return sorted((p for p in qs if p.set == q.set and p.turn < q.turn), key=lambda p: p.turn)


def draw_dev(qs: list[Question], seed: int = DEV_SEED) -> list[str]:
    rng = random.Random(seed)
    ids = []
    # by category, not kind, so a kind override does not change the draw
    for cat in sorted({q.category for q in qs if KINDS.get(q.category) not in ("multi_turn", "out_of_scope")}):
        ids += rng.sample(sorted(q.id for q in qs if q.category == cat), DEV_PER_CATEGORY)
    ids += [q.id for q in qs if KINDS.get(q.category) == "out_of_scope"]
    one_set = rng.choice(sorted({q.set for q in qs if q.set}))
    ids += [q.id for q in qs if q.set == one_set]
    order = {q.id: i for i, q in enumerate(qs)}
    return sorted(ids, key=order.__getitem__)


def draw_ablation(qs: list[Question], dev_ids: set[str], seed: int = ABLATION_SEED) -> list[str]:
    """Content questions by category, as in draw_dev; multi-turn sets and behavioural questions are few, so all are kept
    (whole sets: dev holds whole sets, so a set is either all in dev or not at all)."""
    rng = random.Random(seed)
    pool = [q for q in qs if q.id not in dev_ids]
    ids = []
    for cat in sorted({q.category for q in pool if q.kind == "normal"}):
        ids += rng.sample(sorted(q.id for q in pool if q.category == cat), ABLATION_PER_CATEGORY)
    ids += [q.id for q in pool if q.kind == "multi_turn" or q.kind in BEHAVIOURAL]
    order = {q.id: i for i, q in enumerate(qs)}
    return sorted(ids, key=order.__getitem__)


def _subset(path: Path, flag: str, qs: list[Question]) -> list[Question]:
    if not path.exists():
        raise SystemExit(f"{path} missing: run `python -m rag.questions {flag}`")
    ids = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    by_id = {q.id: q for q in qs}
    return [by_id[i] for i in ids]


def dev(qs: list[Question]) -> list[Question]:
    return _subset(DEV, "--new-dev", qs)


def ablation(qs: list[Question]) -> list[Question]:
    return _subset(ABLATION, "--new-ablation", qs)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-dev", action="store_true", help="draw the dev subset and write it (refuses to overwrite)")
    ap.add_argument("--new-ablation", action="store_true", help="draw the ablation subset and write it (refuses to overwrite)")
    a = ap.parse_args()
    qs = load()
    print(f"{len(qs)} questions, {len({q.category for q in qs})} categories")
    print("kinds:", dict(Counter(q.kind for q in qs)))
    print("difficulty:", dict(Counter(q.difficulty for q in qs)))
    print("multi-turn sets:", {s: sum(q.set == s for q in qs) for s in sorted({q.set for q in qs if q.set})})
    if a.new_dev:
        if DEV.exists():
            raise SystemExit(f"{DEV} exists; delete it first to draw a new subset (earlier dev runs then stop being comparable)")
        ids = draw_dev(qs)
        DEV.parent.mkdir(parents=True, exist_ok=True)
        DEV.write_text(f"# dev subset drawn by rag.questions.draw_dev(seed={DEV_SEED}) from {QUESTIONS.name}\n" + "\n".join(ids) + "\n",
                       encoding="utf-8")
        print(f"dev subset: {len(ids)} questions -> {DEV}")
    if a.new_ablation:
        if ABLATION.exists():
            raise SystemExit(f"{ABLATION} exists; delete it first to draw a new subset (earlier E3/E4 runs then stop being comparable)")
        ids = draw_ablation(qs, {q.id for q in dev(qs)})
        ABLATION.write_text(f"# ablation subset drawn by rag.questions.draw_ablation(seed={ABLATION_SEED}) from {QUESTIONS.name}, "
                            f"dev excluded\n" + "\n".join(ids) + "\n", encoding="utf-8")
        print(f"ablation subset: {len(ids)} questions -> {ABLATION}")


if __name__ == "__main__":
    main()
