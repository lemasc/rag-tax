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
