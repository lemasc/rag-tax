"""HTML tables in OCR text: one explicit decision per table.

Typhoon OCR writes a table as HTML on a single line. Left alone, the chunker cuts a long one at spaces mid-table, so
later parts lose the column headers and the markup breaks. Converting every table by rule would silently mangle the
complex ones (colspan, rowspan, a form whose blank cells the filer fills in, two column-pairs side by side), and
trafilatura already converted the tables on web pages without anyone checking them (docs/plans/cleaning-open-items.md).
So every table in a guide's OCR or an image's text is listed in data/table_decisions.csv (doc, page, table, action, note):

- convert: mechanical HTML -> markdown by `html_table_to_markdown`; only for a simple grid without colspan/rowspan
- manual : replaced by the hand-written markdown in data/table_overrides/<doc>/page-NN-table-K.md (`table-K.md` for an
           image, which has no pages), written after reading the table on the source page
- keep   : the HTML stays; the document gets the flag `html_table`

`page` is the PDF page of the `<!-- page N -->` anchor (0 for an image) and `table` counts the tables on it from 1, in
the text as `replace_pages` leaves it. A decision that matches no table, and a table with no decision, are errors,
like an override for a page that is not there: a changed OCR must not skip or misplace a table silently.
"""

import html
import re
from html.parser import HTMLParser
from pathlib import Path

from crawler.clean.pages import ANCHOR

TABLE = re.compile(r"<table\b.*?</table>", re.S | re.I)
ACTIONS = ("convert", "manual", "keep")


class _Grid(HTMLParser):
    """Collect the rows of one table as lists of cell texts; refuse anything that is not a plain grid."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None
        self._tables = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self._tables += 1
            if self._tables > 1:
                raise ValueError("nested table")
        elif tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th"):
            for name, value in attrs:
                if name in ("colspan", "rowspan") and (value or "1").strip() != "1":
                    raise ValueError(f"{name}={value} needs a manual table")
            if not self.rows:
                raise ValueError("cell outside a row")
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._cell is not None:
            self.rows[-1].append(" ".join("".join(self._cell).split()))
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def html_table_to_markdown(table: str) -> str:
    """A simple HTML table -> a markdown table whose header is the first row. Raises ValueError for colspan/rowspan, a
    nested table or rows with different numbers of cells: those need a hand-written table, not a guess."""
    grid = _Grid()
    grid.feed(table)
    grid.close()
    rows = [r for r in grid.rows if r]
    if not rows:
        raise ValueError("table has no cells")
    if len({len(r) for r in rows}) != 1:
        raise ValueError(f"rows have {sorted({len(r) for r in rows})} cells")
    if grid._cell is not None:
        raise ValueError("unclosed cell")

    def cell(text: str) -> str:
        return html.unescape(text).replace("|", "\\|")

    lines = ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join([lines[0], "| " + " | ".join("---" for _ in rows[0]) + " |"] + lines[1:])


def apply_table_decisions(text: str, decisions: list[dict], overrides: Path) -> str:
    """Replace each HTML table in raw OCR text as `decisions` (one document's rows of data/table_decisions.csv: page,
    table, action) say; manual tables are read from `overrides` (the document's folder). Text without page anchors is
    page 0. Run on the raw text, before `normalize`, so a replacement gets the same cleaning as the OCR it replaces."""
    todo = {(int(d["page"]), int(d["table"])): d for d in decisions}
    if len(todo) != len(decisions):
        raise ValueError("table_decisions.csv: a table is listed twice")
    for d in decisions:
        if d["action"] not in ACTIONS:
            raise ValueError(f"table_decisions.csv: unknown action {d['action']!r} ({d['doc']} p{d['page']} #{d['table']})")
    parts = re.split(r"(<!-- page \d+ -->)", text)
    seen: set[tuple[int, int]] = set()
    unlisted = []
    for i in range(0, len(parts), 2):
        page = int(ANCHOR.fullmatch(parts[i - 1])[1]) if i else 0
        count = 0

        def decide(m: re.Match) -> str:
            nonlocal count
            count += 1
            d = todo.get((page, count))
            if d is None:
                unlisted.append((page, count, " ".join(re.sub(r"<[^>]+>", " ", m[0]).split())[:50]))
                return m[0]
            seen.add((page, count))
            if d["action"] == "keep":
                return m[0]
            if d["action"] == "convert":
                try:
                    return html_table_to_markdown(m[0])
                except ValueError as e:
                    raise ValueError(f"table_decisions.csv: {d['doc']} p{page} #{count} cannot be converted: {e}") from e
            name = f"page-{page:02d}-table-{count}.md" if page else f"table-{count}.md"
            path = overrides / name
            if not path.exists():
                raise ValueError(f"table_decisions.csv: {d['doc']} p{page} #{count} is manual but {path} is missing")
            md = path.read_text(encoding="utf-8").strip("\n")
            if "<table" in md or not md.strip():
                raise ValueError(f"{path} is empty or still has an HTML table")
            return md

        parts[i] = TABLE.sub(decide, parts[i])
    if missing := sorted(set(todo) - seen):
        raise ValueError(f"table_decisions.csv: no table matches (page, table) {missing}")
    if unlisted:
        raise ValueError(f"HTML tables with no row in table_decisions.csv (page, table, start): {unlisted}")
    return "".join(parts)
