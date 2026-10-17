"""Royal Gazette page furniture left in the text of PDF-derived legal documents (pdftotext and OCR).

Every Gazette page starts with a header: volume/part (เล่ม … ตอน …), page (หน้า N ราชกิจจานุเบกษา) and the publication date.
Extraction removes most of it, but misses two shapes: pdftotext writes the tone mark out of order ("เลม่ 136 ตอนที่ 79 ก"),
and Typhoon OCR keeps "หน้า 3 ราชกิจจานุเบกษา" on one line. The publication date comes back at every page start.

The first standalone date is kept (it is the publication date, and "effective the day after publication" needs it) and
returned as `gazette_date`; identical repeats are page headers and are dropped.
"""

import re

NUMBERING = re.compile(r"^เล(?:่ม|ม่)\s*\d+\s*ตอน(?:ที่|พิเศษ)\s*\d+\s*[ก-ฮ]?$")
PAGE = re.compile(r"^หน้า\s*\d+(?:\s*ราชกิจจานุเบกษา)?$")
MONTHS = "มกราคม|กุมภาพันธ์|มีนาคม|เมษายน|พฤษภาคม|มิถุนายน|กรกฎาคม|สิงหาคม|กันยายน|ตุลาคม|พฤศจิกายน|ธันวาคม"
DATE = re.compile(rf"^(\d{{1,2}} (?:{MONTHS}) \d{{4}})$")


def strip_page_headers(text: str) -> tuple[str, str | None, list[str]]:
    """Return (text without page headers, publication date or None, the lines removed)."""
    kept, removed, gazette_date = [], [], None
    for line in text.split("\n"):
        s = line.strip()
        if NUMBERING.match(s) or PAGE.match(s):
            removed.append(s)
        elif m := DATE.match(s):
            if gazette_date is None:
                gazette_date = m.group(1)
                kept.append(line)
            elif m.group(1) == gazette_date:
                removed.append(s)
            else:
                kept.append(line)  # a different standalone date: not ours to judge
        else:
            kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), gazette_date, removed
