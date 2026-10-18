"""crawler.images: overlap checks, and the image documents in the built corpus. Real-corpus cases name their source."""

import json

import pytest

from crawler import images
from conftest import DATA


@pytest.fixture(autouse=True)
def _in_crawler_dir(monkeypatch):
    monkeypatch.chdir(DATA.parent)  # crawler.images resolves data/ relative to the working directory


def test_squash_ignores_markup_punctuation_and_thai_digits():
    assert images.squash("**ลดหย่อน** <b>๖๐,๐๐๐</b> บาท!") == "ลดหย่อน60000บาท"


def test_overlap_of_contained_and_novel_text():
    page = "ผู้มีเงินได้พึงประเมินต้องยื่นแบบแสดงรายการภาษีภายในเดือนมีนาคม"
    corpus = {"p": images.shingles(page), "q": images.shingles("เรื่องอื่นทั้งหมดไม่เกี่ยวกัน")}
    same = images.overlap("* **ผู้มีเงินได้พึงประเมิน** ต้องยื่นแบบแสดงรายการภาษี", corpus, page_id="p")
    assert same["page"] == same["corpus"] == 1.0 and same["best"][0][0] == "p"
    new = images.overlap("ค่าท่องเที่ยวภายในประเทศ 30,000 บาท", corpus, page_id="p")
    assert new["corpus"] < 0.2
    assert images.unmatched_lines("ค่าท่องเที่ยวภายในประเทศ 30,000 บาท\nผู้มีเงินได้พึงประเมินต้องยื่นแบบ", corpus) == ["ค่าท่องเที่ยวภายในประเทศ 30,000 บาท"]


def test_decisions_refer_to_indexed_images():
    if not images.INDEX.exists():
        pytest.skip("data/image_index.csv not available")
    ids = {r["image_id"] for r in images.load_index()}
    assert len(ids) == len(images.load_index()), "image_id must be unique"
    assert set(images.load_decisions()) <= ids
    assert {d["decision"] for d in images.load_decisions().values()} <= {"keep", "drop"}


def test_kept_images_are_documents_in_the_clean_corpus():
    path = DATA / "clean" / "documents.jsonl"
    if not path.exists():
        pytest.skip("data/clean not built")
    docs = {d["doc_id"]: d for d in (json.loads(l) for l in path.open(encoding="utf-8")) if d["source"] == "image"}
    kept = {i for i, d in images.load_decisions().items() if d["decision"] == "keep"}
    assert set(docs) == kept
    for d in docs.values():
        assert d["include"] and d["text"] and "<!-- page" not in d["text"] and d["parent_page"]


def test_65908_poster_is_kept():
    # the page itself is a "Download" hub with 8 characters; the allowance table exists only in the poster
    d = images.load_decisions().get("65908_0_lodyon68_update")
    assert d and d["decision"] == "keep"
