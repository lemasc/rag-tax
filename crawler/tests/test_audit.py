"""Extraction-coverage measures: unit behaviour, plus one regression pin on the known truncation (needs data/raw)."""

import pytest

from crawler.clean.audit import number_recall, page_coverage, recall
from conftest import DATA


def test_recall_counts_missing_characters():
    assert recall("abcd", "abcd") == 1
    assert recall("abcd", "ab") == pytest.approx(0.5)
    assert recall("ab cd", "dcba") == 1  # a multiset measure: order is not judged


def test_number_recall_ignores_thai_digit_form_and_flags_lost_amounts():
    assert number_recall("๖๐,๐๐๐ บาท", "60,000 บาท") == 1
    assert number_recall("60,000 และ 120,000", "60,000") == pytest.approx(0.5)


def test_no_page_has_a_missing_content_paragraph():
    # 60061 used to lose the last paragraph of item 4 (fixed in parse._wrap_bare_inline). What may still be missing
    # from every page is chrome: counters, "Untitled Document", the call-centre blurb, ...
    if not (DATA / "raw" / "60061.html").exists():
        pytest.skip("data/raw not available")
    rows = {r["doc_id"]: r for r in page_coverage(DATA / "pages.jsonl", DATA / "raw")}
    assert not any("กรณีสามีหรือภริยาของผู้มีเงินได้ได้จ่ายเงินสมทบ" in s for s in rows["60061"]["missing_fragments"])
    assert rows["60061"]["char_recall"] > 0.99
