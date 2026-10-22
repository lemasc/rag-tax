"""split_guide(): heading sections of the Typhoon-OCR filling guides (ภ.ง.ด.90/91/94)."""

import pytest

from conftest import DATA
from crawler.clean.units import GUIDE_MIN_CHARS, split_guide

BODY = "ก" * (GUIDE_MIN_CHARS + 10)


def test_sections_follow_headings_and_carry_the_trail():
    text = f"## ข้อ 1 ก\n{BODY}\n### 1. ข\n{BODY}\n#### 1.1 ค\n{BODY}\n## ข้อ 2 ง\n{BODY}"
    pre, units = split_guide("d", text)
    assert pre == ""
    assert [(u.unit_id, u.label, u.section) for u in units] == [
        ("d#001", "ข้อ 1 ก", None),
        ("d#002", "1. ข", "ข้อ 1 ก"),
        ("d#003", "1.1 ค", "ข้อ 1 ก > 1. ข"),
        ("d#004", "ข้อ 2 ง", None),
    ]
    assert all(u.type == "guide" and u.text == BODY for u in units)


def test_bold_only_lines_are_headings_but_bold_in_a_sentence_is_not():
    text = f"## ก\n**ข้อ 4 รายการ**\n{BODY}\nข้อความ **ตัวหนา** ในประโยค\n"
    _, units = split_guide("d", text)
    assert [u.label for u in units] == ["ก"]  # the empty heading takes in the section after it
    assert "**ข้อ 4 รายการ**" in units[0].text and "**ตัวหนา**" in units[0].text


def test_item_headings_are_peers_whatever_the_ocr_marked():
    text = f"# ข\n## ข้อ 3 ก\n{BODY}\n### หักค่าใช้จ่าย\n{BODY}\n**ข้อ 4 ข**\n{BODY}\n#### หักค่าใช้จ่าย\n{BODY}"
    _, units = split_guide("d", text)
    assert [u.section for u in units if u.label == "หักค่าใช้จ่าย"] == ["ข้อ 3 ก", "ข้อ 4 ข"]


def test_an_unnumbered_heading_hangs_on_the_nearest_item_not_on_a_numbered_one_and_does_not_swallow_the_items_after_it():
    text = f"# ยกเว้น\n{BODY}\n## ข้อ 2 ก\n{BODY}\n### 2. ข\n{BODY}\n**คำเตือน**\n{BODY}\n## ข้อ 3 ค\n{BODY}"
    _, units = split_guide("d", text)
    assert [(u.label, u.section) for u in units] == [("ยกเว้น", None), ("ข้อ 2 ก", None), ("2. ข", "ข้อ 2 ก"), ("คำเตือน", "ข้อ 2 ก"), ("ข้อ 3 ค", None)]


def test_short_sections_join_the_next_and_a_short_last_joins_the_one_before():
    text = f"## ก\nสั้น\n## ข\n{BODY}\n## ค\nท้าย"
    _, units = split_guide("d", text)
    assert [u.label for u in units] == ["ก"]
    assert units[0].text == f"สั้น\n## ข\n{BODY}\n## ค\nท้าย"  # nothing is dropped, later headings stay as lines


def test_text_before_the_first_heading_is_the_preamble():
    pre, units = split_guide("d", f"ภ.ง.ด.90\n## ก\n{BODY}")
    assert pre == "ภ.ง.ด.90" and len(units) == 1


def test_numbered_headings_are_peers_whatever_the_ocr_marked():
    text = f"## ข้อ 1 ก\n{BODY}\n## 5. ข\n{BODY}\n### 7. ค\n{BODY}\n# 10. ง\n{BODY}\n#### 10.1 จ\n{BODY}"
    _, units = split_guide("d", text)
    assert [(u.label, u.section) for u in units][1:] == [
        ("5. ข", "ข้อ 1 ก"), ("7. ค", "ข้อ 1 ก"), ("10. ง", "ข้อ 1 ก"), ("10.1 จ", "ข้อ 1 ก > 10. ง")]


def test_a_long_section_is_cut_at_its_own_decimal_items_only():
    item = lambda n: f"7.{n} ข้อ {n}\n{BODY}\n\n"
    text = f"## 7. เบี้ย\nนำ\n\n{item(1)}{item(2)}1.5 เท่า ของเงินได้\n{BODY * 8}\n\n{item(3)}"
    _, units = split_guide("d", text)
    assert [u.label for u in units] == ["7. เบี้ย", "7.2 ข้อ 2", "7.3 ข้อ 3"]  # 7.1 follows the intro lines, "1.5" is no item
    assert units[1].section == "7. เบี้ย" and "1.5 เท่า" in units[1].text and units[0].text.startswith("นำ")


def test_a_long_section_without_a_number_in_its_label_stays_whole():
    _, units = split_guide("d", f"## ก การคำนวณ\n7.1 ก\n{BODY * 8}\n7.2 ข\n{BODY}")
    assert len(units) == 1


@pytest.mark.parametrize("stem", ["Ins90_241268", "Ins91_241268", "Ins94_050668"])
def test_real_guides_lose_no_text(stem):
    path = DATA / "text" / "guide" / f"{stem}.md"
    from crawler.clean.build import drop_empty_cells, normalize, rejoin, take_page_anchors
    text, _ = take_page_anchors(rejoin(drop_empty_cells(normalize(path.read_text(encoding="utf-8"))))[0])
    pre, units = split_guide(stem, text)
    assert len(units) > 10
    assert sum(len(u.text) for u in units) + len(pre) >= 0.95 * len(text)  # headings are the only text left out of unit bodies
    assert all(len(u.text) >= GUIDE_MIN_CHARS for u in units)
