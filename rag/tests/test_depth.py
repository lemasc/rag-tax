"""rag.depth: the pool, the batches, and the classes."""

import pytest

from rag.depth import batches, best_rank, build_pool, check_grades, classify, panel_grades, recall_at


def test_build_pool_records_each_ranking_and_the_cap():
    pool = build_pool(dense=[0, 1, 2], sparse=[2, 3], fused=[2, 0, 1, 3], doc_ids=["a", "a", "a", "b"], returned={2}, cap=2)
    by = {e["idx"]: e for e in pool}
    assert [e["idx"] for e in pool] == [2, 0, 1, 3] and [e["hybrid_rank"] for e in pool] == [1, 2, 3, 4]
    assert (by[2]["dense_rank"], by[2]["sparse_rank"]) == (3, 1) and by[0]["sparse_rank"] is None
    assert by[1]["capped_rank"] is None and by[3]["capped_rank"] == 3  # the third chunk of document a is dropped by the cap
    assert [e["returned"] for e in pool] == [True, False, False, False]


def test_batches_cover_the_pool_once_in_an_order_that_depends_only_on_the_question():
    ids = [f"c{i}" for i in range(23)]
    b = batches(ids, "Q1", size=10)
    assert [len(x) for x in b] == [10, 10, 3] and sorted(c for x in b for c in x) == sorted(ids)
    assert b == batches(ids, "Q1", size=10) and b != batches(ids, "Q2", size=10)


def test_check_grades_wants_every_number_once_and_only_0_1_2():
    check = check_grades(2)
    assert check({"relevance": {"1": 2, "2": 0}}) == {1: 2, 2: 0}
    for bad in ({"relevance": {"1": 2}}, {"relevance": {"1": 2, "2": 3}}, {"relevance": {"1": 2, "2": 1, "3": 1}}):
        with pytest.raises(ValueError):
            check(bad)


@pytest.mark.parametrize("best, cls", [(None, "D"), (1, "A"), (5, "A"), (6, "B"), (50, "B"), (51, "C"), (97, "C")])
def test_classify(best, cls):
    assert classify(best) == cls


def test_best_rank_and_recall_use_only_chunks_graded_2():
    pool = [dict(chunk_id=c, hybrid_rank=r) for c, r in (("a", 1), ("b", 7), ("c", 30), ("d", 60))]
    g = {"a": 1, "b": 2, "c": 2, "d": 0}
    assert best_rank(pool, g) == 7
    assert [recall_at(pool, g, k) for k in (5, 10, 50)] == [0.0, 0.5, 1.0]
    assert best_rank(pool, {c: 1 for c in "abcd"}) is None and recall_at(pool, {c: 0 for c in "abcd"}, 5) is None


def test_panel_grades_median_against_strict():
    rows = {j: [dict(id="Q", chunk_id="c", grade=g)] for j, g in (("x", 2), ("y", 2), ("z", 1))}
    assert panel_grades(rows, strict=False) == {"Q": {"c": 2}}
    assert panel_grades(rows, strict=True) == {"Q": {"c": 1}}


def test_candidates_are_the_panel_2s_best_rank_first_and_capped():
    from rag.depth import candidates

    pool = [dict(chunk_id=c, hybrid_rank=r) for c, r in (("a", 9), ("b", 2), ("c", 4), ("d", 1), ("e", 30))]
    g = {"a": 2, "b": 2, "c": 2, "d": 1, "e": 2}
    assert [e["chunk_id"] for e in candidates(pool, g, n=3)] == ["b", "c", "a"]


def test_status_walks_the_candidates_until_a_person_says_2():
    from rag.depth import status

    cands = [dict(chunk_id=c, hybrid_rank=r) for c, r in (("a", 3), ("b", 8), ("c", 20))]
    assert status(cands, {}) == ("pending", cands[0])
    assert status(cands, {"a": 1}) == ("pending", cands[1])
    assert status(cands, {"a": 1, "b": 2}) == ("found", cands[1])
    assert status(cands, {"a": 0, "b": 1, "c": 1}) == ("none", None)
    assert status([], {}) == ("none", None)


def test_strip_position_rises_and_keeps_a_zone_for_each_part_of_the_ranking():
    from rag.depth import strip_position

    xs = [strip_position(r) for r in range(1, 101)]
    assert xs == sorted(xs) and 0 < xs[0] and xs[-1] < 100
    assert strip_position(5) < 25 < strip_position(6) and strip_position(50) < 75 < strip_position(51)


def test_depth_labels_round_trip_and_a_second_save_replaces_the_first(tmp_path, monkeypatch):
    from rag import depth, labels

    monkeypatch.setattr(labels, "LABELS", tmp_path)
    depth.save_depth_label("ann", "Q1", "c1", 1, "")
    depth.save_depth_label("ann", "Q1", "c1", 2, " ok ")
    depth.save_depth_label("bob", "Q1", "c1", 0, "")
    depth.save_depth_label("cy", "Q1", "c1", 2, "")
    assert depth.human_grades(["ann"]) == {("Q1", "c1"): 2}
    assert depth.human_grades(["ann", "bob", "cy"]) == {("Q1", "c1"): 2}  # median of 2, 0, 2
    assert depth.human_grades(["ann", "bob"]) == {("Q1", "c1"): 0}  # even: the lower middle


def test_next_pending_goes_to_the_next_unresolved_question_and_wraps():
    from rag.depth import next_pending

    cands = {q: [dict(chunk_id=f"{q}{k}", hybrid_rank=k) for k in (1, 2)] for q in ("Q1", "Q2", "Q3")}
    assert next_pending(cands, {}) == ("Q1", "Q11")
    assert next_pending(cands, {("Q1", "Q11"): 2}) == ("Q2", "Q21")  # Q1 is resolved
    assert next_pending(cands, {("Q1", "Q11"): 1}, after=("Q1", "Q11")) == ("Q1", "Q12")  # the next candidate of the same question
    assert next_pending(cands, {("Q3", "Q31"): 1}, after=("Q3", "Q31")) == ("Q3", "Q32")
    assert next_pending(cands, {("Q3", "Q31"): 1}, after=("Q3", "Q32")) == ("Q1", "Q11")  # wraps round to the first open one
    assert next_pending(cands, {("Q1", "Q11"): 2, ("Q2", "Q21"): 2, ("Q3", "Q31"): 2}) is None
