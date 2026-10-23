"""rag.judge_swap: the pass rules for putting luna in sol's seat."""

from rag.judge_swap import fully_graded, pair_check, verdict


def test_pairs_pass_only_when_luna_agrees_and_is_not_more_lenient():
    keys = [("Q1", f"c{i}") for i in range(10)]
    sol = {k: 2 if k == keys[1] else 1 for k in keys}
    other = {k: 1 for k in keys}
    close = {k: 2 if k == keys[0] else 1 for k in keys}  # 80-90% agreement, as many 2s as sol
    assert pair_check({"judge-sol-or": sol, "judge-haiku": other, "judge-deepseek": other, "judge-luna-or": close}, keys)["passes"]
    lenient = {k: 2 for k in keys}
    assert not pair_check({"judge-sol-or": sol, "judge-haiku": other, "judge-deepseek": other, "judge-luna-or": lenient}, keys)["passes"]


def test_only_questions_graded_in_full_are_compared():
    items = [dict(id="Q1", pool=[dict(chunk_id="a"), dict(chunk_id="b")]), dict(id="Q2", pool=[dict(chunk_id="a")])]
    assert [it["id"] for it in fully_graded(items, {("Q1", "a"): 1, ("Q2", "a"): 2})] == ["Q2"]


def test_verdict_follows_the_outcome_table():
    assert verdict(True, True).startswith("swap:")
    assert "both panels" in verdict(True, False)
    assert verdict(False, True).startswith("no swap")
