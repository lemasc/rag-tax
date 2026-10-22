"""crawler.clean.build: hand-recorded decisions applied to the built corpus."""

import csv
import json

import pytest

from conftest import DATA
from crawler.clean.build import apply_decisions, apply_relations, text_hash


def test_dropped_documents_and_units_are_excluded_with_their_original():
    docs = [dict(doc_id="a", include=True), dict(doc_id="b", include=True)]
    units = [dict(unit_id="b#001"), dict(unit_id="b#002")]
    apply_decisions(docs, units, [
        dict(id="a", level="doc", decision="drop", duplicate_of="b"),
        dict(id="b#002", level="unit", decision="drop", duplicate_of="c#009"),
    ])
    assert (docs[0]["include"], docs[0]["duplicate_of"]) == (False, "b")
    assert docs[1]["include"] and "duplicate_of" not in docs[1]
    assert [(u["include"], u["duplicate_of"]) for u in units] == [(True, None), (False, "c#009")]


def test_a_decision_naming_a_missing_unit_fails():
    with pytest.raises(SystemExit, match="62149#999"):
        apply_decisions([], [dict(unit_id="62149#001")], [dict(id="62149#999", level="unit", decision="drop", duplicate_of="")])


def test_a_decision_whose_text_changed_fails():
    units = [dict(unit_id="g#002", text="ข้อความใหม่")]
    with pytest.raises(SystemExit, match="changed"):
        apply_decisions([], units, [dict(id="g#002", level="unit", decision="drop", duplicate_of="", text_hash=text_hash("ข้อความเดิม"))])


def test_a_decision_hash_ignores_whitespace():
    units = [dict(unit_id="g#002", text="ข้อ 1\n  เงินได้")]
    apply_decisions([], units, [dict(id="g#002", level="unit", decision="drop", duplicate_of="", text_hash=text_hash("ข้อ 1 เงินได้"))])
    assert units[0]["include"] is False


def test_relations_mark_the_target_and_keep_it():
    docs = [dict(doc_id="new", year="2567", flags=[]), dict(doc_id="old", year="2538", flags=[])]
    rel = dict(doc_id="new", unit_id="new#001", relation="repeals", scope="", target_kind="ประกาศอธิบดี", target_number="58", target_doc_id="old")
    apply_relations(docs, [dict(unit_id="new#001")], [rel, rel | dict(target_number="255", target_doc_id="")])
    assert [a["target"] for a in docs[0]["amends"]] == ["ประกาศอธิบดี 58", "ประกาศอธิบดี 255"]
    assert docs[1]["amended_by"] == [dict(doc_id="new", relation="repeals", year="2567", scope=None)]
    assert docs[1]["flags"] == ["repealed"] and docs[0]["amended_by"] is None


def test_a_relation_naming_a_missing_document_fails():
    rel = dict(doc_id="new", unit_id="new#001", relation="amends", scope="ข้อ 4 ของ", target_kind="x", target_number="1", target_doc_id="gone")
    with pytest.raises(SystemExit, match="gone"):
        apply_relations([dict(doc_id="new", year=None, flags=[])], [dict(unit_id="new#001")], [rel])


def test_built_corpus_applies_every_drop_decision():
    docs_path, units_path = DATA / "clean" / "documents.jsonl", DATA / "clean" / "units.jsonl"
    if not docs_path.exists():
        pytest.skip("data/clean not built")
    recs = {d["doc_id"]: d for d in map(json.loads, docs_path.open(encoding="utf-8"))}
    recs |= {u["unit_id"]: u for u in map(json.loads, units_path.open(encoding="utf-8"))}
    drops = [r for r in csv.DictReader((DATA / "unit_decisions.csv").open(encoding="utf-8")) if r["decision"] == "drop"]
    assert drops
    for r in drops:
        assert recs[r["id"]]["include"] is False and recs[r["id"]]["duplicate_of"] == r["duplicate_of"], r["id"]
