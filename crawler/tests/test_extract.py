"""extract.normalise(): OCR page anchors survive, failed-page marks and figure captions do not."""

from crawler.extract import normalise


def test_page_anchors_kept():
    t = normalise("<!-- page 1 -->\n\nข้อ ๑ ก\n\n<!-- page 2 -->\n\nข้อ ๒ ข")
    assert "<!-- page 1 -->" in t and "<!-- page 2 -->" in t
    assert "ข้อ 1 ก" in t  # Thai digits still converted


def test_failed_page_and_figure_dropped():
    t = normalise("<!-- page 3: OCR FAILED -->\n<figure>emblem</figure>\nข้อ ๑")
    assert "OCR FAILED" not in t and "emblem" not in t


def test_idempotent():
    s = "<!-- page 1 -->\n\nข้อ ๑ ก\n\n<!-- page 2 -->\n\nข้อ ๒ ข"
    assert normalise(normalise(s)) == normalise(s)


def test_html_text_breaks_lines_at_br_and_blocks(tmp_path):
    page = tmp_path / "x.html"
    page.write_text(
        '<html><head><meta charset="utf-8"></head><body><div class="col-main"><p>ข้อ 1 ให้ยกเลิก<br>(1) กฎกระทรวง\n  ฉบับที่ 110<br />(2) กฎกระทรวง ฉบับที่ 124</p>'
        "<p>สั่ง ณ วันที่ 7 กุมภาพันธ์ พ.ศ. 2543</p><div>ร้อยเอก ก</div>ท้าย<script>x()</script></div></body></html>",
        encoding="utf-8")
    from crawler.extract import html_text

    lines = [ln for ln in html_text(page).split("\n") if ln]
    assert lines == ["ข้อ 1 ให้ยกเลิก", "(1) กฎกระทรวง ฉบับที่ 110", "(2) กฎกระทรวง ฉบับที่ 124", "สั่ง ณ วันที่ 7 กุมภาพันธ์ พ.ศ. 2543", "ร้อยเอก ก", "ท้าย"]
