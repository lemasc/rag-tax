"""split_statute(): one unit per มาตรา. Source: rd.go.th/5937 (ม.38-64), cross-checked against its table of contents 2597."""

import re

from crawler.clean.units import SUFFIXES, SECTION, note_type, split_statute

# The TOC glues the suffix to the title ("มาตรา 57 ตรีการถือเงินได้..."), so no word boundary after it here.
TOC_LABEL = re.compile(rf"มาตรา\s*(\d+)(?!\d)(?:\s+({'|'.join(SUFFIXES)}))?")


def test_sections_match_the_table_of_contents(page_text):
    toc = {f"มาตรา {m.group(1)}" + (f" {m.group(2)}" if m.group(2) else "") for m in TOC_LABEL.finditer(page_text("2597"))}
    _, units = split_statute("5937", page_text("5937"))
    got = {u.label for u in units}
    # The TOC also names ม.65 onwards; the page only carries 38-64.
    in_range = {l for l in toc if int(l.split()[1]) <= 64}
    assert got == in_range


def test_sections_are_in_order_and_complete(page_text):
    _, units = split_statute("5937", page_text("5937"))
    assert len(units) == 43
    assert units[0].label == "มาตรา 38" and units[-1].label == "มาตรา 64"
    nums = [int(u.label.split()[1]) for u in units]
    assert nums == sorted(nums)


def test_nothing_lost(page_text):
    text = page_text("5937")
    pre, units = split_statute("5937", text)
    assert pre == ""
    assert "\n".join(u.text for u in units) == text


def test_notes_are_kept_in_text_and_listed_in_metadata(page_text):
    _, units = split_statute("5937", page_text("5937"))
    notes = [n for u in units for n in u.notes]
    assert len(notes) == 282
    assert {t: sum(n["type"] == t for n in notes) for t in ("see", "amendment", "repeal")} == {"see": 160, "amendment": 109, "repeal": 13}
    assert all(n["text"] in u.text for u in units for n in u.notes)  # kept, not stripped
    assert [u.label for u in units if "has_repeal_note" in u.flags] == [
        "มาตรา 39", "มาตรา 42", "มาตรา 57 ตรี", "มาตรา 57 เบญจ", "มาตรา 58", "มาตรา 59"]


def test_note_types():
    assert note_type("( ดูคำสั่งกรมสรรพากร ที่ ป.7/2528 )") == "see"
    assert note_type("( พระราชกำหนดแก้ไขเพิ่มเติม (ฉบับที่ 1) พ.ศ. 2527 ใช้บังคับ 1 ม.ค. 2528 เป็นต้นไป )") == "amendment"
    assert note_type("(20) (ยกเลิกโดย พระราชบัญญัติแก้ไขเพิ่มเติม (ฉบับที่ 26) พ.ศ.2525 มาตรา 5 ตั้งแต่ 28 ส.ค. 2525 เป็นต้นไป)") == "repeal"
    assert note_type("(4) สำหรับเงินสมทบที่ผู้ประกันตนจ่ายเข้ากองทุนประกันสังคม ตามมาตรา 47 (1) (ฌ)") is None  # an item, not a note


def test_cross_reference_at_line_start_is_not_a_heading():
    text = "มาตรา 40 เงินได้\nมาตรา 39 ที่กล่าวข้างต้น\nมาตรา 41 ทวิ ผู้โอน"
    _, units = split_statute("x", text)
    assert [u.label for u in units] == ["มาตรา 40", "มาตรา 41 ทวิ"]


def test_suffix_must_be_a_whole_word():
    # "ฉบับ" starts with the suffix ฉ; it must not be read as "มาตรา 42 ฉ"
    m = SECTION.match("มาตรา 42 ฉบับที่ 3")
    assert m and m.group(2) is None
