"""Extraction coverage: how much of the raw source made it into the text we hold.

Needs data/raw (not committed); the review notebook stores the results. Measures are on characters and on numbers,
because a lost rate or amount is worse than a lost sentence.
"""

import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

from lxml import html as lh

from crawler.clean.text import THAI_DIGITS
from crawler.legal import doc_text

NUM = re.compile(r"\d[\d,.]*\d|\d")
GAZETTE_HEADER = re.compile(r"^(เล่ม \d+ ตอน|หน้า \d+$)")  # running header/footer of every Royal Gazette page


def squash(s: str) -> str:
    return re.sub(r"[\s​]+", "", s.replace("ํา", "ำ").translate(THAI_DIGITS))


def recall(src: str, out: str) -> float:
    """Share of the source's non-space characters (as a multiset) present in the output."""
    a, b = Counter(squash(src)), Counter(squash(out))
    return 1 - sum(max(0, n - b[c]) for c, n in a.items()) / max(1, sum(a.values()))


def number_recall(src: str, out: str) -> float:
    a, b = Counter(NUM.findall(src.translate(THAI_DIGITS))), Counter(NUM.findall(out.translate(THAI_DIGITS)))
    return 1 - sum(max(0, n - b[k]) for k, n in a.items()) / max(1, sum(a.values()))


def page_source_parts(raw_html: Path) -> list[str]:
    """Visible text fragments of the page's main column, one per text node (so table cells stay separate)."""
    main = lh.parse(str(raw_html)).getroot().xpath('//div[contains(@class,"col-main")]')[0]
    for bad in main.xpath(".//script|.//style"):
        bad.getparent().remove(bad)
    return [" ".join(t.split()) for t in main.itertext() if t.strip()]


def page_coverage(pages_jsonl: Path, raw_dir: Path) -> list[dict]:
    rows = []
    for line in pages_jsonl.open(encoding="utf-8"):
        p = json.loads(line)
        pid = p["url"].rsplit("/", 1)[-1]
        parts = page_source_parts(raw_dir / pid)
        out = p["text"] or ""
        anchors = {squash(link["title"]) for link in p["content_links"]}
        missing = [s for s in parts if len(squash(s)) >= 15 and squash(s) not in squash(out) and squash(s) not in anchors]
        rows.append(dict(doc_id=pid.removesuffix(".html"), kind=None, src_chars=len(squash(" ".join(parts))),
                         char_recall=recall(" ".join(parts), out), number_recall=number_recall(" ".join(parts), out),
                         missing_fragments=missing))
    return rows


def legal_coverage(legal_text_csv: list[dict], data: Path) -> list[dict]:
    """Compare cached text with the raw HTML (`doc_text`) or `pdftotext` it came from. OCR rows are skipped:
    their text layer is garbage, so there is nothing to compare against."""
    rows = []
    for r in legal_text_csv:
        if r["status"] != "ok" or r["method"] == "ocr":
            continue
        raw = data / "raw" / "legal" / (hashlib.sha1(r["url"].encode()).hexdigest()[:12] + "." + r["url"].rsplit(".", 1)[-1])
        src = doc_text(raw) if raw.suffix == ".html" else subprocess.run(["pdftotext", str(raw), "-"], capture_output=True, text=True).stdout
        out = (data / "text" / "legal" / r["file"]).read_text(encoding="utf-8")
        lost_lines = [ln.strip() for ln in src.splitlines() if NUM.search(ln) and not GAZETTE_HEADER.match(ln.strip())
                      and Counter(NUM.findall(ln.translate(THAI_DIGITS))) - Counter(NUM.findall(out))]
        rows.append(dict(doc_id=Path(r["file"]).stem, method=r["method"], src_chars=len(squash(src)),
                         char_recall=recall(src, out), number_recall=number_recall(src, out), lost_number_lines=lost_lines))
    return rows
