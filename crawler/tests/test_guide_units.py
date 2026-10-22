"""split_guide(): heading sections of the Typhoon-OCR filling guides (ภ.ง.ด.90/91/94)."""

import pytest

from conftest import DATA
from crawler.clean.units import GUIDE_MIN_CHARS, split_guide

BODY = "ก" * (GUIDE_MIN_CHARS + 10)


def test_sections_follow_headings_and_carry_the_trail():
    text = f"# หัวเรื่อง\n{BODY}\n## ส่วน 1\n{BODY}\n### ย่อย 1.1\n{BODY}\n## ส่วน 2\n{BODY}"
    pre, units = split_guide("d", text)
    assert pre == ""
    assert [(u.unit_id, u.label, u.section) for u in units] == [
        ("d#001", "หัวเรื่อง", None),
        ("d#002", "ส่วน 1", "หัวเรื่อง"),
        ("d#003", "ย่อย 1.1", "หัวเรื่อง > ส่วน 1"),
        ("d#004", "ส่วน 2", "หัวเรื่อง"),
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
    assert [u.section for u in units if u.label == "หักค่าใช้จ่าย"] == ["ข > ข้อ 3 ก", "ข > ข้อ 4 ข"]


def test_short_sections_join_the_next_and_a_short_last_joins_the_one_before():
    text = f"## ก\nสั้น\n## ข\n{BODY}\n## ค\nท้าย"
    _, units = split_guide("d", text)
    assert [u.label for u in units] == ["ก"]
    assert units[0].text == f"สั้น\n## ข\n{BODY}\n## ค\nท้าย"  # nothing is dropped, later headings stay as lines


def test_text_before_the_first_heading_is_the_preamble():
    pre, units = split_guide("d", f"ภ.ง.ด.90\n## ก\n{BODY}")
    assert pre == "ภ.ง.ด.90" and len(units) == 1


@pytest.mark.parametrize("stem", ["Ins90_241268", "Ins91_241268", "Ins94_050668"])
def test_real_guides_lose_no_text(stem):
    path = DATA / "raw" / "pit2568" / "ocr" / f"{stem}.md"
    if not path.exists():
        pytest.skip("OCR cache not available (data/raw is not checked in)")
    from crawler.clean.build import drop_empty_cells, normalize, rejoin, take_page_anchors
    text, _ = take_page_anchors(rejoin(drop_empty_cells(normalize(path.read_text(encoding="utf-8"))))[0])
    pre, units = split_guide(stem, text)
    assert len(units) > 10
    assert sum(len(u.text) for u in units) + len(pre) >= 0.95 * len(text)  # headings are the only text left out of unit bodies
    assert all(len(u.text) >= GUIDE_MIN_CHARS for u in units)
