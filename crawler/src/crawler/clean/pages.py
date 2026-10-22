"""Page anchors in OCR text.

Typhoon OCR output starts each PDF page with `<!-- page N -->`, and `extract.py` keeps those lines in `data/text/legal/`.
Here they are taken out of the text and kept as offsets, so a unit or chunk can say which PDF pages it came from
(`page_of`). N is the page index in the PDF (1-based), not the printed Gazette page number.

Run this last: the other cleaning steps change the text length, and offsets are into the final text. They leave the
anchor lines alone, which also means a word split across a page boundary is never rejoined.
"""

import re

from crawler.clean.units import BOLD_HEADING, HEADING

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


def replace_pages(text: str, overrides: dict[int, str]) -> tuple[str, list[int]]:
    """Replace the content of whole PDF pages in raw OCR text (the anchor line stays) and return (text, pages replaced).

    Used for the few pages Typhoon misreads (a column's continuation read as a table; run-in paragraphs read as
    headings). Run it on the raw text, before `normalize`, so an override gets the same cleaning as the OCR it replaces.
    A page number the text does not have is an error: the override would silently do nothing.
    """
    parts = re.split(r"(<!-- page \d+ -->)", text)
    anchors = {int(ANCHOR.fullmatch(parts[i])[1]): i for i in range(1, len(parts), 2)}
    missing = sorted(set(overrides) - set(anchors))
    if missing:
        raise ValueError(f"no page {missing} in the text to override")
    for n, content in overrides.items():
        parts[anchors[n] + 1] = "\n\n" + content.strip("\n") + "\n\n"
    return "".join(parts), sorted(overrides)


def demote_headings(text: str, decisions: list[dict]) -> tuple[str, int]:
    """Turn OCR headings (`#` lines, bold-only lines) into plain lines where `decisions` (stem's rows of
    data/guide_heading_decisions.csv: page, text, decision) say demote; return (text, number demoted).

    A row matches the heading on its page whose text starts with the row's text. A demote row that matches nothing is an
    error, like an override for a page that is not there. Run on the raw text, before `normalize`.
    """
    todo = [(int(d["page"]), d["text"]) for d in decisions if d["decision"] == "demote"]
    parts = re.split(r"(<!-- page \d+ -->)", text)
    done = set()
    for i in range(1, len(parts), 2):
        page = int(ANCHOR.fullmatch(parts[i])[1])
        lines = parts[i + 1].split("\n")
        for j, line in enumerate(lines):
            m = HEADING.match(line) or BOLD_HEADING.match(line.strip())
            if not m:
                continue
            heading = m[m.lastindex].replace("**", "")
            hit = next((t for t in todo if t[0] == page and heading.startswith(t[1])), None)
            if hit:
                lines[j] = heading
                done.add(hit)
        parts[i + 1] = "\n".join(lines)
    if missing := [t for t in todo if t not in done]:
        raise ValueError(f"no heading matches {missing}")
    return "".join(parts), len(done)
