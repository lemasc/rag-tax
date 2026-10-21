"""rag.labels: per-reviewer files, upserts, queue rules, agreement. Uses a temporary labels directory."""

import pytest

from rag import labels
from rag.questions import load

FULL = dict(grounded="2", correct="1", useful="2", behaviour="na", tags="outdated", note="")


@pytest.fixture(autouse=True)
def _tmp_labels(monkeypatch, tmp_path):
    monkeypatch.setattr(labels, "LABELS", tmp_path / "labels")


def test_names_are_checked():
    assert labels.check_name("  Lemasc ") == "lemasc"
    for bad in ("", "a b", "../x", "-x", "x" * 40):
        with pytest.raises(ValueError):
            labels.check_name(bad)


def test_save_upserts_and_keeps_other_rows():
    labels.save("ann", "run1", "Q1", FULL, {"c1": {"relevance": "2"}, "c2": {"relevance": "0"}})
    labels.save("ann", "run1", "Q2", FULL, {"c1": {"relevance": "1"}})
    labels.save("ann", "run1", "Q1", FULL | {"correct": "2"}, {"c1": {"relevance": "1"}})
    a, c = labels.answer_labels("ann"), labels.chunk_labels("ann")
    assert len(a) == 2 and a[("run1", "Q1")]["correct"] == "2"
    assert c[("Q1", "c1")]["relevance"] == "1" and c[("Q1", "c2")]["relevance"] == "0" and c[("Q2", "c1")]["relevance"] == "1"
    assert labels.reviewers() == ["ann"]


def test_incomplete_labels_do_not_count_as_done():
    assert labels.is_complete(FULL) and not labels.is_complete(FULL | {"behaviour": ""}) and not labels.is_complete(None)


def test_queue_shared_first_then_unclaimed_and_sets_stay_with_their_reviewer():
    qs = load()
    a_set = [q.id for q in qs if q.set == "A"]
    ids = ["Q0001", "Q0002", "Q0003"] + a_set
    shared = ["Q0003"]
    todo, _ = labels.queue("ann", "r", ids, shared)
    assert todo[0].question_id == "Q0003" and {i.question_id for i in todo} == set(ids)
    labels.save("bob", "r", "Q0001", FULL, {})
    labels.save("bob", "r", "Q0003", FULL, {})
    labels.save("bob", "r", a_set[0], FULL, {})
    todo, items = labels.queue("ann", "r", ids, shared)
    assert [i.question_id for i in todo] == ["Q0003", "Q0002"]  # shared stays; Q0001 and bob's set are taken
    assert next(i for i in items if i.question_id == "Q0001").done_by == ["bob"]
    todo, _ = labels.queue("bob", "r", ids, shared)
    assert {i.question_id for i in todo} == {"Q0002", *a_set[1:]}


def test_each_reviewer_gets_their_own_order_with_sets_kept_together():
    qs = load()
    sets = {s: [q.id for q in qs if q.set == s] for s in "ABCD"}
    ids = [f"Q{n:04d}" for n in range(1, 31)] + [q for s in "ABCD" for q in sets[s]]
    shared = ["Q0005", "Q0001"]
    orders = {}
    for name in ("ann", "bob", "cat"):
        todo, _ = labels.queue(name, "r", ids, shared)
        got = [i.question_id for i in todo]
        assert got[:2] == ["Q0001", "Q0005"]  # shared first, in file order
        for s in "ABCD":  # each set contiguous, turns in order
            pos = [got.index(q) for q in sets[s]]
            assert pos == list(range(pos[0], pos[0] + 3))
        assert got == [i.question_id for i in labels.queue(name, "r", ids, shared)[0]]  # stable for the same reviewer
        orders[name] = got[2:]
    assert len({tuple(o) for o in orders.values()}) == 3
    assert len({o[0] for o in orders.values()}) > 1  # different people start in different places


def test_agreement_counts_pairs_on_the_given_questions():
    labels.save("ann", "r", "Q1", FULL, {"c1": {"relevance": "2"}})
    labels.save("bob", "r", "Q1", FULL | {"correct": "2"}, {"c1": {"relevance": "2"}})
    labels.save("bob", "r", "Q9", FULL, {})
    agr = labels.agreement("r", ["Q1"])
    assert agr["grounded"] == (1, 1.0) and agr["correct"] == (1, 0.0) and agr["relevance"] == (1, 1.0)


def test_agreement_compares_behaviour_on_behavioural_questions_only():
    kinds = {q.kind: q.id for q in load()}
    normal, ask_back = kinds["normal"], kinds["ask_back"]
    labels.save("ann", "r", normal, FULL | {"behaviour": "yes"}, {})
    labels.save("bob", "r", normal, FULL | {"behaviour": "no"}, {})
    assert labels.agreement("r", [normal])["behaviour"][0] == 0
    labels.save("ann", "r", ask_back, FULL | {"behaviour": "yes"}, {})
    labels.save("bob", "r", ask_back, FULL | {"behaviour": "yes"}, {})
    assert labels.agreement("r", [normal, ask_back])["behaviour"] == (1, 1.0)
