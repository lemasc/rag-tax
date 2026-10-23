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
