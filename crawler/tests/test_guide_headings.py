"""guide_headings: matching OCR headings to the PDF's bold runs, on Thai that the PDF text has damaged."""

from crawler.guide_headings import bold_fraction, ocr_headings, pdf_pages, skeleton

XML = """<pdf2xml><page number="1" height="1" width="1">
<text top="1" left="1" width="1" height="1" font="1"><b>10. ดอกเบี้ยเงินกู้ยืม</b></text>
<text top="2" left="1" width="1" height="1" font="1">ทั่วไปตามหลักเกณฑ์ วิธีการ และเงื่อนไข</text>
<text top="3" left="1" width="1" height="1" font="1"><b>หลักเกณฑ์ วิธีการ และเงื่อนไข</b></text>
</page></pdf2xml>"""


def test_skeleton_keeps_consonants_and_digits_so_damaged_thai_still_matches():
    assert skeleton("กำหนด ๑๐ เดือน") == skeleton("กำาหนด 10 เดือ่น")  # sara am doubled, tone mark displaced in the PDF text


def test_a_heading_whose_text_runs_on_past_the_bold_lead_in_scores_below_a_real_heading():
    page = pdf_pages(XML)[1]
    assert bold_fraction("10. ดอกเบี้ยเงินกู้ยืม", page) == 1.0
    assert 0 < bold_fraction("10. ดอกเบี้ยเงินกู้ยืมจากการกู้ยืมเงินเพื่อซื้อ", page) < 0.8  # the bold lead is a fraction of it


def test_a_phrase_also_used_in_plain_running_text_counts_by_its_bold_occurrence():
    assert bold_fraction("หลักเกณฑ์ วิธีการ และเงื่อนไข", pdf_pages(XML)[1]) == 1.0


def test_ocr_headings_lists_hash_and_bold_only_lines_with_their_page():
    text = "<!-- page 1 -->\n\n# หัวเรื่อง\n\nข้อความ **ตัวหนา** ในประโยค\n\n<!-- page 2 -->\n\n**ข้อ 4 รายการ**\n\n### 10.1 ก"
    assert list(ocr_headings(text)) == [(1, "#", "หัวเรื่อง"), (2, "bold", "ข้อ 4 รายการ"), (2, "###", "10.1 ก")]
