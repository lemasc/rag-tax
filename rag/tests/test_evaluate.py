"""rag.evaluate without network: claim scoring, relevance, rubric validation, aggregation and judge-human agreement."""

import numpy as np
import pytest

from rag import llm
from rag.evaluate import (agree, check_rubric, check_verdicts, conversation, faithfulness, human_gap, make_ask, relevance, rubric,
                          score_record, summarise)


class FakeReply:
    cached = True
    usage = {}


def scripted(*replies):
    """An `ask` that returns each scripted JSON reply in turn through the real `check`."""
    it = iter(replies)

    def ask(messages, check):
        return check(next(it)), [FakeReply()]

    return ask


def test_faithfulness_is_the_share_of_supported_claims():
    ask = scripted({"claims": ["ก", "ข", "ค", "ง"]},
                   {"verdicts": [{"supported": True}, {"supported": True}, {"supported": False}, {"supported": True}]})
    f, _ = faithfulness(ask, "บริบท", "คำตอบ")
    assert f["score"] == 0.75 and f["claims"][2] == dict(claim="ค", supported=False, reason="")


def test_faithfulness_is_none_without_claims():
    f, _ = faithfulness(scripted({"claims": []}), "บริบท", "ขอทราบรายได้ทั้งปีครับ")
    assert f == dict(score=None, claims=[])


def test_verdict_count_must_match_claims():
    with pytest.raises(ValueError):
        check_verdicts(2)({"verdicts": [{"supported": True}]})


def test_relevance_is_mean_cosine_and_zero_when_noncommittal():
    vecs = {"q": [1.0, 0.0], "a": [1.0, 0.0], "b": [0.0, 1.0]}
    emb = lambda texts, query: np.array([vecs[t] for t in texts])  # noqa: E731
    r, _ = relevance(scripted({"questions": ["a", "b"], "noncommittal": False}), emb, "q", "ans")
    assert r["score"] == pytest.approx(0.5)
    r, _ = relevance(scripted({"questions": ["a"], "noncommittal": True}), emb, "q", "ans")
    assert r["score"] == 0.0


GOOD = {"relevance": {"1": 2, "2": 0}, "grounded": 2, "correct": 1, "useful": 2, "behaviour": "na", "tags": ["outdated", "nope"]}


def test_rubric_check_keeps_known_tags_and_requires_every_source():
    out = check_rubric(2)(GOOD)
    assert out["tags"] == ["outdated"] and out["relevance"] == {"1": 2, "2": 0} and out["correct"] == 1
    for bad in (GOOD | {"grounded": 3}, GOOD | {"behaviour": "maybe"}, GOOD | {"relevance": {"1": 2}}, GOOD | {"relevance": {"1": 2, "2": 5}}):
        with pytest.raises(ValueError):
            check_rubric(2)(bad)



def test_rubric_behaviour_is_na_outside_behavioural_questions():
    rec = dict(kind="normal", question="q", answer="a", hits=[{}, {}])
    got, _ = rubric(scripted(GOOD | {"behaviour": "yes"}), rec, "ctx")
    assert got["behaviour"] == "na"
    got, _ = rubric(scripted(GOOD | {"behaviour": "no"}), rec | {"kind": "ask_back"}, "ctx")
    assert got["behaviour"] == "no"

def test_ask_retries_once_without_the_cache(monkeypatch):
    calls = []

    class R:
        cached = False
        usage = {}

    def fake(judge, messages, use_cache=True, **kw):
        calls.append(use_cache)
        return ({"claims": "oops"} if len(calls) == 1 else {"claims": ["x"]}), R()

    monkeypatch.setattr("rag.evaluate.llm.chat_json", fake)
    def check(d):
        if not isinstance(d["claims"], list):
            raise ValueError("claims is not a list")
        return d["claims"]

    checked, _ = make_ask(None)([], check)
    assert checked == ["x"] and calls == [True, False]


