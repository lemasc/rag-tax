"""normalize(): character-level cleaning. Real-corpus cases name their source."""

import csv
import re

import pytest

from crawler.clean.text import normalize
from conftest import DATA


def test_idempotent():
    s = "a\xa0b<br />c &amp; \x93x\x94 ​z ๑๒"
    assert normalize(normalize(s)) == normalize(s)


def test_cp1252_quotes_are_restored_not_dropped():
    # amending instruments wrap the replacement clause in \x93 ... \x94 (38 legal files, e.g. rd.go.th/2502.html)
    assert normalize("แทน \x93(4) ต้องใช้\x94 ข้อ 2") == "แทน “(4) ต้องใช้” ข้อ 2"


def test_whitespace_and_invisible_characters():
    assert normalize("a\xa0\xa0b ​ c\t\td  \n\n\n\n e") == "a b c d\n\ne"


def test_thai_digits_become_ascii():
    assert normalize("มาตรา ๔๗ (๑)") == "มาตรา 47 (1)"


def test_sara_am_recombined():
    assert normalize("กํา") == "กำ"


def test_leaked_br_tag_splits_question_from_answer(page_text):
    # 60055 item 7 has a literal "<br />" between คำถาม and คำตอบ in the source
    t = page_text("60055")
    assert "<br" not in t
    assert re.search(r"ได้หรือไม่\nคำตอบ :", t)


def test_entities():
    assert normalize("A &amp; B &nsbp;C") == "A & B C"


def test_cp1252_repair_covers_every_legal_file():
    # \x93/\x94 appear in 38 legal files (169 characters); each must come out as a curly quote, none left behind.
    # (Quote balance is not asserted: the source itself mixes “ ” and ", and 13481.html closes a quote with “.)
    n = 0
    for r in csv.DictReader((DATA / "legal_text.csv").open(encoding="utf-8")):
        if r["status"] != "ok":
            continue
        raw = (DATA / "text" / "legal" / r["file"]).read_text(encoding="utf-8")
        t = normalize(raw)
        assert not re.search(r"[\x80-\x9f]", t), r["url"]
        assert t.count("“") - raw.count("“") == raw.count("\x93"), r["url"]
        n += raw.count("\x93") + raw.count("\x94")
    assert n == 169


def test_replacement_characters_become_spaces(pages):
    # U+FFFD comes from the source HTML: 20 in 61065 (where its duplicate 61081 has a space), 1 in 61117
    assert normalize("A7 :� 1.") == "A7 : 1."
    assert not any("�" in normalize(p["text"] or "") for p in pages.values())


def test_drop_empty_cells_keeps_a_cell_that_holds_a_column():
    from crawler.clean.text import drop_empty_cells

    html = "<tr><td>a</td><td></td><td>b</td></tr>\n<tr><td></td><td></td></tr>\n<tr><td>c</td><td></td><td></td><td></td><td></td></tr>"
    assert drop_empty_cells(html) == "<tr><td>a</td><td></td><td>b</td></tr>\n<tr><td>c</td></tr>"


def test_drop_page_numbers_removes_only_the_marker_line():
    from crawler.clean.text import drop_page_numbers

    assert drop_page_numbers("ก\n<page_number>10</page_number>\nข\n  <page_number> 3 </page_number>\nค") == "ก\nข\nค"
