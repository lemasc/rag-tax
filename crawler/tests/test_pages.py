"""take_page_anchors() and page_of(): OCR page anchors become offsets into the cleaned text."""

import json

import pytest

from crawler.clean.pages import page_of, take_page_anchors
from conftest import DATA


def test_anchors_removed_and_offsets_point_at_content():
    text = "<!-- page 1 -->\n\nก ข\nค\n\n<!-- page 2 -->\n\nง จ"
    out, pages = take_page_anchors(text)
    assert out == "ก ข\nค\n\nง จ"
    assert pages == [[1, 0], [2, out.index("ง")]]


def test_no_anchors_is_unchanged():
    assert take_page_anchors("ก ข\nค") == ("ก ข\nค", None)


def test_page_of():
    out, pages = take_page_anchors("<!-- page 1 -->\nก\n<!-- page 2 -->\nข\n<!-- page 3 -->\nค")
    assert [page_of(pages, out.index(c)) for c in "กขค"] == [1, 2, 3]
    assert page_of(None, 0) is None


def test_ocr_documents_in_the_built_corpus():
    path = DATA / "clean" / "documents.jsonl"
    if not path.exists():
        pytest.skip("data/clean not built")
    docs = [json.loads(l) for l in path.open(encoding="utf-8")]
    ocr = [d for d in docs if d["source"] == "legal" and d["text_method"] == "ocr"]
    assert ocr, "no OCR documents"
    for d in ocr:
        assert "<!-- page" not in d["text"], d["doc_id"]
        starts = [s for _, s in d["pages"]]
        assert starts[0] == 0 and starts == sorted(starts) and starts[-1] < len(d["text"]), d["doc_id"]
        assert [p for p, _ in d["pages"]] == list(range(1, len(d["pages"]) + 1)), d["doc_id"]


def test_replace_pages_swaps_one_pages_content_and_keeps_the_anchors():
    from crawler.clean.pages import replace_pages

    text = "<!-- page 1 -->\n\nก\n\n<!-- page 2 -->\n\nข\n\n<!-- page 3 -->\n\nค"
    out, done = replace_pages(text, {2: "ใหม่\n"})
    assert done == [2]
    assert take_page_anchors(out)[0] == "ก\n\nใหม่\n\nค"
    assert [p for p, _ in take_page_anchors(out)[1]] == [1, 2, 3]


def test_replace_pages_fails_on_a_page_the_text_does_not_have():
    from crawler.clean.pages import replace_pages

    with pytest.raises(ValueError, match="7"):
        replace_pages("<!-- page 1 -->\n\nก", {7: "x"})


def test_demote_headings_makes_only_the_decided_headings_plain():
    from crawler.clean.pages import demote_headings

    text = "<!-- page 1 -->\n\n# 9. ก\n\n### 10.1 ข ยาว\n\n**10.2 ค**\n\n<!-- page 2 -->\n\n### 10.1 ข ยาว"
    rows = [dict(page="1", text="10.1 ข", decision="demote"), dict(page="1", text="10.2", decision="demote"),
            dict(page="1", text="9.", decision="keep")]
    out, n = demote_headings(text, rows)
    assert n == 2
    assert out == "<!-- page 1 -->\n\n# 9. ก\n\n10.1 ข ยาว\n\n10.2 ค\n\n<!-- page 2 -->\n\n### 10.1 ข ยาว"  # page 2 untouched


def test_demote_headings_fails_on_a_row_that_matches_nothing():
    from crawler.clean.pages import demote_headings

    with pytest.raises(ValueError, match="10.9"):
        demote_headings("<!-- page 1 -->\n\n# ก", [dict(page="1", text="10.9", decision="demote")])
