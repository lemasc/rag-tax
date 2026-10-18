"""Build the clean corpus: one record per document, plus structural units for statute and FAQ documents.

Input : data/pages.jsonl, data/legal_core.csv, data/legal_text.csv, data/text/legal/*.md,
        data/legal_scope.csv (hand-labelled PIT scope, optional; see docs/plans/pit-scope.md)
Output: data/clean/documents.jsonl  (doc_id, source, kind, role, include, title, text, flags, ...)
        data/clean/units.jsonl      (unit_id, doc_id, type, label, text, section, title, flags, notes)
Run   : uv run python -m crawler.clean.build
"""

import csv
import json
from collections import Counter
from pathlib import Path

from crawler.clean import classify
from crawler.clean.gazette import strip_page_headers
from crawler.clean.rejoin import fix_tone_marks, rejoin
from crawler.clean.text import normalize
from crawler.clean.units import split_faq, split_statute

DATA = Path("data")
OUT = DATA / "clean"

# Source-side defects we know about and do not repair here. Keyed by doc_id; surfaced in `flags`.
KNOWN_ISSUES: dict[str, str] = {}  # nothing outstanding; 60061 was fixed in parse._wrap_bare_inline


def page_docs() -> tuple[list[dict], list[dict]]:
    docs, units = [], []
    for line in (DATA / "pages.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        doc_id = p["url"].rsplit("/", 1)[-1].removesuffix(".html")
        text, joins = rejoin(normalize(p["text"] or ""))
        kind, role = classify.kind(p), classify.role(p)
        preamble, us = "", []
        if kind == "statute":
            preamble, us = split_statute(doc_id, text)
            if len(us) < 5:  # a table of contents, not statute text
                role, us = "toc", []
        elif kind == "faq":
            preamble, us = split_faq(doc_id, text)
        flags = [KNOWN_ISSUES[doc_id]] if doc_id in KNOWN_ISSUES else []
        docs.append(dict(
            doc_id=doc_id, source="page", url=p["url"], kind=kind, role=role, include=role == "content",
            title=p["heading"], breadcrumb=p["breadcrumb"], last_update=p["last_update"], tax_year=classify.tax_year(p),
            text_method="trafilatura", preamble=preamble, n_units=len(us), n_chars=len(text), flags=flags, text=text,
            n_joins=len(joins),
        ))
        units += [u.to_dict() for u in us]
    return docs, units


def legal_docs() -> list[dict]:
    core = {r["url"]: r for r in csv.DictReader((DATA / "legal_core.csv").open(encoding="utf-8")) if r["decision"] == "keep"}
    scope_path = DATA / "legal_scope.csv"
    scope = {r["url"]: r for r in csv.DictReader(scope_path.open(encoding="utf-8"))} if scope_path.exists() else {}
    docs = []
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
        s = scope.get(r["url"], {})
        docs.append(dict(
            doc_id=Path(r["file"]).stem, source="legal", url=r["url"], kind=c["kind"].split(":")[0], role="content",
            include=s.get("scope") != "non_pit", scope=s.get("scope") or None, pit_clauses=s.get("pit_clauses") or None,
            title=c["title"], breadcrumb=[], last_update=None, tax_year=None, year=c["year"] or None,
            text_method=r["method"], preamble="", n_units=0, n_chars=len(text), flags=[], text=text,
            gazette_date=gazette_date, n_header_lines_removed=len(removed), n_joins=len(joins), n_tone_fixes=len(fixes),
        ))
    return docs


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    docs, units = page_docs()
    docs += legal_docs()
    for name, rows in (("documents", docs), ("units", units)):
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    print(f"{len(docs)} documents ({sum(d['include'] for d in docs)} included), {len(units)} units -> {OUT}")
    print("by source/kind:", dict(Counter((d["source"], d["kind"]) for d in docs)))
    print("legal scope:", dict(Counter(d["scope"] for d in docs if d["source"] == "legal")))
    print("unit flags:", dict(Counter(f for u in units for f in u["flags"])))


if __name__ == "__main__":
    main()
