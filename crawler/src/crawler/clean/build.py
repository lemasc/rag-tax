"""Build the clean corpus: one record per document, plus structural units for statute and FAQ documents.

Input : data/pages.jsonl, data/legal_core.csv, data/legal_text.csv, data/text/legal/*.md
Output: data/clean/documents.jsonl  (doc_id, source, kind, role, include, title, text, flags, ...)
        data/clean/units.jsonl      (unit_id, doc_id, type, label, text, section, title, flags, notes)
Run   : uv run python -m crawler.clean.build
"""

import csv
import json
from collections import Counter
from pathlib import Path

from crawler.clean import classify
from crawler.clean.text import normalize
from crawler.clean.units import split_faq, split_statute

DATA = Path("data")
OUT = DATA / "clean"

# Source-side defects we know about and do not repair here. Keyed by doc_id; surfaced in `flags`.
KNOWN_ISSUES = {
    "60061": "extraction_truncated: trafilatura cut the tail of the first answer (social-security deduction, spouse paragraph)",
}


def page_docs() -> tuple[list[dict], list[dict]]:
    docs, units = [], []
    for line in (DATA / "pages.jsonl").open(encoding="utf-8"):
        p = json.loads(line)
        doc_id = p["url"].rsplit("/", 1)[-1].removesuffix(".html")
        text = normalize(p["text"] or "")
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
        ))
        units += [u.to_dict() for u in us]
    return docs, units


def legal_docs() -> list[dict]:
    core = {r["url"]: r for r in csv.DictReader((DATA / "legal_core.csv").open(encoding="utf-8")) if r["decision"] == "keep"}
    docs = []
    for r in csv.DictReader((DATA / "legal_text.csv").open(encoding="utf-8")):
        c = core.get(r["url"])
        if c is None or r["status"] != "ok":
            continue
        text = normalize((DATA / "text" / "legal" / r["file"]).read_text(encoding="utf-8"))
        docs.append(dict(
            doc_id=Path(r["file"]).stem, source="legal", url=r["url"], kind=c["kind"].split(":")[0], role="content", include=True,
            title=c["title"], breadcrumb=[], last_update=None, tax_year=None, year=c["year"] or None,
            text_method=r["method"], preamble="", n_units=0, n_chars=len(text), flags=[], text=text,
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
    print("unit flags:", dict(Counter(f for u in units for f in u["flags"])))


if __name__ == "__main__":
    main()
