"""Character- and whitespace-level cleaning shared by every document type.

Deliberately does not touch line structure beyond trimming: unwrapping hard-wrapped PDF/OCR lines and
restoring paragraphs in flattened HTML are boundary decisions that belong to the per-type splitters.
"""

import re

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

# cp1252 bytes that reached us as C1 control characters (rd.go.th pages declare the wrong charset).
# \x93/\x94 delimit the replacement clause in amending instruments, so they must stay as quotes.
C1_FIX = {
    0x91: "‘", 0x92: "’", 0x93: "“", 0x94: "”", 0x95: "•", 0x96: "–", 0x97: "—",
}
C1 = re.compile(r"[\x80-\x9f]")
INVISIBLE = re.compile("[​‌‍﻿]")
# U+FFFD is already in the source HTML (61065: 20, 61117: 1); in the duplicate page 61081 the same spots hold a space.
REPLACEMENT = "\ufffd"
BR = re.compile(r"<br\s*/?>", re.I)  # leaked from the source markup (one FAQ page)
ENTITIES = {"&amp;": "&", "&nbsp;": " ", "&nsbp;": " "}  # the only ones present; "&nsbp;" is a typo in the source


def _c1(m: re.Match) -> str:
    return C1_FIX.get(ord(m.group()), "")


def normalize(text: str) -> str:
    """Clean one document's text. Idempotent."""
    t = C1.sub(_c1, text)
    t = BR.sub("\n", INVISIBLE.sub("", t)).replace("\xa0", " ").replace(REPLACEMENT, " ")
    for ent, ch in ENTITIES.items():
        t = t.replace(ent, ch)
    t = t.translate(THAI_DIGITS)
    t = t.replace("\u0e4d\u0e32", "\u0e33")  # sara am split into nikhahit + sara aa (pdftotext)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.replace("\r", "").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


EMPTY_ROWS = re.compile(r"<tr>(?:\s*<td>\s*</td>)*\s*</tr>\s*")
EMPTY_RUNS = re.compile(r"(?:<td>\s*</td>\s*){3,}")


def drop_empty_cells(text: str) -> str:
    """Remove the `<td></td>` padding Typhoon writes for blank table cells (176 in Ins90's OCR): rows with nothing in
    them and runs of three or more empty cells. One or two empty cells stay, since they can hold a column's place.
    Not part of `normalize`: only OCR documents with HTML tables need it."""
    return EMPTY_RUNS.sub("", EMPTY_ROWS.sub("", text))


PAGE_NUMBER = re.compile(r"^[ \t]*<page_number>\s*\d*\s*</page_number>[ \t]*\n?", re.M)


def drop_page_numbers(text: str) -> str:
    """Remove the printed page number Typhoon marks as its own `<page_number>N</page_number>` line (76 in the three
    2568 guides). The PDF page is already kept as a page anchor."""
    return PAGE_NUMBER.sub("", text)


# A page whose HTML puts every text run on its own line (61549: 1,751 lines, median 19 characters, no blank lines).
HARD_WRAPPED_LINES = 40
HARD_WRAPPED_MEDIAN = 45
BLOCK_START = re.compile(r"^(?:\||[QA]\s*\d+\b|\d+\s*:|\d+\s*[.)](?:\s|$)|\d+\.\d+|[-•*–]\s|\([ก-ฮ\d]+\)|\*\*|#)")


def hard_wrapped(text: str) -> bool:
    """True for a document whose lines are text runs, not paragraphs: at least HARD_WRAPPED_LINES lines and a median line
    of HARD_WRAPPED_MEDIAN characters or less."""
    lens = sorted(len(ln) for ln in text.split("\n") if ln.strip())
    return len(lens) >= HARD_WRAPPED_LINES and lens[len(lens) // 2] <= HARD_WRAPPED_MEDIAN


def unwrap_lines(text: str) -> str:
    """Join each line to the one before it with a space, except a blank line, which stays, and a line that starts a block:
    a Q or A marker (or a bare `2 :` whose Q was lost), a numbered or bulleted item, a table row, a heading; nothing joins
    onto a table row. Only whitespace changes, so a splitter that works on lines
    (the FAQ markers) can run on the result."""
    out: list[str] = []
    for ln in text.split("\n"):
        if out and out[-1] and not out[-1].startswith("|") and ln.strip() and not BLOCK_START.match(ln.strip()):
            out[-1] += " " + ln.strip()
        else:
            out.append(ln.strip())
    return "\n".join(out)


def insert_headings(text: str, rows: list[dict]) -> str:
    """Put each row's `heading` on its own `## ` line before the line that starts with its `before`. For a page whose
    section headings are pictures (63437: six banner images): the text starts each section where the picture was. A row
    whose `before` matches no line start after the previous row's raises, so a change of the page text cannot move a
    heading silently."""
    out, pos = text, 0
    for r in rows:
        m = re.compile(r"(?m)^" + re.escape(r["before"])).search(out, pos)
        if m is None:
            raise ValueError(f"page_headings.csv: no line of page {r['page_id']} starts with {r['before']!r} after the previous heading")
        out = out[: m.start()] + f"## {r['heading']}\n" + out[m.start() :]
        pos = m.start() + len(r["heading"]) + 4
    return out

