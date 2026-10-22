"""rag.chunk: packing invariants on synthetic text (characters as tokens), and the built chunk table."""

import hashlib
import json
from pathlib import Path

import pytest

from rag.chunk import MAX_TOKENS, TOKENIZER, WINDOW_TOKENS, hard_cut, make_chunks, split

CHUNKS = Path(__file__).parent.parent / "out" / "chunks.jsonl"
CLEAN = Path(__file__).parent.parent.parent / "crawler" / "data" / "clean"
FREEZE = Path(__file__).parent.parent / "chunks_freeze.json"


def squash(s: str) -> str:
    return "".join(s.split())


def test_split_fits_and_loses_no_text():
    text = "ข้อ 1 ผู้มีเงินได้\n" + "ก" * 25 + "\n\n" + " ".join(["คำ"] * 20) + "\nท้าย"
    parts = split(text, 10, len)
    assert all(len(p) <= 10 for p in parts)
    assert squash("".join(parts)) == squash(text)


def test_split_packs_short_paragraphs_together():
    assert split("ab\ncd\nef", 5, len) == ["ab\ncd", "ef"]


def test_hard_cut_takes_longest_prefixes():
    assert hard_cut("abcdefg", 3, len) == ["abc", "def", "g"]


def test_split_table_parts_repeat_the_header_row_and_separator():
    head = "| ลำดับ | ชื่อ |\n| --- | --- |"
    rows = [f"| {i} | พรรค{i} |" for i in range(1, 9)]
    text = "ก่อนตาราง\n" + head + "\n" + "\n".join(rows) + "\nหลังตาราง"
    parts = split(text, 60, len)
    assert len(parts) > 2 and all(len(p) <= 60 for p in parts)
    assert parts[0].startswith("ก่อนตาราง\n" + head)
    later = [p for p in parts[1:] if p.startswith("|")]
    assert later and all(p.startswith(head + "\n| ") for p in later)
    body = [ln for p in parts for ln in p.split("\n") if ln not in head.split("\n") and ln.startswith("| ")]
    assert body == rows  # every row once, in order
    assert parts[-1].endswith("หลังตาราง")


def test_split_gives_prose_after_a_table_no_header():
    text = "| a | b |\n| --- | --- |\n| 1 | 2 |\n" + "\n".join(["ข้อความหลังตารางยาวๆ"] * 6)
    parts = split(text, 40, len)
    assert len(parts) > 2 and parts[0].startswith("| a | b |\n| --- | --- |\n| 1 | 2 |")
    assert all("| a |" not in p for p in parts[1:])


def doc(doc_id, include=True, text="", preamble=""):
    return dict(doc_id=doc_id, include=include, source="page", kind="faq", title="T", url="u", tax_year=None,
                flags=[], text=text, preamble=preamble)


def unit(unit_id, text, include=True):
    return dict(unit_id=unit_id, doc_id=unit_id.split("#")[0], type="faq", label="Q1", section=None, title=None,
                text=text, include=include)


def test_units_stay_whole_and_excluded_records_are_skipped():
    docs = [doc("a"), doc("b", include=False)]
    units = [unit("a#001", "Q1 : ถาม\nA1 : ตอบ"), unit("a#002", "x", include=False), unit("b#001", "y")]
    chunks = list(make_chunks(docs, units, len))
    assert [(c["chunk_id"], c["text"], c["header"]) for c in chunks] == [("a#001", "Q1 : ถาม\nA1 : ตอบ", "T | Q1")]


def test_split_faq_parts_repeat_the_question_in_the_header(monkeypatch):
    monkeypatch.setattr("rag.chunk.MAX_TOKENS", 60)
    body = "Q1 : ถามอะไร\nA1 : " + "\n".join(["ตอบยาวมาก" * 3] * 6)
    chunks = list(make_chunks([doc("a")], [unit("a#001", body)], len))
    assert len(chunks) > 1 and all(c["n_tokens"] <= 60 for c in chunks)
    assert chunks[0]["header"] == "T | Q1" and all(c["header"] == "T | Q1 | Q1 : ถามอะไร" for c in chunks[1:])
    assert squash("".join(c["text"] for c in chunks)) == squash(body)


@pytest.fixture(scope="module")
def built():
    if not CHUNKS.exists():
        pytest.skip("rag/out/chunks.jsonl not built")
    return [json.loads(line) for line in CHUNKS.open(encoding="utf-8")]


def test_built_chunks_respect_the_cap_and_are_unique(built):
    assert max(c["n_tokens"] for c in built) <= MAX_TOKENS
    assert len({c["chunk_id"] for c in built}) == len(built)


def test_built_chunks_cover_exactly_the_included_units(built):
    docs = {d["doc_id"]: d for d in map(json.loads, (CLEAN / "documents.jsonl").open(encoding="utf-8"))}
    units = [json.loads(line) for line in (CLEAN / "units.jsonl").open(encoding="utf-8")]
    want = {u["unit_id"] for u in units if u["include"] and docs[u["doc_id"]]["include"]}
    assert {c["unit_id"] for c in built if c["unit_id"]} == want
    assert {c["doc_id"] for c in built} == {d for d, r in docs.items() if r["include"]}


def test_built_chunks_are_the_frozen_ones():
    """Qrels key on chunk ids, so the chunk table changes only on purpose: regenerate, re-map the qrels, update the freeze."""
    if not CHUNKS.exists():
        pytest.skip("rag/out/chunks.jsonl not built")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    assert (TOKENIZER, MAX_TOKENS, WINDOW_TOKENS) == (freeze["tokenizer"], freeze["max_tokens"], freeze["window_tokens"])
    assert hashlib.sha256(CHUNKS.read_bytes()).hexdigest() == freeze["sha256"], "chunks.jsonl differs from rag/chunks_freeze.json"