def test_ask_does_not_retry_a_reply_cut_off_at_the_cap(monkeypatch):
    calls = []

    def fake(judge, messages, use_cache=True, **kw):
        calls.append(use_cache)
        raise llm.Truncated("cut off at 200 tokens")

    monkeypatch.setattr("rag.evaluate.llm.chat_json", fake)
    with pytest.raises(ValueError, match="cut off"):
        make_ask(None)([], lambda d: d)
    assert calls == [True]


def test_conversation_gives_earlier_turns_of_the_set_only():
    r = lambda i, t: dict(id=i, set="A", turn=t, question=f"q{t}", answer=f"a{t}")  # noqa: E731
    by_id = {x["id"]: x for x in (r("Q1", 1), r("Q2", 2), r("Q3", 3))}
    assert conversation(by_id["Q1"], by_id) == ""
    assert conversation(by_id["Q3"], by_id).count("บทสนทนาก่อนหน้า") == 2
    assert "q3" not in conversation(by_id["Q3"], by_id)
    assert conversation(dict(id="Q9", set=None, turn=None), by_id) == ""


def test_reference_run_gives_the_rubric_its_sources_and_skips_faithfulness():
    seen = []

    def ask(messages, check):
        seen.append(messages[1]["content"])
        if "questions" in messages[0]["content"] and "noncommittal" in messages[0]["content"]:
            return check(dict(questions=["q"], noncommittal=True)), [FakeReply()]
        return check(dict(grounded=1, correct=2, useful=2, behaviour="na", relevance={"1": 2, "2": 0})), [FakeReply()]

    chunks = {c: dict(chunk_id=c, kind="faq", header="", text=f"text {c}") for c in ("c1", "c2")}
    r = dict(id="Q1", category="A", kind="normal", set=None, turn=None, question="q", answer="a", hits=[])
    ref = dict(id="Q1", hits=[dict(chunk_id="c1"), dict(chunk_id="c2")])
    s = score_record(ask, None, r, chunks, {"Q1": r}, ref)
    assert s["faithfulness"]["score"] is None
    assert s["rubric"]["relevance"] == {"1": 2, "2": 0}
    assert len(seen) == 2 and "text c2" in seen[-1]


def rec(kind, category, f, rel, g, behaviour="na", tags=()):
    return dict(id="Q", category=category, kind=kind, faithfulness=dict(score=f), relevance=dict(score=rel),
                rubric=dict(grounded=g, correct=g, useful=g, behaviour=behaviour, tags=list(tags)))


def test_summary_keeps_behavioural_questions_out_of_the_content_table():
    s = summarise([rec("normal", "A", 1.0, 0.8, 2), rec("normal", "A", None, 0.6, 0, tags=["outdated"]),
                   rec("ask_back", "B", 0.0, 0.0, 2, "yes")])
    assert s["content"]["n"] == 2 and s["content"]["faithfulness"] == 1.0 and s["content"]["relevance"] == pytest.approx(0.7)
    assert s["by_category"].keys() == {"A"} and s["behavioural"]["ask_back"]["behaviour"]["yes"] == 1
    assert s["tags"] == {"outdated": 1}


def test_agree_reports_exact_within_one_and_bias():
    a = agree([("2", "2"), ("1", "2"), ("2", "0"), ("2", "")], numeric=True)
    assert a["n"] == 3 and a["exact"] == pytest.approx(1 / 3) and a["within_one"] == pytest.approx(2 / 3)
    assert a["bias"] == pytest.approx((0 - 1 + 2) / 3)
    assert agree([("yes", "yes"), ("no", "yes")], numeric=False) == dict(n=2, exact=0.5)
    assert agree([], numeric=True) == dict(n=0)


def test_human_gap_ignores_incomplete_labels():
    rub = dict(grounded=2, correct=1, useful=2)
    full = lambda g, c, u: dict(grounded=str(g), correct=str(c), useful=str(u), behaviour="na")  # noqa: E731
    assert human_gap(rub, [full(2, 1, 2)]) == 0
    assert human_gap(rub, [full(2, 1, 2), full(0, 1, 2)]) == pytest.approx(2 / 6)
    assert human_gap(rub, [dict(grounded="2", correct="", useful="2", behaviour="na")]) is None
    assert human_gap(rub, []) is None
