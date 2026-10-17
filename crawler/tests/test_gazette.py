"""strip_page_headers(): Royal Gazette page furniture in PDF-derived text. Real cases name their source file."""

import csv

import pytest

from crawler.clean.gazette import NUMBERING, PAGE, strip_page_headers
from crawler.clean.text import normalize
from conftest import DATA


def cleaned(name: str):
    """(cleaned text, gazette_date, removed) for a legal file by the basename of its URL."""
    for r in csv.DictReader((DATA / "legal_text.csv").open(encoding="utf-8")):
        if r["status"] == "ok" and r["url"].endswith("/" + name):
            return strip_page_headers(normalize((DATA / "text" / "legal" / r["file"]).read_text(encoding="utf-8")))
    pytest.skip(f"{name} not in legal_text.csv")


def test_first_date_is_kept_as_metadata_and_repeats_are_dropped():
    text = "8 ธันวาคม 2566\n\nกฎกระทรวง\n\nข้อ 1 ก\n\n8 ธันวาคม 2566\n\nข้อ 2 ข\n\n8 ธันวาคม 2566\n\nให้ไว้"
    out, date, removed = strip_page_headers(text)
    assert date == "8 ธันวาคม 2566"
    assert out.count("8 ธันวาคม 2566") == 1 and out.startswith("8 ธันวาคม 2566")
    assert removed == ["8 ธันวาคม 2566"] * 2
    assert "\n\n\n" not in out


def test_a_different_standalone_date_is_left_alone():
    out, date, removed = strip_page_headers("5 เมษายน 2567\nข้อ 1\n6 เมษายน 2567\nข้อ 2")
    assert date == "5 เมษายน 2567" and removed == [] and "6 เมษายน 2567" in out


def test_a_date_inside_a_sentence_is_not_a_header():
    text = "ให้ไว้ ณ วันที่ 8 ธันวาคม พ.ศ. 2566\nใช้บังคับตั้งแต่ 8 ธันวาคม 2566 เป็นต้นไป"
    assert strip_page_headers(text) == (text, None, [])


@pytest.mark.parametrize("line", ["เลม่ 136 ตอนที่ 79 ก", "เล่ม 134 ตอนพิเศษ 97 ง", "หน้า 3 ราชกิจจานุเบกษา", "หน้า 12"])
def test_header_shapes(line):
    assert NUMBERING.match(line) or PAGE.match(line)


def test_content_that_mentions_the_gazette_is_kept():
    text = "ให้ใช้บังคับตั้งแต่วันถัดจากวันประกาศในราชกิจจานุเบกษาเป็นต้นไป"
    assert strip_page_headers(text) == (text, None, [])


def test_pdftotext_tone_mark_misorder_mr350():
    # mr350.pdf: "เลม่ 136 ตอนที่ 79 ก" at the top of both pages; the earlier stripper only knew "เล่ม"
    out, date, removed = cleaned("mr350.pdf")
    assert [l for l in removed if l.startswith("เลม่")] == ["เลม่ 136 ตอนที่ 79 ก"] * 2
    assert "เลม่" not in out and date == "25 มิถุนายน 2562" and out.count(date) == 1


def test_ocr_keeps_page_line_mr396():
    # mr396.pdf (OCR): "หน้า 3 ราชกิจจานุเบกษา" survived, and the date repeats on every page (3 pages)
    out, date, removed = cleaned("mr396.pdf")
    assert "หน้า 3 ราชกิจจานุเบกษา" in removed
    assert date == "20 ธันวาคม 2567" and out.count(date) == 1 and removed.count(date) == 2


def test_document_without_headers_is_unchanged():
    # mr397.pdf (OCR, 4 pages) has no standalone date line at all
    out, date, removed = cleaned("mr397.pdf")
    assert date is None and removed == []


def test_no_header_line_survives_in_any_pdf_derived_document():
    leftovers = []
    for r in csv.DictReader((DATA / "legal_text.csv").open(encoding="utf-8")):
        if r["status"] != "ok" or r["method"] not in ("pdftotext", "ocr"):
            continue
        out, _, _ = strip_page_headers(normalize((DATA / "text" / "legal" / r["file"]).read_text(encoding="utf-8")))
        leftovers += [(r["url"], l) for l in out.split("\n") if NUMBERING.match(l.strip()) or PAGE.match(l.strip())]
    assert not leftovers, leftovers
