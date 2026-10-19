"""crawler.clean.build: hand-recorded decisions applied to the built corpus."""

import csv
import json

import pytest

from conftest import DATA
from crawler.clean.build import apply_decisions


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
