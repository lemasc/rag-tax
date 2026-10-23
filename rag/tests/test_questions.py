"""rag.questions: parsing, turn tags, history, dev subset."""

import pytest

from rag import questions as Q


def row(id_, cat, text, diff="ง่าย"):
    return {"ID": id_, "หมวด": cat, "คำถาม": text, "ระดับความยาก": diff}


def test_turn_tag_is_stripped_into_set_and_turn():
    q = Q.parse(row("Q1", "คำถามหลายรอบ", "ถ้ามีโบนัสอีก 30,000 บาทล่ะ? [รอบ 2: ชุด A]"))
    assert (q.text, q.set, q.turn, q.kind) == ("ถ้ามีโบนัสอีก 30,000 บาทล่ะ?", "A", 2, "multi_turn")


def test_kinds_and_missing_difficulty():
    assert Q.parse(row("Q1", "โจทย์ข้อมูลไม่ครบ", "x")).kind == "ask_back"
    assert Q.parse(row("Q2", "พื้นฐานภาษี", "x")).kind == "normal"
    assert Q.parse(row("Q3", "นอกขอบเขต", "x", diff="")).difficulty is None


def test_a_tag_outside_the_multi_turn_category_is_an_error():
    with pytest.raises(ValueError, match="disagree"):
        Q.parse(row("Q1", "พื้นฐานภาษี", "x [รอบ 1: ชุด A]"))


@pytest.fixture(scope="module")
def qs():
    if not Q.QUESTIONS.exists():
        pytest.skip("question CSV not available")
    return Q.load()


def test_real_set_loads_with_expected_shape(qs):
    assert len(qs) == 369
    assert sum(q.kind == "multi_turn" for q in qs) == 12 and not any("[รอบ" in q.text for q in qs)


def test_history_is_the_earlier_turns_of_the_same_set(qs):
    third = next(q for q in qs if q.set == "B" and q.turn == 3)
    assert [(p.set, p.turn) for p in Q.history(third, qs)] == [("B", 1), ("B", 2)]
    assert Q.history(next(q for q in qs if q.set is None), qs) == []


def test_dev_draw_is_deterministic_and_matches_the_saved_subset(qs):
    ids = Q.draw_dev(qs)
    assert ids == Q.draw_dev(qs) and len(ids) == len(set(ids)) == 40
    if Q.DEV.exists():
        assert [q.id for q in Q.dev(qs)] == ids
    sets = {q.set for q in qs if q.id in ids and q.set}
    assert len(sets) == 1 and sum(q.set in sets for q in qs if q.id in ids) == 3  # one whole set


def test_ablation_draw_is_deterministic_leaves_out_dev_and_matches_the_saved_subset(qs):
    dev_ids = set(Q.draw_dev(qs))
    ids = Q.draw_ablation(qs, dev_ids)
    assert ids == Q.draw_ablation(qs, dev_ids) and len(ids) == len(set(ids)) == 131 and not dev_ids & set(ids)
    if Q.ABLATION.exists():
        assert [q.id for q in Q.ablation(qs)] == ids
    kinds = {}
    for q in qs:
        if q.id in ids:
            kinds[q.kind] = kinds.get(q.kind, 0) + 1
    assert kinds == {"normal": 96, "multi_turn": 9, "ask_back": 13, "misconception": 13}
    for s in {q.set for q in qs if q.id in ids and q.set}:  # whole sets, so every turn has its earlier turns
        assert all(q.id in ids for q in qs if q.set == s)
