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


def test_65908_text_is_the_corrected_one():
    # the OCR output lost "ส่วนตัว 60,000", invented a 100,000 limit for the CCTV row and duplicated a donation row
    text = (images.TEXT / "65908_0_lodyon68_update.md").read_text(encoding="utf-8")
    assert "- ส่วนตัว: 60,000 บาท" in text
    cctv = next(ln for ln in text.split("\n") if "CCTV" in ln)
    assert "100,000" not in cctv and "เพิ่ม 1 เท่าตามที่จ่ายจริง" in cctv
    assert sum("สถานพยาบาลของรัฐ" in ln for ln in text.split("\n")) == 1
    assert images.load_decisions()["65908_0_lodyon68_update"]["source"] == "manual"


def test_export_never_overwrites_a_manual_text(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "TEXT", tmp_path)
    monkeypatch.setattr(images, "load_decisions", lambda: {
        "a": dict(image_id="a", decision="keep", source="manual", verified=""),
        "b": dict(image_id="b", decision="keep", source="ocr", verified=""),
        "c": dict(image_id="c", decision="drop", source="ocr", verified="")})
    monkeypatch.setattr(images, "ocr_text", lambda i: f"ocr {i}")
    (tmp_path / "a.md").write_text("corrected\n", encoding="utf-8")
    assert images.export_kept() == ["b"]
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "corrected\n"
    assert (tmp_path / "b.md").read_text(encoding="utf-8") == "ocr b\n" and not (tmp_path / "c.md").exists()


def test_decisions_without_the_new_columns_default_to_ocr_and_unverified(tmp_path, monkeypatch):
    path = tmp_path / "d.csv"
    path.write_text("image_id,decision,title,note,decided_at\nx,keep,,,2026-10-18\n", encoding="utf-8")
    monkeypatch.setattr(images, "DECISIONS", path)
    assert images.load_decisions()["x"]["source"] == "ocr" and images.load_decisions()["x"]["verified"] == ""
