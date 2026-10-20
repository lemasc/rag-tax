"""The evaluation question set (rag/eval/tax-questions-pass-1.csv): parsing, question kinds, multi-turn history, dev subset.

Kinds, from the category column:
- multi_turn    คำถามหลายรอบ: sets of turns tagged "[รอบ n: ชุด X]"; the tag is stripped from the text
- ask_back      โจทย์ข้อมูลไม่ครบ: the right answer asks for the missing facts
- misconception ความเข้าใจผิด: the right answer corrects the premise
- out_of_scope  นอกขอบเขต: the right answer declines or says the corpus does not cover it
- normal        everything else
Behavioural kinds (ask_back, misconception, out_of_scope) are scored on behaviour, not on retrieval.

The dev subset is used while iterating; it is drawn once and saved, so every run uses the same questions:
2 per category (seeded), the out-of-scope question, and one whole multi-turn set.

Run: uv run python -m rag.questions [--new-dev]
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

KINDS = {"คำถามหลายรอบ": "multi_turn", "โจทย์ข้อมูลไม่ครบ": "ask_back", "ความเข้าใจผิด": "misconception", "นอกขอบเขต": "out_of_scope"}
BEHAVIOURAL = {"ask_back", "misconception", "out_of_scope"}
TURN_TAG = re.compile(r"\s*\[รอบ\s*(\d+)\s*:\s*ชุด\s*(\w+)\]\s*$")
DEV_PER_CATEGORY = 2
DEV_SEED = 20261020


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
    kind = KINDS.get(row["หมวด"], "normal")
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
    for cat in sorted({q.category for q in qs if q.kind not in ("multi_turn", "out_of_scope")}):
        ids += rng.sample(sorted(q.id for q in qs if q.category == cat), DEV_PER_CATEGORY)
    ids += [q.id for q in qs if q.kind == "out_of_scope"]
    one_set = rng.choice(sorted({q.set for q in qs if q.set}))
    ids += [q.id for q in qs if q.set == one_set]
    order = {q.id: i for i, q in enumerate(qs)}
    return sorted(ids, key=order.__getitem__)


def dev(qs: list[Question]) -> list[Question]:
    if not DEV.exists():
        raise SystemExit(f"{DEV} missing: run `python -m rag.questions --new-dev`")
    ids = [ln.strip() for ln in DEV.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    by_id = {q.id: q for q in qs}
    return [by_id[i] for i in ids]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new-dev", action="store_true", help="draw the dev subset and write it (refuses to overwrite)")
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


if __name__ == "__main__":
    main()
