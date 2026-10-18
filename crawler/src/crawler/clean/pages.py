"""Page anchors in OCR text.

Typhoon OCR output starts each PDF page with `<!-- page N -->`, and `extract.py` keeps those lines in `data/text/legal/`.
Here they are taken out of the text and kept as offsets, so a unit or chunk can say which PDF pages it came from
(`page_of`). N is the page index in the PDF (1-based), not the printed Gazette page number.

Run this last: the other cleaning steps change the text length, and offsets are into the final text. They leave the
anchor lines alone, which also means a word split across a page boundary is never rejoined.
"""

import re

ANCHOR = re.compile(r"<!-- page (\d+) -->")


def take_page_anchors(text: str) -> tuple[str, list[list[int]] | None]:
    """Return (text without anchor lines, [[page, start offset], ...]); the list is None when there are no anchors.

    The blank lines right after an anchor are dropped, so `start` is the first character of the page's content.
    """
    out: list[str] = []
    pages: list[list[int]] = []
    size = 0  # length of "\n".join(out)
    skip_blank = False
    for line in text.split("\n"):
        m = ANCHOR.fullmatch(line.strip())
        if m:
            pages.append([int(m[1]), size + 1 if out else 0])
            skip_blank = True
            continue
        if skip_blank and not line.strip():
            continue
        skip_blank = False
        size += len(line) + (1 if out else 0)
        out.append(line)
    if not pages:
        return text, None
    return "\n".join(out).strip(), pages


def page_of(pages: list[list[int]] | None, offset: int) -> int | None:
    """The page that contains `offset` in the text returned by `take_page_anchors`."""
    if not pages:
        return None
    found = pages[0][0]
    for page, start in pages:
        if start > offset:
            break
        found = page
    return found
