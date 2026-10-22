"""Find near-duplicate units across the clean corpus and say what kind of overlap each pair is.

Text that repeats is not always a duplicate to drop. A pair falls in one of these cases, and only the first is settled by
dropping a unit (data/unit_decisions.csv):
- guide_copy: the same section in two filling guides (ภ.ง.ด.90/91/94 print the same instructions); Ins90 is kept.
- legal_version: two instruments where one amends or repeals the other (data/legal_relations.csv): both stay, the build
  marks the older one `amended_by`.
- legal_shared: two instruments with the same clauses and no relation between them, parallel rules (ประกาศ 165/166/167
  on housing-loan interest) or boilerplate (the commencement มาตรา of every พ.ร.ฎ.): both stay.
- quotation: a guide, FAQ or article quoting a legal clause, or each other across sources: both stay, they differ in
  authority and context.
- same_doc: repeats inside one document (worked examples, a table printed twice).
- other: two explainer units (FAQ, article, page, image) that overlap.

The comparison is character 6-grams of the text without whitespace or markup. A pair is listed when its Jaccard similarity
is at least JACCARD or the smaller text is at least CONTAINMENT inside the larger one. Documents without units are
compared whole.

Input : data/clean/{documents,units}.jsonl, data/legal_relations.csv, data/unit_decisions.csv
Output: data/dup_candidates.csv  (case, a, b, doc_a, doc_b, jaccard, containment, exact, decision)
Run   : uv run python -m crawler.dups
"""

import csv
import json
import re
import zlib
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path("data")
GUIDE_KIND = "คู่มือกรอกแบบ"
SHINGLE = 6
MIN_SHINGLES = 40  # shorter texts (a heading, a one-line item) match everything that quotes them
JACCARD = 0.5
CONTAINMENT = 0.8
COMMON = 200  # a shingle in more texts than this is boilerplate; it does not propose pairs (scores still count it)
FIELDS = ["case", "a", "b", "doc_a", "doc_b", "jaccard", "containment", "exact", "decision"]


def skeleton(text: str) -> str:
    """Text without whitespace, markdown markers or HTML tags: OCR and HTML differ in all three."""
    return re.sub(r"<[^>]+>|[\s|*#]+", "", text)


def shingles(text: str) -> set[int]:
    t = skeleton(text)
    return {zlib.crc32(t[i : i + SHINGLE].encode()) for i in range(len(t) - SHINGLE + 1)}


def items(docs: list[dict], units: list[dict]) -> list[dict]:
    """The included units, and the included documents that have none, as {id, doc_id, family, text}."""
    by_id = {d["doc_id"]: d for d in docs}

    def family(d: dict) -> str:
        return "guide" if d["kind"] == GUIDE_KIND else "legal" if d["source"] == "legal" else "explainer"

    out = [dict(id=u["unit_id"], doc_id=u["doc_id"], family=family(by_id[u["doc_id"]]), text=u["text"])
           for u in units if u["include"] and by_id[u["doc_id"]]["include"]]
    with_units = {u["doc_id"] for u in units}
    out += [dict(id=d["doc_id"], doc_id=d["doc_id"], family=family(d), text=d["text"])
            for d in docs if d["include"] and d["doc_id"] not in with_units]
    return out


def pairs(rows: list[dict]) -> list[tuple[int, int, float, float]]:
    """(i, j, jaccard, containment) for every pair over the thresholds. Candidates come from shared shingles that are not
    COMMON, then the exact scores are computed on the full sets."""
    sets = [shingles(r["text"]) for r in rows]
    postings: dict[int, list[int]] = defaultdict(list)
    for i, s in enumerate(sets):
        if len(s) >= MIN_SHINGLES:
            for h in s:
                postings[h].append(i)
    out = []
    for i, s in enumerate(sets):
        if len(s) < MIN_SHINGLES:
            continue
        shared = Counter(j for h in s if len(postings[h]) <= COMMON for j in postings[h] if j > i)
        for j, n in shared.items():
            if n < CONTAINMENT * MIN_SHINGLES / 2:
                continue
            inter = len(s & sets[j])
            jac, cont = inter / len(s | sets[j]), inter / min(len(s), len(sets[j]))
            if jac >= JACCARD or cont >= CONTAINMENT:
                out.append((i, j, jac, cont))
    return out


def case(a: dict, b: dict, related: set[frozenset]) -> str:
    if a["doc_id"] == b["doc_id"]:
        return "same_doc"
    fams = {a["family"], b["family"]}
    if fams == {"guide"}:
        return "guide_copy"
    if fams == {"legal"}:
        return "legal_version" if frozenset((a["doc_id"], b["doc_id"])) in related else "legal_shared"
    return "other" if fams == {"explainer"} else "quotation"


def main() -> None:
    read = lambda name: [json.loads(line) for line in (DATA / "clean" / name).open(encoding="utf-8")]
    rows = items(read("documents.jsonl"), read("units.jsonl"))
    related = {frozenset((r["doc_id"], r["target_doc_id"])) for r in csv.DictReader((DATA / "legal_relations.csv").open(encoding="utf-8"))
               if r["target_doc_id"]}
    decided = {r["id"]: r for r in csv.DictReader((DATA / "unit_decisions.csv").open(encoding="utf-8"))}
    out = []
    for i, j, jac, cont in pairs(rows):
        a, b = sorted((rows[i], rows[j]), key=lambda r: r["id"])
        d = decided.get(b["id"]) or decided.get(a["id"])
        out.append(dict(case=case(a, b, related), a=a["id"], b=b["id"], doc_a=a["doc_id"], doc_b=b["doc_id"], jaccard=f"{jac:.2f}",
                        containment=f"{cont:.2f}", exact=skeleton(a["text"]) == skeleton(b["text"]),
                        decision=f"{d['decision']} {d['id']}" if d else ""))
    out.sort(key=lambda r: (r["case"], r["a"], r["b"]))
    with (DATA / "dup_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} pairs:", dict(Counter(r["case"] for r in out)))


if __name__ == "__main__":
    main()
