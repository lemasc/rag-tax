"""Audit the headings Typhoon wrote for the 2568 filling guides against the PDF's own typesetting.

The OCR marks a heading (`#`, or a line that is only bold) wherever it thinks the type changes, and gets it wrong: a bold
lead-in followed by a paragraph, or a numbered item in plain type, becomes a heading. The PDFs are born-digital, so
`pdftohtml -xml` still has which text runs are bold even where its Thai is damaged. For each OCR heading this finds its
text on the same PDF page (matched on Thai consonants and digits only, which survive the damage) and measures how much
of it is bold. Headings with little bold are candidates to demote to plain text (data/guide_heading_decisions.csv).

Input : data/raw/pit2568/*.pdf (not checked in), data/text/guide/<stem>.md
Output: data/guide_heading_audit.csv  (stem, page, kind, length, bold_frac, text); bold_frac is empty when the text was
        not found on the page (a table cell, a short or Latin-only heading)
Run   : uv run python -m crawler.guide_headings
"""

import csv
import html
import re
import subprocess
import tempfile
from collections.abc import Iterator
from pathlib import Path

DATA = Path("data")
RAW = DATA / "raw" / "pit2568"
GUIDES = ("Ins90_241268", "Ins91_241268", "Ins94_050668")
THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
BOLD_LINE = re.compile(r"^\*\*([^*\n]{2,100})\*\*$")
ANCHOR = re.compile(r"<!-- page (\d+) -->")
PREFIXES = (30, 18, 10)  # skeleton characters tried, longest first, when looking a heading up on its page


def skeleton(text: str) -> str:
    """Thai consonants and digits only: what pdftotext-style extraction of Thai keeps intact (vowels, tone marks and sara am
    are what it damages)."""
    return re.sub(r"[^ก-ฮ0-9]", "", text.translate(THAI_DIGITS))


def pdf_pages(xml: str) -> dict[int, tuple[str, list[bool]]]:
    """{page: (skeleton of the page's text in stream order, bold flag per skeleton character)} from `pdftohtml -xml`."""
    pages = {}
    for pm in re.finditer(r'<page number="(\d+)"[^>]*>(.*?)</page>', xml, re.S):
        chars, bold = [], []
        for rm in re.finditer(r"<text [^>]*>(.*?)</text>", pm[2], re.S):
            sk = skeleton(html.unescape(re.sub(r"<[^>]+>", "", rm[1])))
            chars.append(sk)
            bold += ["<b>" in rm[1]] * len(sk)
        pages[int(pm[1])] = ("".join(chars), bold)
    return pages


def ocr_headings(text: str) -> Iterator[tuple[int, str, str]]:
    """(page, kind, heading text) for every heading in raw OCR text; kind is the `#` run or "bold"."""
    parts = ANCHOR.split(text)
    for i in range(1, len(parts), 2):
        for line in parts[i + 1].split("\n"):
            if m := HEADING.match(line):
                yield int(parts[i]), m[1], m[2].replace("**", "")
            elif m := BOLD_LINE.match(line.strip()):
                yield int(parts[i]), "bold", m[1]


def bold_fraction(heading: str, page: tuple[str, list[bool]]) -> float | None:
    """Share of the heading's characters set in bold on its PDF page, None if the text is not found there.

    The text can occur more than once on a page (a heading phrase is also used in running text), so every occurrence is
    measured and the most bold one counts: a real heading is bold wherever it is set as one, and the audit should not
    propose demoting a heading because the phrase also appears in plain type.
    """
    sk, bold = page
    hs = skeleton(heading)
    for n in PREFIXES:
        if len(hs) < n:
            continue
        starts = [m.start() for m in re.finditer(re.escape(hs[:n]), sk)]
        if starts:
            return max(sum(bold[p:p + len(hs)]) / len(bold[p:p + len(hs)]) for p in starts)
    return None


def audit(stem: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftohtml", "-xml", "-i", "-q", "-nodrm", str(RAW / f"{stem}.pdf"), f"{tmp}/{stem}"], check=True)
        pages = pdf_pages(Path(f"{tmp}/{stem}.xml").read_text(encoding="utf-8"))
    rows = []
    for page, kind, text in ocr_headings((DATA / "text" / "guide" / f"{stem}.md").read_text(encoding="utf-8")):
        b = bold_fraction(text, pages[page]) if page in pages else None
        rows.append(dict(stem=stem, page=page, kind=kind, length=len(text), bold_frac="" if b is None else f"{b:.2f}", text=text))
    return rows


def main() -> None:
    rows = [r for stem in GUIDES for r in audit(stem)]
    with (DATA / "guide_heading_audit.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["stem", "page", "kind", "length", "bold_frac", "text"])
        w.writeheader()
        w.writerows(rows)
    low = [r for r in rows if r["bold_frac"] and float(r["bold_frac"]) < 0.5]
    print(f"{len(rows)} headings; bold >= 0.5: {sum(1 for r in rows if r['bold_frac'] and float(r['bold_frac']) >= 0.5)}; "
          f"bold < 0.5: {len(low)}; not found on the page: {sum(1 for r in rows if not r['bold_frac'])}")


if __name__ == "__main__":
    main()
