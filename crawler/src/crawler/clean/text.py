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
BR = re.compile(r"<br\s*/?>", re.I)  # leaked from the source markup (one FAQ page)
ENTITIES = {"&amp;": "&", "&nbsp;": " ", "&nsbp;": " "}  # the only ones present; "&nsbp;" is a typo in the source


def _c1(m: re.Match) -> str:
    return C1_FIX.get(ord(m.group()), "")


def normalize(text: str) -> str:
    """Clean one document's text. Idempotent."""
    t = C1.sub(_c1, text)
    t = BR.sub("\n", INVISIBLE.sub("", t)).replace("\xa0", " ")
    for ent, ch in ENTITIES.items():
        t = t.replace(ent, ch)
    t = t.translate(THAI_DIGITS)
    t = t.replace("\u0e4d\u0e32", "\u0e33")  # sara am split into nikhahit + sara aa (pdftotext)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in t.replace("\r", "").split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
