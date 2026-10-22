"""html_table_to_markdown() and apply_table_decisions(): every HTML table in OCR text has an explicit decision."""

import json

import pytest

from conftest import DATA
from crawler.clean.tables import apply_table_decisions, html_table_to_markdown

SIMPLE = "<table><tr><td>ปี</td><td>1 ปี</td></tr><tr><td>ร้อยละ</td><td>92</td></tr></table>"


def row(page, table, action, doc="d"):
    return dict(doc=doc, page=str(page), table=str(table), action=action, note="")


def test_simple_table_becomes_markdown_with_the_first_row_as_header():
    assert html_table_to_markdown(SIMPLE) == "| ปี | 1 ปี |\n| --- | --- |\n| ร้อยละ | 92 |"


def test_cells_are_one_line_and_pipes_are_escaped():
    t = "<table><tr><th>a</th><th>b</th></tr><tr><td>1. x\n2. y<br/>z</td><td>p|q &amp; r</td></tr></table>"
    assert html_table_to_markdown(t).split("\n")[2] == "| 1. x 2. y z | p\\|q & r |"


@pytest.mark.parametrize("table", [
    '<table><tr><th colspan="2">t</th></tr><tr><td>a</td><td>b</td></tr></table>',
    '<table><tr><td rowspan="2">a</td><td>b</td></tr><tr><td>c</td></tr></table>',
    "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>",
    "<table></table>",
])
def test_complex_or_ragged_tables_are_refused(table):
    with pytest.raises(ValueError):
        html_table_to_markdown(table)


def test_span_of_one_is_a_plain_cell():
    assert html_table_to_markdown('<table><tr><td colspan="1">a</td></tr></table>') == "| a |\n| --- |"


def test_decisions_apply_per_page_and_table_number(tmp_path):
    text = f"x\n{SIMPLE}\n<!-- page 2 -->\n{SIMPLE}\n{SIMPLE}"
    (tmp_path / "page-02-table-2.md").write_text("| hand | made |\n| --- | --- |\n", encoding="utf-8")
    out = apply_table_decisions(text, [row(0, 1, "convert"), row(2, 1, "keep"), row(2, 2, "manual")], tmp_path)
    parts = out.split("<!-- page 2 -->")
    assert parts[0] == "x\n| ปี | 1 ปี |\n| --- | --- |\n| ร้อยละ | 92 |\n"
    assert parts[1] == f"\n{SIMPLE}\n| hand | made |\n| --- | --- |"


def test_a_table_with_no_decision_fails(tmp_path):
    with pytest.raises(ValueError, match="no row"):
        apply_table_decisions(f"<!-- page 1 -->\n{SIMPLE}\n{SIMPLE}", [row(1, 1, "convert")], tmp_path)


def test_a_decision_with_no_table_fails(tmp_path):
    with pytest.raises(ValueError, match="no table matches"):
        apply_table_decisions(f"<!-- page 1 -->\n{SIMPLE}", [row(1, 1, "convert"), row(1, 2, "convert")], tmp_path)
    with pytest.raises(ValueError, match="no table matches"):
        apply_table_decisions("no tables here", [row(0, 1, "keep")], tmp_path)


def test_convert_of_a_complex_table_and_a_missing_manual_file_fail(tmp_path):
    complex_ = '<table><tr><th colspan="2">t</th></tr></table>'
    with pytest.raises(ValueError, match="cannot be converted"):
        apply_table_decisions(complex_, [row(0, 1, "convert")], tmp_path)
    with pytest.raises(ValueError, match="is missing"):
        apply_table_decisions(SIMPLE, [row(0, 1, "manual")], tmp_path)


def test_built_corpus_has_no_unreviewed_html_table():
    path = DATA / "clean" / "documents.jsonl"
    if not path.exists():
        pytest.skip("data/clean not built")
    for line in path.open(encoding="utf-8"):
        d = json.loads(line)
        assert ("<table" in d["text"]) == ("html_table" in d["flags"]), d["doc_id"]
