"""Propose which legal instruments amend or repeal which, from their own clauses.

Similar text is not a version: กฎกระทรวง and ประกาศ that share criteria clauses are often parallel rules (ประกาศอธิบดี 224, 397
and 398 each replace a different older notice), so a relation is only taken from what an instrument says it does: a clause
with `ให้ยกเลิก` (repeal, or amend when it repeals a part: "ให้ยกเลิกความในมาตรา 7 แห่ง...") or `ให้เพิ่ม` (amend by adding
an item) followed by the instrument it names. Targets the corpus does not carry are kept, with an empty target_doc_id.

The proposals are checked by hand into data/legal_relations.csv, which clean.build reads (`amends` / `amended_by`).

Input : data/clean/documents.jsonl, data/clean/units.jsonl
Output: data/legal_relation_candidates.csv  (doc_id, unit_id, relation, scope, target_kind, target_number, target_doc_id, cited)
Run   : uv run python -m crawler.legal_relations
"""

import csv
import json
import re
from pathlib import Path

DATA = Path("data")
GUIDE_KIND = "คู่มือกรอกแบบ"
VERB = re.compile(r"ให้ยกเลิก|ให้เพิ่ม")
# The instrument named after the verb. A Code amendment act ("พระราชบัญญัติแก้ไขเพิ่มเติมประมวลรัษฎากร (ฉบับที่ 10)") is part
# of how a clause cites its own legal basis, not a target, so the number must come before any พระราชบัญญัติ.
CITE = re.compile(
    r"(กฎกระทรวง|พระราชกฤษฎีกา|ประกาศอธิบดีกรมสรรพากร|คำสั่งกรมสรรพากร|ประกาศกระทรวงการคลัง|ประกาศกรมสรรพากร)"
    r"(?:(?!พระราชบัญญัติ)[^\n]){0,160}?(?:ฉบับที่\s*(\d+)|ที่\s*(ป\.\s*\d+\s*/\s*\d+))"
)
CITE_WINDOW = 300  # characters after the verb in which the named instrument must start
KIND = {"ประกาศอธิบดีกรมสรรพากร": "ประกาศอธิบดี"}  # citation wording -> documents.jsonl kind, where they differ
PART = re.compile(r"\s*(ความ|ข้อความ|บทนิยาม|ข้อ\s*\d)")  # "ให้ยกเลิกความใน (78) ของข้อ 2 แห่ง...": a part, not the whole
LIST_ITEM = re.compile(r"(?m)^\s*\(\d+\)\s*")
TITLE_NUMBER = re.compile(r"ฉบับที่\s*(\d+)|(ป\.\s*\d+\s*/\s*\d+)")
HEAD_CHARS = 400  # where an instrument states its own number ("ประกาศอธิบดีกรมสรรพากร ... (ฉบับที่ 58)")
FIELDS = ["doc_id", "unit_id", "relation", "scope", "target_kind", "target_number", "target_doc_id", "cited"]


def number(text: str) -> str | None:
    m = TITLE_NUMBER.search(text)
    return re.sub(r"\s+", "", m[1] or m[2]) if m else None


def own_number(d: dict) -> str | None:
    """The number an instrument gives itself in its heading (the text before `อาศัยอำนาจ`). The listing title is not it:
    rd.go.th lists a consolidated ประกาศ under its latest amendment ("ฉบับที่ 224" holds ประกาศ 165 as amended), and a few
    are mislabelled (2502.html is listed as กฎกระทรวง ฉบับที่ 380 and holds 126; AI_AUDIT, "Mislabelled and
    duplicate-looking listings"). A document whose title has no number (two ประกาศกรมสรรพากร) has none: its heading
    only cites others."""
    if number(d["title"]) is None:
        return None
    return number(d["text"][:HEAD_CHARS].split("อาศัยอำนาจ")[0]) or number(d["title"])


def index(docs: list[dict]) -> dict[tuple[str, str], str]:
    """(kind, number) -> doc_id for the legal instruments."""
    out = {}
    for d in docs:
        if d["source"] == "legal" and d["kind"] != GUIDE_KIND and (n := own_number(d)):
            out.setdefault((d["kind"], n), d["doc_id"])
    return out


def proposals(docs: list[dict], units: list[dict]) -> list[dict]:
    by_id = {d["doc_id"]: d for d in docs}
    idx = index(docs)
    rows = []
    for u in units:
        d = by_id[u["doc_id"]]
        if d["source"] != "legal" or d["kind"] == GUIDE_KIND:
            continue
        for v in VERB.finditer(u["text"]):
            after = u["text"][v.end():]
            # "ให้ยกเลิก\n(1) ประกาศ... (ฉบับที่ 58)\n(2) ...": each item names its own target
            items = LIST_ITEM.split(after)[1:] if LIST_ITEM.match(after) else [after]
            for item in items:
                c = CITE.search(item[:CITE_WINDOW + 200])
                if c is None or c.start() > CITE_WINDOW:
                    continue
                kind, num = KIND.get(c[1], c[1]), re.sub(r"\s+", "", c[2] or c[3])
                target = idx.get((kind, num), "")
                if target == d["doc_id"]:
                    continue
                part = bool(PART.match(item))
                relation = "amends" if v.group() == "ให้เพิ่ม" or part else "repeals"
                scope = " ".join(item[: c.start()].split())[:80] if part else ""
                rows.append(dict(doc_id=d["doc_id"], unit_id=u["unit_id"], relation=relation, scope=scope, target_kind=kind,
                                 target_number=num, target_doc_id=target, cited=" ".join((v.group() + " " + item[: c.end()]).split())[:200]))
    return rows


def main() -> None:
    read = lambda name: [json.loads(line) for line in (DATA / "clean" / name).open(encoding="utf-8")]
    rows = proposals(read("documents.jsonl"), read("units.jsonl"))
    with (DATA / "legal_relation_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} proposals, {sum(1 for r in rows if r['target_doc_id'])} with the target in the corpus")


if __name__ == "__main__":
    main()
