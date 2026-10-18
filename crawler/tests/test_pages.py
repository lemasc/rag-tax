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
    ocr = [d for d in docs if d.get("text_method") == "ocr"]
    assert ocr, "no OCR documents"
    for d in ocr:
        assert "<!-- page" not in d["text"], d["doc_id"]
        starts = [s for _, s in d["pages"]]
        assert starts[0] == 0 and starts == sorted(starts) and starts[-1] < len(d["text"]), d["doc_id"]
        assert [p for p, _ in d["pages"]] == list(range(1, len(d["pages"]) + 1)), d["doc_id"]
