"""Human review labels: storage, rubric, and who reviews what. The review notebook (rag/review.py) is only a screen
over this module, so another front end can use the same files.

Files, one directory per reviewer, so reviewers never write to the same file:
  rag/eval/labels/<reviewer>/answers.csv  one row per (run, question): rubric scores, failure tags, note
  rag/eval/labels/<reviewer>/chunks.csv   one row per (question, chunk): relevance 0/1/2
Chunk relevance does not depend on the run, so a later run that retrieves the same chunk for the same question
reuses the label; answer labels belong to one run's answer.

Assignment: everyone labels the shared set first (rag/eval/shared_questions.txt, drawn once); it is where agreement
between reviewers is measured. The rest is split by first come: a reviewer's queue holds the shared questions they
have not done, then the questions nobody has labelled for this run. Multi-turn sets travel together. Each reviewer
sees the unclaimed questions in their own order (a hash of their name and the question), so people working at the
same time rarely start on the same one; when they do, it only adds overlap.

Rubric and tags: docs/plans/review-rubric.md (keep the two in step).
"""

import csv
import hashlib
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path

from rag.questions import Question, dev, load

ROOT = Path(__file__).parent.parent
LABELS = ROOT / "rag" / "eval" / "labels"
SHARED = ROOT / "rag" / "eval" / "shared_questions.txt"
RUNS = ROOT / "rag" / "out" / "runs"
SHARED_N = 10
SHARED_SEED = 20261021
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

# rubric: value -> label shown to the reviewer; "" means not scored yet
SCORES = {"2": "2 ใช่", "1": "1 บางส่วน", "0": "0 ไม่ใช่"}
RUBRIC = {
    "grounded": "ทุกข้อความในคำตอบมีอยู่ในเอกสารอ้างอิง (ไม่แต่งเพิ่ม)",
    "correct": "ถูกต้องตามกฎหมายปัจจุบันเท่าที่ผู้ตรวจทราบ รวมถึงตัวเลขและปีภาษี",
    "useful": "ตอบตรงคำถามและนำไปใช้ได้จริง",
}
BEHAVIOUR = {"na": "ไม่เกี่ยว", "yes": "ทำถูก", "no": "ไม่ทำ / ทำผิด"}  # asked back, corrected, declined as needed
RELEVANCE = {"2": "2 ตอบได้", "1": "1 เกี่ยวข้อง", "0": "0 ไม่เกี่ยว"}
TAGS = {
    "retrieval_miss": "ไม่ได้ดึงเอกสารที่ควรได้",
    "one_doc": "เอกสารเดียวกินทุกช่อง",
    "outdated": "ใช้ข้อมูลปีเก่า",
    "misread": "อ่านเอกสารผิด / ผสมข้อมูลผิดบริบท",
    "unsupported": "แต่งข้อมูลที่ไม่มีในเอกสาร",
    "calc_error": "คำนวณผิด",
    "needless_refusal": "ปฏิเสธ/ถามกลับโดยไม่จำเป็น",
    "bad_citation": "อ้างอิงผิดเอกสาร",
    "language": "ภาษาไม่เป็นธรรมชาติ / อ่านยาก",
    "other": "อื่น ๆ (เขียนในหมายเหตุ)",
}

ANSWER_FIELDS = ["run_id", "question_id", "grounded", "correct", "useful", "behaviour", "tags", "note", "labelled_at"]
CHUNK_FIELDS = ["question_id", "chunk_id", "relevance", "note", "labelled_at"]


def check_name(name: str) -> str:
    name = name.strip().lower()
    if not NAME.match(name):
        raise ValueError("reviewer name: lowercase letters, digits, - or _, up to 32 characters")
    return name


def reviewers() -> list[str]:
    return sorted(p.name for p in LABELS.iterdir() if p.is_dir()) if LABELS.exists() else []


