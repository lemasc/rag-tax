"""Build the clean corpus: one record per document, plus structural units for statute and FAQ documents.

Input : data/pages.jsonl, data/legal_core.csv, data/legal_text.csv, data/text/legal/*.md,
        data/legal_catalog.csv + data/text/guide/*.md (the คู่มือกรอกแบบ filling guides),
        data/image_decisions.csv + data/text/image/*.md (images decided keep become documents, source "image"),
        data/legal_scope.csv (hand-labelled PIT scope, optional; see docs/plans/pit-scope.md),
        data/unit_decisions.csv (hand-recorded duplicate drops; a dropped document or unit gets include=false and duplicate_of),
        data/legal_relations.csv (which instrument amends or repeals which, checked by hand from crawler.legal_relations)
Output: data/clean/documents.jsonl  (doc_id, source, kind, role, include, title, text, flags, pages, amends, amended_by, ...)
        `pages` is [[pdf page, start offset in text], ...] for OCR documents, else null (see clean/pages.py)
        data/clean/units.jsonl      (unit_id, doc_id, type, label, text, section, title, flags, notes, include, duplicate_of)
Run   : uv run python -m crawler.clean.build
"""

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from crawler import images
from crawler.clean import classify
from crawler.clean.gazette import strip_page_headers
from crawler.clean.pages import demote_headings, replace_pages, take_page_anchors
from crawler.clean.rejoin import fix_tone_marks, rejoin
from crawler.clean.text import drop_empty_cells, drop_page_numbers, hard_wrapped, insert_headings, normalize, unwrap_lines
from crawler.clean.units import split_faq, split_guide, split_instrument, split_statute

DATA = Path("data")
OUT = DATA / "clean"
# Typhoon OCR of the 2568 filling guides (`~/san/ocr/typhoon_ocr_file.py`), copied from the cache next to the PDFs
# (data/raw/pit2568/ocr, not checked in) so a fresh clone can build, like data/text/image.
GUIDE_KIND = "คู่มือกรอกแบบ"
GUIDE_OCR = DATA / "text" / "guide"
GUIDE_HEADINGS = DATA / "guide_heading_decisions.csv"  # keep/demote per OCR heading, from crawler.guide_headings
PAGE_HEADINGS = DATA / "page_headings.csv"  # page_id, heading, before, source, note: headings that are pictures on the page (63437)
GUIDE_OVERRIDES = DATA / "guide_overrides"  # <stem>/page-NN.md: hand-corrected text for a page the OCR misreads (checked in)

# Source-side defects we know about and do not repair here. Keyed by doc_id; surfaced in `flags`.
KNOWN_ISSUES: dict[str, str] = {}  # nothing outstanding; 60061 was fixed in parse._wrap_bare_inline


