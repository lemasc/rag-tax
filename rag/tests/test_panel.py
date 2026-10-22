"""rag.panel: the aggregation of several judges' scores, without network or files."""

from rag.panel import aggregate, majority, median


def rec(g, c, u, behaviour="na", tags=(), rel=None, faith=1.0, kind="normal"):
    return dict(id="Q1", category="พื้นฐานภาษี", kind=kind, faithfulness=dict(score=faith), relevance=dict(score=0.5),
                rubric=dict(grounded=g, correct=c, useful=u, behaviour=behaviour, tags=list(tags),
                            relevance=rel or {"1": 2, "2": 0}, note="x"),
                judge_tokens=dict(prompt=10, completion=5))


def test_median_takes_the_lower_middle_of_an_even_panel():
    assert median([2, 0, 1]) == 1
    assert median([0, 2]) == 0


def test_behaviour_tie_goes_to_the_more_severe_value():
    assert majority(["yes", "yes", "no"]) == "yes"
    assert majority(["yes", "no"]) == "no"
    assert majority(["na", "yes"]) == "yes"


def test_aggregate_uses_the_median_and_keeps_each_judges_rubric():
    a = aggregate(dict(a=rec(2, 2, 2), b=rec(1, 0, 2), c=rec(2, 1, 0)))
    assert (a["rubric"]["grounded"], a["rubric"]["correct"], a["rubric"]["useful"]) == (2, 1, 2)
    assert a["spread"] == dict(grounded=1, correct=2, useful=2) and a["contested"]
    assert set(a["judges"]) == {"a", "b", "c"} and a["judge_tokens"] == dict(prompt=30, completion=15)


def test_agreeing_judges_are_not_contested():
    assert not aggregate(dict(a=rec(2, 2, 1), b=rec(2, 1, 1), c=rec(2, 2, 2)))["contested"]


def test_tags_need_a_majority_and_relevance_is_per_source():
    a = aggregate(dict(a=rec(2, 2, 2, tags=["misread", "unsupported"], rel={"1": 2, "2": 1}),
                       b=rec(2, 2, 2, tags=["misread"], rel={"1": 1, "2": 1}),
                       c=rec(2, 2, 2, rel={"1": 2, "2": 0})))
    assert a["rubric"]["tags"] == ["misread"] and a["rubric"]["relevance"] == {"1": 2, "2": 1}


def test_a_judge_without_claims_does_not_pull_faithfulness_down():
    a = aggregate(dict(a=rec(2, 2, 2, faith=0.5), b=rec(2, 2, 2, faith=None), c=rec(2, 2, 2, faith=1.0)))
    assert a["faithfulness"]["score"] == 0.75
