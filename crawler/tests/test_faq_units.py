"""split_faq(): one unit per question, across the three source layouts. Each case names the page it comes from."""

import re

import pytest

from crawler.clean.units import split_faq

FAQ_PAGES = ["60062", "66379", "60056", "61081", "63908", "60116", "60054", "60055", "60057", "60058", "60059",
             "60060", "60061", "60063", "61549", "61065", "62149", "62777"]


def split(page_text, pid):
    return split_faq(pid, page_text(pid))


def test_clearcut_plain_pairs(page_text):
    # 66379 (Gift Tax): Q1..Q10, A1..A10, nothing else on the page
    pre, units = split(page_text, "66379")
    assert pre == ""
    assert [u.label for u in units] == [f"Q{i}" for i in range(1, 11)]
    assert all(u.text.startswith(f"Q{i} :") and f"\nA{i} :" in u.text for i, u in enumerate(units, 1))


def test_numbered_sections_restart_q_numbering(page_text):
    # 61081: seven numbered sections, Q numbers restart at 1 in each; headings sit between the last A and the next Q1
    pre, units = split(page_text, "61081")
    assert len(units) == 74
    assert pre.startswith("Clear Cut")
    sections = list(dict.fromkeys(u.section for u in units))
    assert [s.split(".")[0] for s in sections] == ["1", "2", "3", "4", "5", "6", "7"]
    assert sections[1] == "2. การยื่นแบบฯ ภ.ง.ด.90/91"
    first_of_section_2 = next(u for u in units if u.section == sections[1])
    assert first_of_section_2.label == "Q1"
    prev = units[units.index(first_of_section_2) - 1]
    assert "2. การยื่นแบบฯ" not in prev.text  # the heading was cut off the previous answer


def test_marker_split_over_two_lines_and_lost_q(page_text):
    # 61549: "Q8" / ":มีเงินได้..." is one marker over two lines; "2 : ..." lost its Q in extraction
    pre, units = split(page_text, "61549")
    assert len(units) == 121
    q2 = next(u for u in units if u.label == "Q2")
    assert "marker_q_lost" in q2.flags and "วิสาหกิจชุมชนต้องยื่นแบบ" in q2.text
    q8 = next(u for u in units if u.label == "Q8" and "มีเงินได้จากเงินเดือนอย่างเดียว" in u.text)
    assert "A8" in q8.text


def test_unnumbered_headings_are_guessed_and_flagged(page_text):
    # 62777: headings are bare short lines ("คู่สมรส", "บุตร") glued to the end of the previous answer
    pre, units = split(page_text, "62777")
    guessed = [u for u in units if "section_guessed" in u.flags]
    assert len(guessed) == 23
    assert guessed[0].section == "คู่สมรส" and guessed[1].section == "บุตร"
    assert "คู่สมรส" not in units[units.index(guessed[0]) - 1].text.split("\n")[-1]


def test_roi_rueang_titles_and_inherited_titles(page_text):
    # 60057: item 5 holds two questions (one title); the title is inherited and the second one labelled (2)
    pre, units = split(page_text, "60057")
    assert pre.startswith("“ร้อยเรื่องลดหย่อน ปีภาษี 2560”") and "หมวดค่าลดหย่อนอุปการะเลี้ยงดูคนพิการ" in pre
    assert len(units) == 8
    inh = [u for u in units if "title_inherited" in u.flags]
    assert [u.label for u in inh] == ["ชื่อเรื่อง 5 (2)"]
    assert inh[0].title == units[units.index(inh[0]) - 1].title


def test_roi_rueang_answers_without_colon_or_glued_to_question(page_text):
    # 60060: some answers read "คำตอบ การกู้..." (no colon); 60061: answer glued to the question text
    for pid, n in (("60060", 16), ("60061", 4), ("60055", 11)):
        _, units = split(page_text, pid)
        assert len(units) == n
        assert not [u.label for u in units if "no_answer" in u.flags or "multiple_answers" in u.flags], pid


def test_roi_rueang_irregular_marker_spacing(page_text):
    # 60062 writes its markers as "1 .ชื่อเรื่อง", "3..ชื่อเรื่อง", "9. ชื่อเรื่อง", "11 .ชื่อเรื่อง": all eleven are found
    _, units = split(page_text, "60062")
    assert [u.label for u in units] == [f"ชื่อเรื่อง {i}" for i in range(1, 12)]
    assert units[2].title.startswith("เอกสารหลักฐานในการบริจาค")


def test_roi_rueang_doubled_dot_marker(page_text):
    # 60061 writes "1. .ชื่อเรื่อง" and "2. .ชื่อเรื่อง": four titles, none inherited
    _, units = split(page_text, "60061")
    assert [u.label for u in units] == [f"ชื่อเรื่อง {i}" for i in range(1, 5)]
    assert not any("title_inherited" in u.flags for u in units)


def test_non_faq_text_gives_no_units():
    assert split_faq("x", "เนื้อหาทั่วไป\nไม่มีคำถาม") == ("เนื้อหาทั่วไป\nไม่มีคำถาม", [])


@pytest.mark.parametrize("pid", FAQ_PAGES)
def test_no_text_is_lost_or_invented(page_text, pid):
    # Units + preamble + the section headings cut out of answers must reproduce the page exactly (ignoring whitespace).
    text = page_text(pid)
    pre, units = split_faq(pid, text)
    assert units, pid
    parts = [pre] + [u.text for u in units] + list(dict.fromkeys(u.section for u in units if u.section))
    squash = lambda s: sorted(re.sub(r"\s+", "", s))
    assert squash("".join(parts)) == squash(text)


@pytest.mark.parametrize("pid", FAQ_PAGES)
def test_every_unit_has_one_answer_and_unique_id(page_text, pid):
    _, units = split(page_text, pid)
    assert len({u.unit_id for u in units}) == len(units)
    assert not [u.label for u in units if {"no_answer", "multiple_answers"} & set(u.flags)]
