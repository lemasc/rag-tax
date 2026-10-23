"""rag.answer without network: prompt assembly, citations, multi-turn query, reasoning cut from replies."""

import pytest

from rag import answer as A, llm
from rag.answer import SYSTEM, SYSTEM_NO_SOURCES, citations, messages_for, retrieval_query, source_block, strip_thinking, year_label
from rag.questions import Question

HITS = [
    dict(chunk_id="a#001", header="T | Q1", kind="faq", tax_year=2563, year=None, flags=[], text="ลดหย่อน 30,000 บาท"),
    dict(chunk_id="b~001", header="กฎกระทรวง", kind="กฎกระทรวง", tax_year=None, year="2545", flags=[], text="ข้อ 1"),
    dict(chunk_id="c~001", header="โปสเตอร์", kind="image", tax_year=None, year=None, flags=["unverified"], text="60,000"),
]


def test_year_label_prefers_tax_year_then_document_year():
    assert [year_label(h) for h in HITS] == ["ปีภาษี 2563", "พ.ศ. 2545", "ไม่ระบุปี"]


def test_source_block_numbers_and_flags_unverified_text():
    assert source_block(1, HITS[0]).startswith("[1] T | Q1\nประเภท: คำถาม-คำตอบ กรมสรรพากร | ปีภาษี 2563\n")
    assert "ยังไม่ได้ตรวจทาน" in source_block(3, HITS[2]) and "ยังไม่ได้ตรวจทาน" not in source_block(2, HITS[1])


def test_citations_map_numbers_to_chunks_and_report_strays():
    cited, bad = citations("ได้ 30,000 บาท [1] ตามกฎกระทรวง [2][1] และ [7]", HITS)
    assert cited == ["a#001", "b~001"] and bad == [7]


def test_messages_put_sources_only_on_the_current_turn():
    msgs = messages_for("แล้วถ้ามีโบนัสล่ะ?", HITS, [("เงินเดือน 25,000 ต้องเสียภาษีไหม?", "ไม่ต้อง [1]")])
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[0]["content"] == SYSTEM and msgs[1]["content"] == "เงินเดือน 25,000 ต้องเสียภาษีไหม?"
    assert msgs[3]["content"].startswith("เอกสารอ้างอิง\n\n[1]") and msgs[3]["content"].endswith("คำถาม: แล้วถ้ามีโบนัสล่ะ?")


def test_retrieval_query_joins_earlier_turns():
    q = lambda t, n: Question(id=f"Q{n}", category="c", difficulty=None, text=t, kind="multi_turn", set="A", turn=n)  # noqa: E731
    assert retrieval_query(q("ล่ะ?", 2), [q("เงินเดือน", 1)]) == "เงินเดือน\nล่ะ?"


@pytest.mark.parametrize("reply", [
    "<think>ดู [2] ก่อน</think>\n\nหักได้ 60,000 บาท [1]",
    "ดู [2] ก่อน</think>\n\nหักได้ 60,000 บาท [1]",  # the template opened the block in the prompt
])
def test_reasoning_is_cut_and_its_citations_do_not_count(reply):
    text, cut = strip_thinking(reply)
    assert text.strip() == "หักได้ 60,000 บาท [1]" and cut > 0
    assert citations(text, HITS) == (["a#001"], [])


def test_reply_without_reasoning_is_unchanged():
    assert strip_thinking("หักได้ [1][2]") == ("หักได้ [1][2]", 0)


def test_no_retrieval_sends_the_bare_question_under_the_no_sources_prompt():
    msgs = messages_for("ต้องยื่นไหม", None, [("ถามก่อน", "ตอบก่อน")])
    assert msgs[0] == {"role": "system", "content": SYSTEM_NO_SOURCES}
    assert msgs[1:] == [{"role": "user", "content": "ถามก่อน"}, {"role": "assistant", "content": "ตอบก่อน"},
                        {"role": "user", "content": "ต้องยื่นไหม"}]
    assert "[n]" not in SYSTEM_NO_SOURCES and "เอกสารอ้างอิงที่ให้มา" not in SYSTEM_NO_SOURCES
    assert citations("ตอบ [1]", []) == ([], [1])  # any [n] without sources is a bad citation


def _replies(monkeypatch, texts):
    calls = []

    def fake(p, messages, attempt=0):
        calls.append(attempt)
        return llm.Reply(texts[attempt], "m", {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, cached=False, seconds=1.0)

    monkeypatch.setattr(llm, "chat", fake)
    return calls


def test_an_answer_in_chinese_script_is_asked_again_until_clean(monkeypatch):
    calls = _replies(monkeypatch, ["ต้อง申报ภาษี [1]", "ต้องยื่นแบบ [1]", "ไม่ถูกถาม"])
    text, _, r, replies = A.answer(None, "ถาม", HITS, script_retries=3)
    assert (text, calls, len(replies)) == ("ต้องยื่นแบบ [1]", [0, 1], 2) and r is replies[-1]


def test_retries_stop_at_the_limit_and_keep_the_last_answer(monkeypatch):
    calls = _replies(monkeypatch, ["申报 1", "申报 2", "申报 3"])
    text, _, _, replies = A.answer(None, "ถาม", HITS, script_retries=2)
    assert (text, calls) == ("申报 3", [0, 1, 2]) and A.FOREIGN.findall(text) == ["申报"]


def test_without_retries_a_foreign_answer_is_kept(monkeypatch):
    calls = _replies(monkeypatch, ["申报"])
    assert A.answer(None, "ถาม", HITS)[0] == "申报" and calls == [0]