def page_docs() -> tuple[list[dict], list[dict]]:
    docs, units = [], []
    headings: dict[str, list[dict]] = {}
    for r in csv.DictReader(PAGE_HEADINGS.open(encoding="utf-8")) if PAGE_HEADINGS.exists() else []:
        headings.setdefault(r["page_id"], []).append(r)
    for line in (DATA / "pages.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        doc_id = p["url"].rsplit("/", 1)[-1].removesuffix(".html")
        text, joins = rejoin(normalize(p["text"] or ""))
        wrapped = hard_wrapped(text)
        if wrapped:  # every text run on its own line (61549): paragraphs are restored before the splitter reads the lines
            text = unwrap_lines(text)
        kind, role = classify.kind(p), classify.role(p)
        preamble, us = "", []
        if kind == "statute":
            preamble, us = split_statute(doc_id, text)
            if len(us) < 5:  # a table of contents, not statute text
                role, us = "toc", []
        elif kind == "faq":
            preamble, us = split_faq(doc_id, text)
        elif doc_id in headings:
            text = insert_headings(text, headings[doc_id])
            preamble, us = split_guide(doc_id, text, unit_type="section")
        flags = ([KNOWN_ISSUES[doc_id]] if doc_id in KNOWN_ISSUES else []) + (["unwrapped_lines"] if wrapped else [])
        docs.append(dict(
            doc_id=doc_id, source="page", url=p["url"], kind=kind, role=role, include=role == "content",
            title=p["heading"], breadcrumb=p["breadcrumb"], last_update=p["last_update"], tax_year=classify.tax_year(p),
            text_method="trafilatura", preamble=preamble, n_units=len(us), n_chars=len(text), flags=flags, text=text,
            n_joins=len(joins), pages=None,
        ))
        units += [u.to_dict() for u in us]
    return docs, units


def legal_docs() -> tuple[list[dict], list[dict]]:
    """Documents and units of the legal instruments the Code cites; units only for those with `ข้อ`/`มาตรา` headings."""
    core = {r["url"]: r for r in csv.DictReader((DATA / "legal_core.csv").open(encoding="utf-8")) if r["decision"] == "keep"}
    scope_path = DATA / "legal_scope.csv"
    scope = {r["url"]: r for r in csv.DictReader(scope_path.open(encoding="utf-8"))} if scope_path.exists() else {}
    docs, units = [], []
    for r in csv.DictReader((DATA / "legal_text.csv").open(encoding="utf-8")):
        c = core.get(r["url"])
        if c is None or r["status"] != "ok":
            continue
        text = normalize((DATA / "text" / "legal" / r["file"]).read_text(encoding="utf-8"))
        gazette_date, removed = None, []
        if r["method"] in ("pdftotext", "ocr"):
            text, gazette_date, removed = strip_page_headers(text)
        text, joins = rejoin(text)
        fixes = []
        if r["method"] == "pdftotext":
            text, fixes = fix_tone_marks(text)
        text, pages = take_page_anchors(text)  # last: offsets are into the final text
        s = scope.get(r["url"], {})
        include = s.get("scope") != "non_pit"
        preamble, us = split_instrument(Path(r["file"]).stem, text) if include else ("", [])
        preamble = preamble if us else ""
        docs.append(dict(
            doc_id=Path(r["file"]).stem, source="legal", url=r["url"], kind=c["kind"].split(":")[0], role="content",
            include=include, scope=s.get("scope") or None, pit_clauses=s.get("pit_clauses") or None,
            title=c["title"], breadcrumb=[], last_update=None, tax_year=None, year=c["year"] or None,
            text_method=r["method"], preamble=preamble, n_units=len(us), n_chars=len(text), flags=[], text=text,
            gazette_date=gazette_date, n_header_lines_removed=len(removed), n_joins=len(joins), n_tone_fixes=len(fixes), pages=pages,
        ))
        units += [u.to_dict() for u in us]
    return docs, units


def guide_docs() -> tuple[list[dict], list[dict]]:
    """One document per `legal_catalog.csv` row of kind คู่มือกรอกแบบ, from its OCR in data/text/guide (not in data/text/legal:
    these guides were OCR'd outside the crawler flow and are not cited by the Code, so legal_core never sees them)."""
    docs, units = [], []
    heading_rows = list(csv.DictReader(GUIDE_HEADINGS.open(encoding="utf-8")))
    for r in csv.DictReader((DATA / "legal_catalog.csv").open(encoding="utf-8")):
        if r["kind"] != GUIDE_KIND:
            continue
        stem = r["url"].rsplit("/", 1)[-1].removesuffix(".pdf")
        path = GUIDE_OCR / f"{stem}.md"
        if not path.exists():
            raise SystemExit(f"{stem} is in legal_catalog.csv as {GUIDE_KIND} but {path} is missing")
        overrides = {int(f.stem.removeprefix("page-")): f.read_text(encoding="utf-8") for f in sorted((GUIDE_OVERRIDES / stem).glob("page-*.md"))}
        raw, replaced = replace_pages(path.read_text(encoding="utf-8"), overrides)
        raw, _ = demote_headings(raw, [d for d in heading_rows if d["stem"] == stem])
        text, joins = rejoin(drop_page_numbers(drop_empty_cells(normalize(raw))))
        text, pages = take_page_anchors(text)
        year = re.search(r"ปีภาษี\s*(25\d\d)", r["title"])
        preamble, us = split_guide(stem, text)
        docs.append(dict(
            doc_id=stem, source="legal", url=r["url"], kind=GUIDE_KIND, role="content", include=True, scope=None, pit_clauses=None,
            title=r["title"], breadcrumb=[], last_update=None, tax_year=int(year[1]) if year else None, year=None,
            text_method="ocr", preamble=preamble, n_units=len(us), n_chars=len(text),
            flags=["manual_override:p" + ",".join(map(str, replaced))] if replaced else [], text=text,
            gazette_date=None, n_header_lines_removed=0, n_joins=len(joins), n_tone_fixes=0, pages=pages,
        ))
        units += [u.to_dict() for u in us]
    return docs, units


def image_docs() -> list[dict]:
    """One document per image decided `keep` in data/image_decisions.csv (see crawler/images.py), from its exported OCR text."""
    index = {r["image_id"]: r for r in images.load_index()}
    docs = []
    for image_id, d in sorted(images.load_decisions().items()):
        if d["decision"] != "keep":
            continue
        path = images.TEXT / f"{image_id}.md"
        if not path.exists():
            raise SystemExit(f"{image_id} is decided keep but {path} is missing: run `python -m crawler.images --ocr {image_id}`")
        text = normalize(path.read_text(encoding="utf-8"))
        heading = next((ln.lstrip("# ").strip() for ln in text.split("\n") if ln.startswith("#")), "")
        page_id = index[image_id]["page_id"]
        docs.append(dict(
            doc_id=image_id, source="image", url=f"https://www.rd.go.th/{page_id}.html", kind="image", role="content", include=True,
            title=d["title"] or heading or image_id, breadcrumb=[], last_update=None, tax_year=int(d["tax_year"]) if d["tax_year"] else None,  # set by hand: open item 5
            text_method="manual" if d["source"] == "manual" else "ocr", preamble="", n_units=0, n_chars=len(text),
            flags=[] if d["verified"] else ["unverified"], text=text, n_joins=0, pages=None,
            parent_page=page_id, image_url=index[image_id]["url"], verified=d["verified"] or None,
        ))
    return docs


def text_hash(text: str) -> str:
    """Short hash of a record's text with whitespace collapsed, recorded with a decision so it can be checked later."""
    return hashlib.sha1(" ".join(text.split()).encode()).hexdigest()[:12]


def apply_decisions(docs: list[dict], units: list[dict], decisions: list[dict]) -> None:
    """Mark dropped documents and units include=false with what they duplicate. Every decision must name an existing
    record, and one with a `text_hash` a record with that text: unit ids are positional (`62149#025`), so a splitter or
    cleaning change that moves an id onto other text fails here instead of silently dropping the wrong unit."""
    for u in units:
        u["include"], u["duplicate_of"] = True, None
    by_level = {"doc": {d["doc_id"]: d for d in docs}, "unit": {u["unit_id"]: u for u in units}}
    for r in decisions:
        if r["decision"] != "drop":
            continue
        rec = by_level[r["level"]].get(r["id"])
        if rec is None:
            raise SystemExit(f"unit_decisions.csv: no {r['level']} {r['id']!r} in the built corpus")
        if r.get("text_hash") and text_hash(rec["text"]) != r["text_hash"]:
            raise SystemExit(f"unit_decisions.csv: the text of {r['level']} {r['id']!r} changed since the decision; check it again")
        rec["include"], rec["duplicate_of"] = False, r["duplicate_of"] or None


def apply_relations(docs: list[dict], units: list[dict], relations: list[dict]) -> None:
    """Record on each instrument what it amends or repeals (`amends`) and, on a target the corpus carries, who amended or
    repealed it (`amended_by`, plus an `amended`/`repealed` flag the chunks carry). Old instruments stay in the corpus: a
    question can be about an earlier year, and the generator can see that a text is no longer in force."""
    by_id = {d["doc_id"]: d for d in docs}
    unit_ids = {u["unit_id"] for u in units}
    for d in docs:
        d["amends"], d["amended_by"] = None, None
    for r in relations:
        src, tgt = by_id.get(r["doc_id"]), by_id.get(r["target_doc_id"]) if r["target_doc_id"] else None
        if src is None or r["unit_id"] not in unit_ids or (r["target_doc_id"] and tgt is None):
            raise SystemExit(f"legal_relations.csv: {r['doc_id']} {r['unit_id']} -> {r['target_doc_id']!r} not in the built corpus")
        src["amends"] = (src["amends"] or []) + [dict(relation=r["relation"], target=f"{r['target_kind']} {r['target_number']}",
                                                     target_doc_id=r["target_doc_id"] or None, scope=r["scope"] or None)]
        if tgt is not None:
            tgt["amended_by"] = (tgt["amended_by"] or []) + [dict(doc_id=src["doc_id"], relation=r["relation"], year=src["year"], scope=r["scope"] or None)]
            flag = "repealed" if r["relation"] == "repeals" else "amended"
            if flag not in tgt["flags"]:
                tgt["flags"].append(flag)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    docs, units = page_docs()
    legal, legal_units = legal_docs()
    docs += legal
    units += legal_units
    guide, guide_units = guide_docs()
    docs += guide
    units += guide_units
    docs += image_docs()
    decisions_path = DATA / "unit_decisions.csv"
    if decisions_path.exists():
        apply_decisions(docs, units, list(csv.DictReader(decisions_path.open(encoding="utf-8"))))
    relations_path = DATA / "legal_relations.csv"
    if relations_path.exists():
        apply_relations(docs, units, list(csv.DictReader(relations_path.open(encoding="utf-8"))))
    for name, rows in (("documents", docs), ("units", units)):
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print(f"{len(docs)} documents ({sum(d['include'] for d in docs)} included), {len(units)} units ({sum(u['include'] for u in units)} included) -> {OUT}")
    print("by source/kind:", dict(Counter((d["source"], d["kind"]) for d in docs)))
    print("legal scope:", dict(Counter(d["scope"] for d in docs if d["source"] == "legal")))
    print("unit flags:", dict(Counter(f for u in units for f in u["flags"])))


if __name__ == "__main__":
    main()