def _read(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    """Atomic rewrite: a temporary file replaces the old one, so a failure leaves the old file intact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    try:
        with tmp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def answer_labels(reviewer: str) -> dict[tuple[str, str], dict]:
    return {(r["run_id"], r["question_id"]): r for r in _read(LABELS / reviewer / "answers.csv")}


def chunk_labels(reviewer: str) -> dict[tuple[str, str], dict]:
    return {(r["question_id"], r["chunk_id"]): r for r in _read(LABELS / reviewer / "chunks.csv")}


def save(reviewer: str, run_id: str, question_id: str, answer: dict, chunks: dict[str, dict]) -> None:
    """Upsert one question's labels: the answer label and one row per chunk (chunk_id -> {relevance, note})."""
    reviewer = check_name(reviewer)
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    a = answer_labels(reviewer)
    a[(run_id, question_id)] = {f: "" for f in ANSWER_FIELDS} | {k: v for k, v in answer.items() if k in ANSWER_FIELDS} | dict(
        run_id=run_id, question_id=question_id, labelled_at=now)
    _write(LABELS / reviewer / "answers.csv", ANSWER_FIELDS, sorted(a.values(), key=lambda r: (r["run_id"], r["question_id"])))
    c = chunk_labels(reviewer)
    for chunk_id, v in chunks.items():
        c[(question_id, chunk_id)] = dict(question_id=question_id, chunk_id=chunk_id, relevance=v.get("relevance", ""),
                                          note=v.get("note", ""), labelled_at=now)
    _write(LABELS / reviewer / "chunks.csv", CHUNK_FIELDS, sorted(c.values(), key=lambda r: (r["question_id"], r["chunk_id"])))


def is_complete(label: dict | None) -> bool:
    return bool(label) and all(label[k] for k in ("grounded", "correct", "useful", "behaviour"))


# ---------------------------------------------------------------- assignment


def draw_shared(qs: list[Question], seed: int = SHARED_SEED) -> list[str]:
    """SHARED_N dev questions everyone labels: no multi-turn (a set is 3 questions), at least one behavioural one."""
    rng = random.Random(seed)
    pool = [q for q in dev(qs) if q.kind != "multi_turn"]
    behavioural = [q for q in pool if q.kind in ("ask_back", "misconception", "out_of_scope")]
    pick = rng.sample(behavioural, 1) + rng.sample([q for q in pool if q.kind == "normal"], SHARED_N - 1)
    order = {q.id: i for i, q in enumerate(qs)}
    return sorted((q.id for q in pick), key=order.__getitem__)


def shared_ids() -> list[str]:
    if not SHARED.exists():
        raise SystemExit(f"{SHARED} missing: run `python -m rag.labels --new-shared`")
    return [ln.strip() for ln in SHARED.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]


@dataclass
class Item:
    """One question to review in a run. Multi-turn sets are reviewed turn by turn but queued together."""
    question_id: str
    shared: bool
    done_by: list[str]  # reviewers with a complete answer label for this run


def queue(reviewer: str, run_id: str, question_ids: list[str], shared: list[str]) -> tuple[list[Item], list[Item]]:
    """(to do, all) for a reviewer in a run; `all` is in file order. To do: the shared questions they have not
    finished (file order), then questions nobody has finished in the reviewer's own order; a multi-turn set another
    reviewer has started is left to them, and a set's turns stay together and in order."""
    done = {r: {q for (rid, q), lab in answer_labels(r).items() if rid == run_id and is_complete(lab)} for r in reviewers()}
    set_of = {q.id: q.set for q in load()}
    items = [Item(q, q in shared, sorted(r for r, d in done.items() if q in d)) for q in question_ids]
    mine = done.get(reviewer, set())
    others_sets = {set_of[i.question_id] for i in items if set_of[i.question_id] and set(i.done_by) - {reviewer}}
    my_sets = {set_of[q] for q in mine if set_of.get(q)}
    todo = [i for i in items if i.question_id not in mine and (
        i.shared or (not i.done_by and (set_of[i.question_id] is None or set_of[i.question_id] not in others_sets - my_sets)))]
    position = {q: n for n, q in enumerate(question_ids)}

    def order(i: Item) -> tuple:
        if i.shared:
            return (0, "", position[i.question_id])
        unit = set_of[i.question_id] or i.question_id  # a multi-turn set sorts as one unit
        return (1, hashlib.sha256(f"{reviewer}:{run_id}:{unit}".encode()).hexdigest(), position[i.question_id])

    return sorted(todo, key=order), items


def agreement(run_id: str, question_ids: list[str]) -> dict[str, tuple[int, float]]:
    """Exact agreement between reviewers on the given questions: field -> (number of reviewer pairs compared,
    share of pairs with the same value). Chunk relevance is compared per (question, chunk)."""
    from itertools import combinations

    revs = reviewers()
    ans = {r: answer_labels(r) for r in revs}
    out = {}
    for f in ("grounded", "correct", "useful", "behaviour"):
        pairs = [(ans[a].get((run_id, q), {}).get(f), ans[b].get((run_id, q), {}).get(f))
                 for q in question_ids for a, b in combinations(revs, 2)]
        pairs = [(x, y) for x, y in pairs if x and y]
        out[f] = (len(pairs), sum(x == y for x, y in pairs) / len(pairs) if pairs else float("nan"))
    ch = {r: chunk_labels(r) for r in revs}
    keys = {k for r in revs for k in ch[r] if k[0] in question_ids}
    pairs = [(ch[a][k]["relevance"], ch[b][k]["relevance"]) for k in keys for a, b in combinations(revs, 2) if k in ch[a] and k in ch[b]]
    pairs = [(x, y) for x, y in pairs if x and y]
    out["relevance"] = (len(pairs), sum(x == y for x, y in pairs) / len(pairs) if pairs else float("nan"))
    return out


def runs() -> list[str]:
    return sorted((p.name for p in RUNS.iterdir() if (p / "answers.jsonl").exists()), reverse=True) if RUNS.exists() else []


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--new-shared", action="store_true", help="draw the shared set and write it (refuses to overwrite)")
    a = ap.parse_args()
    if a.new_shared:
        if SHARED.exists():
            raise SystemExit(f"{SHARED} exists; delete it first (agreement on the old set is then lost)")
        ids = draw_shared(load())
        SHARED.write_text(f"# shared review set drawn by rag.labels.draw_shared(seed={SHARED_SEED}) from the dev subset\n"
                          + "\n".join(ids) + "\n", encoding="utf-8")
        print(f"shared set: {len(ids)} questions -> {SHARED}")
    print("reviewers:", reviewers() or "none yet")


if __name__ == "__main__":
    main()
