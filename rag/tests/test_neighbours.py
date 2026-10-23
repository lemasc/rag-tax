"""rag.neighbours: which text goes with a chunk, how the sample is cut, and the effect over the noise floor."""

import pytest

from rag.neighbours import batches_of, effect, expanded_text, neighbours, stratum, units_by_doc


def chunk(i, unit, part=1, n_parts=1, tokens=100, header="D | ข้อ", origin="clause"):
    return dict(chunk_id=f"d#{unit:03d}" + (f"~{part:03d}" if n_parts > 1 else ""), doc_id="d", unit_id=f"d#{unit:03d}", origin=origin,
                part=part, n_parts=n_parts, n_tokens=tokens, header=header, text=f"t{unit}.{part}")


def test_the_other_parts_of_the_unit_come_first_then_siblings_nearest_first():
    cs = [chunk(1, 1), chunk(2, 2, 1, 2), chunk(2, 2, 2, 2), chunk(3, 3), chunk(4, 4)]
    units = units_by_doc(cs)["d"]
    before, after = neighbours(cs[2], units, cap=200)  # the later part of unit 2
    assert [p["text"] for p in before] == ["t2.1"] and [p["text"] for p in after] == ["t3.1"]  # its part 1, then the next unit before the previous one


def test_a_neighbour_that_does_not_fit_is_skipped_and_a_smaller_one_further_away_is_taken():
    cs = [chunk(1, 1, tokens=50), chunk(2, 2), chunk(3, 3, tokens=450)]
    before, after = neighbours(cs[1], units_by_doc(cs)["d"], cap=100)
    assert [p["text"] for p in before] == ["t1.1"] and after == []


def test_sub_items_are_siblings_only_under_the_same_parent():
    cs = [chunk(1, 1, header="D | ข้อ 1 | (1)"), chunk(2, 2, header="D | ข้อ 1 | (2)"), chunk(3, 3, header="D | ข้อ 2 | (1)")]
    before, after = neighbours(cs[0], units_by_doc(cs)["d"])
    assert before == [] and [p["text"] for p in after] == ["t2.1"]


def test_expanded_text_marks_the_neighbours_and_keeps_reading_order():
    a, b, c = (chunk(i, i) for i in (1, 2, 3))
    text = expanded_text(b, [a], [c])
    assert text.index("t1.1") < text.index("t2.1") < text.index("t3.1") and text.count("[ข้อความข้างเคียง") == 2


def test_strata():
    assert stratum(chunk(1, 1)) == "clause"
    assert stratum(chunk(1, 1, 2, 3, origin="statute")) == "later-part"
    assert stratum(chunk(1, 1, 1, 3, origin="statute")) is None  # the first part is not a later part
    assert stratum(chunk(1, 1, origin="faq")) is None


def test_a_batch_equal_to_an_e1_batch_is_reversed_in_both_conditions():
    ids = ["a", "b", "c"]
    plain = batches_of("Q1", ids, {})
    clash = batches_of("Q1", ids, {"Q1": {frozenset(plain[0])}})
    assert clash == [plain[0][::-1]]


def test_effect_is_the_gain_over_asking_again_and_counts_each_chunk_once():
    rows = [dict(id=f"Q{i}", chunk_id="c" if i < 3 else f"c{i}", e1=1) for i in range(4)]
    g = {(r["id"], r["chunk_id"], "alone"): 2 if r["id"] == "Q3" else 1 for r in rows}
    g |= {(r["id"], r["chunk_id"], "expanded"): 2 for r in rows}
    e = effect(rows, lambda r, c: g[r["id"], r["chunk_id"], c], 1)
    assert (e["n"], e["chunks"]) == (4, 2) and e["expanded_is_2"] == 1.0 and e["alone_is_2"] == 0.25
    assert e["difference"] == pytest.approx(0.75)
    assert e["per_chunk_difference"] == pytest.approx((1 + 0) / 2)  # chunk c gains in all 3 questions, chunk c3 not at all
