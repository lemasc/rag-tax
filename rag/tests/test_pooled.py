"""rag.pooled: the grades kept per chunk text, the metrics of one mode, and the paired difference."""

import math

import pytest

from rag.pooled import missing, panel_grades, paired_difference, question_metrics

ITEM = dict(id="Q1", pool=[dict(chunk_id="a", text_sha1="1"), dict(chunk_id="b", text_sha1="2")])


def test_missing_asks_again_only_for_pairs_new_or_with_changed_text():
    done = [dict(id="Q1", chunk_id="a", text_sha1="1", grade=2), dict(id="Q1", chunk_id="b", text_sha1="old", grade=1)]
    assert missing([ITEM], done) == {"Q1": ["b"]}
    assert missing([ITEM], done + [dict(id="Q1", chunk_id="b", text_sha1="2", grade=0)]) == {}


def test_panel_grades_ignore_grades_of_chunks_no_longer_in_the_pool():
    rows = {j: [dict(id="Q1", chunk_id="a", text_sha1="1", grade=g), dict(id="Q1", chunk_id="b", text_sha1="gone", grade=2)]
            for j, g in (("x", 2), ("y", 2), ("z", 1))}
    assert panel_grades(rows, [ITEM], strict=False) == {"Q1": {"a": 2}}
    assert panel_grades(rows, [ITEM], strict=True) == {"Q1": {"a": 1}}


def test_question_metrics_by_hand():
    grades = {c: g for c, g in zip("abcdefg", (0, 1, 2, 0, 0, 2, 1))}
    m = question_metrics(list("abcdef"), grades)
    assert m["hit5"] == 1.0 and m["precision5"] == 0.2 and m["mrr10"] == pytest.approx(1 / 3)
    assert m["recall10"] == 1.0  # both 2s (c, f) are in the top 10
    dcg = 1 / math.log2(3) + 2 / math.log2(4) + 2 / math.log2(7)
    ideal = 2 + 2 / math.log2(3) + 1 / math.log2(4) + 1 / math.log2(5)
    assert m["ndcg10"] == pytest.approx(dcg / ideal)
    late = question_metrics(list("abdegf"), grades)  # the first 2 comes at rank 6: outside the top 5
    assert late["hit5"] == 0.0 and late["precision5"] == 0.0 and late["mrr10"] == pytest.approx(1 / 6)


def test_a_question_without_a_2_scores_zero_where_it_can_and_none_where_it_cannot():
    m = question_metrics(["a", "b"], {"a": 1, "b": 0})
    assert (m["hit5"], m["mrr10"], m["precision5"]) == (0.0, 0.0, 0.0)
    assert m["recall10"] is None
    assert question_metrics(["a"], {"a": 0})["ndcg10"] is None


def test_paired_difference_skips_questions_either_mode_has_no_value_for():
    a, b = {"q1": 1.0, "q2": 0.5, "q3": None}, {"q1": 0.0, "q2": 0.5, "q3": 0.3}
    d = paired_difference(a, b)
    assert d["n"] == 2 and d["mean"] == pytest.approx(0.5) and d["lo"] <= d["mean"] <= d["hi"]
    assert paired_difference({"q": None}, {"q": 1.0}) == dict(mean=None, lo=None, hi=None, n=0)


def test_compare_modes_and_contested_and_sources():
    from rag.pooled import compare_modes, contested, hybrid_top5_sources, judge_grades

    item = dict(id="Q1", pool=[dict(chunk_id=c, text_sha1="1") for c in "abc"],
                rankings=dict(dense=["a", "b"], sparse=["c", "b"], hybrid=["b", "c"]))
    g = {"Q1": {"a": 2, "b": 1, "c": 0}}
    assert compare_modes(item, g) == "dense only"  # the 2 is in dense's top 5; hybrid does not have it
    g2 = {"Q1": {"a": 1, "b": 1, "c": 2}}
    assert compare_modes(item, g2, "dense", "sparse") == "sparse only"
    assert compare_modes(item, {"Q1": {"a": 0, "b": 1, "c": 1}}) == "no 2 in pool"
    assert hybrid_top5_sources([item], g) == {"both": [1], "dense only": [], "sparse only": [0], "neither": []}
    rows = {j: [dict(id="Q1", chunk_id="a", text_sha1="1", grade=x), dict(id="Q1", chunk_id="b", text_sha1="1", grade=1),
                dict(id="Q1", chunk_id="c", text_sha1="1", grade=1), dict(id="Q1", chunk_id="a", text_sha1="old", grade=0)]
            for j, x in (("x", 2), ("y", 0))}
    assert contested(item, judge_grades(rows, [item])) == ["a"]


def test_add_variant_puts_only_new_chunks_into_the_pool_and_modes_of_lists_it():
    from rag.pooled import add_variant, modes_of, ranking

    item = dict(id="Q1", pool=[dict(chunk_id="a", text_sha1="1")], rankings=dict(dense=["a"], sparse=["a"], hybrid=["a"]))
    assert modes_of([item]) == ["dense", "sparse", "hybrid"]
    assert add_variant(item, "hybrid-k10", ["a", "b", "b"], {"a": "1", "b": "2"}) == 1
    assert [e["chunk_id"] for e in item["pool"]] == ["a", "b"] and ranking(item, "hybrid-k10") == ["a", "b", "b"]
    assert modes_of([item]) == ["dense", "sparse", "hybrid", "hybrid-k10"] and ranking(item, "dense") == ["a"]
    assert modes_of([item, dict(item, variants={})]) == ["dense", "sparse", "hybrid"]  # only variants every question has


def test_modes_of_orders_rrf_variants_by_k_then_the_others():
    from rag.pooled import modes_of
    items = [dict(variants={"hybrid-k20": [], "dense-rerank": [], "hybrid-k5": []})]
    assert modes_of(items) == ["dense", "sparse", "hybrid", "hybrid-k5", "hybrid-k20", "dense-rerank"]


def test_rerank_orders_dense_candidates_by_the_cross_encoder(monkeypatch):
    import sys
    import types
    from rag import pooled

    class Fake:
        def __init__(self, *a, **kw):
            pass

        def predict(self, pairs, batch_size):
            return [float(p[1].endswith("c")) for p in pairs]  # only chunk c "answers"

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=Fake))
    monkeypatch.setattr(pooled, "passage", lambda c: c["text"])
    chunks = [dict(chunk_id=x, text=f"text {x}") for x in "abc"]
    retriever = types.SimpleNamespace(chunks=chunks, rankings=lambda q: ([0, 1, 2], [], []))
    item = dict(query="q", pool=[dict(chunk_id="a", text_sha1="x")])
    assert pooled.build_rerank(retriever, [item]) == 2  # b and c are new to the pool
    assert item["variants"]["dense-rerank"][0] == "c"
