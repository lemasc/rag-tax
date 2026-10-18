"""rejoin() and fix_tone_marks(): split Thai words and pdftotext's tone-mark order. Real cases name their source."""

import csv
from collections import Counter

import pytest

from crawler.clean.rejoin import fix_tone_marks, rejoin
from crawler.clean.text import normalize
from conftest import DATA


@pytest.mark.parametrize("before, after", [
    ("ผู้ใ ช้", "ผู้ใช้"),                 # leading vowel cut off (8d6b68bf1ac8, pdftotext)
    ("ก็ได ้คือ", "ก็ได้คือ"),             # tone mark after a space (5937, HTML)
    ("ลงชือ\n่", "ลงชือ่"),                # tone mark wrapped onto the next line (8d6b68bf1ac8)
    ("เสี ยภาษี", "เสียภาษี"),            # fragment on both sides (0d97ab92720d)
    ("รั ษฎากร", "รัษฎากร"),               # e40452566c8d, 887975f1dbb3 (pdftotext)
])
def test_split_words_are_joined(before, after):
    assert rejoin(before)[0] == after


@pytest.mark.parametrize("text", [
    "ราบรื่น\nนอกจากนี้",   # synthetic: sentence break, both sides are words
    "ใน\nการซ่อมแซม",       # 97fdb7a648ca (OCR): wrap at a word boundary, left as a line break
    "แล้ว จะ",              # 6055, 61081 and 7 more pages: newmm alone would join this into "วจะ"
    "นาย ก. นาย ข.",        # 62777: single-letter abbreviations ("นายก" is a word, but not here)
    "อบต. วัด",             # synthetic
    "30 มิถุนายน พ.ศ. 2560",  # synthetic
    "รหัส ผ่า น",           # 8d6b68bf1ac8 (pdftotext), known miss: "ผ่า" is itself a word, so nothing marks the break
])
def test_word_boundaries_are_left_alone(text):
    assert rejoin(text) == (text, [])


def test_join_records_say_why():
    _, joins = rejoin("เสี ยภาษี และ ผู้ใ ช้")
    assert [(j["reason"], j["word"]) for j in joins] == [("fragment", "เสียภาษี"), ("mark", "")]


@pytest.mark.parametrize("before, after", [
    # after sara aa / sara am: หนา้ in 8 pdftotext documents (0d97ab92720d, ...); นำ้ synthetic
    ("หนา้", "หน้า"), ("นำ้", "น้ำ"),
    ("ทีไ่ด", "ที่ได"),                               # after a leading vowel; synthetic
    # after the อ/ย of a diphthong: ลงชือ่ is 8d6b68bf1ac8's "ลงชือ\n่" once rejoined; เปลีย่น synthetic
    ("ลงชือ่", "ลงชื่อ"), ("เปลีย่น", "เปลี่ยน"),
    ("ตัง้", "ตั้ง"), ("ชัน้", "ชั้น"),               # after mai han-akat's final: ตัง้ in 8d6b68bf1ac8; ชัน้ synthetic
])
def test_misplaced_tone_marks(before, after):
    text, fixes = fix_tone_marks(before)
    assert text == after and len(fixes) == 1


@pytest.mark.parametrize("text", ["มีน้ำ", "ที่นี่", "ซึ่ง", "ทั้งนี้", "เปลี่ยน"])  # valid spellings; synthetic
def test_valid_tone_marks_are_left_alone(text):
    assert fix_tone_marks(text) == (text, [])


def test_joins_stay_out_of_clean_text(pages):
    # The rule is meant for pdftotext. In HTML and OCR text it should only ever fire on a stray space before a mark.
    by_method = Counter()
    for pid, p in pages.items():
        for j in rejoin(normalize(p["text"] or ""))[1]:
            by_method["page"] += 1
            assert j["reason"] == "mark", (pid, j)
    for r in csv.DictReader((DATA / "legal_text.csv").open(encoding="utf-8")):
        if r["status"] == "ok":
            joins = rejoin(normalize((DATA / "text" / "legal" / r["file"]).read_text(encoding="utf-8")))[1]
            by_method[r["method"]] += len(joins)
            if r["method"] != "pdftotext":
                assert all(j["reason"] == "mark" for j in joins), (r["url"], joins)
    assert by_method["page"] + by_method["html"] == 5 and by_method["ocr"] == 0, by_method
