import re

from crawler.clean.units import INSTRUMENT_SPLIT_CHARS, split_instrument

PAD = " เงินได้ที่ได้รับตามกฎหมายนี้" * 16  # long enough that an item is not merged with its neighbour


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def test_one_unit_per_heading_and_preamble_kept():
    text = "กฎกระทรวง ฉบับที่ 1 ข้อ 1 ให้ใช้บังคับ ข้อ 2 ให้ยกเว้นภาษี ข้อ 3 ผู้รักษาการ"
    pre, us = split_instrument("d", text)
    assert pre == "กฎกระทรวง ฉบับที่ 1"
    assert [u.label for u in us] == ["ข้อ 1", "ข้อ 2", "ข้อ 3"] and [u.unit_id for u in us] == ["d#001", "d#002", "d#003"]
    assert squash(pre + "".join(u.text for u in us)) == squash(text)


def test_a_reference_is_not_a_heading():
    text = "ข้อ 1 ให้ใช้ตาม ข้อ 2 และ ข้อ 3 ในกรณีนี้ ข้อ 2 ให้ยกเว้น ข้อ 3 ให้ใช้บังคับ"
    _, us = split_instrument("d", text)
    assert [u.label for u in us] == ["ข้อ 1", "ข้อ 2", "ข้อ 3"] and "ตาม ข้อ 2 และ ข้อ 3" in us[0].text


def test_heading_after_a_year_and_after_an_opening_quote():
    _, us = split_instrument("d", "ข้อ 1 ใช้บังคับตั้งแต่ พ.ศ. 2560 ข้อ 2 ให้ยกเว้น “ข้อ 3 ให้เพิ่ม")
    assert [u.label for u in us] == ["ข้อ 1", "ข้อ 2", "ข้อ 3"]


def test_prose_has_no_units():
    text = "คำวินิจฉัย เงินได้ตามมาตรา 40 (1) และข้อ 2 ของคำสั่ง"
    assert split_instrument("d", text) == (text, [])


def test_a_long_heading_is_cut_at_its_items_with_the_lead_in_as_section():
    items = " ".join(f"({n}) รายการที่ {n}{PAD}" for n in range(1, 5))
    assert len(items) > INSTRUMENT_SPLIT_CHARS
    _, us = split_instrument("d", f"ข้อ 1 ให้ใช้ ข้อ 2 ให้ยกเว้นเงินได้ดังต่อไปนี้ {items}")
    assert [u.label for u in us] == ["ข้อ 1", "(1)", "(2)", "(3)", "(4)"]
    assert us[1].section.startswith("ข้อ 2 ให้ยกเว้นเงินได้ดังต่อไปนี้") and us[3].section == us[1].section
    assert us[1].text.startswith("ข้อ 2 ให้ยกเว้น") and us[2].text.startswith("(2) รายการที่ 2")  # a short lead-in joins item 1


def test_items_after_a_quote_a_repealed_gap_and_a_reference_to_an_item():
    items = " ".join(
        [f'"(1) รายการ 1{PAD}" (แก้ไขเพิ่มเติมโดยกฎกระทรวง ฉบับที่ 3)', f"(2) รายการ 2 ตามมาตรา 40 (3) หรือ (4){PAD}",
         f"(3) รายการ 3{PAD} (ยกเลิก) (5) รายการ 5{PAD}"])
    _, us = split_instrument("d", f"ข้อ 1 ให้ใช้บังคับ ข้อ 2 ให้ยกเว้น {items}")
    assert [u.label for u in us] == ["ข้อ 1", "(1)", "(2)", "(3)", "(5)"] and "(3) หรือ (4)" in us[2].text
    assert us[2].text.startswith("(2)") and us[3].text.endswith("(ยกเลิก)")


def test_sections_of_a_royal_decree_when_there_is_no_khor():
    _, us = split_instrument("d", "มาตรา 1 พระราชกฤษฎีกานี้ มาตรา 2 ให้ยกเว้นตามมาตรา 3 แห่งประมวลรัษฎากร มาตรา 3 ผู้รักษาการ")
    assert [u.label for u in us] == ["มาตรา 1", "มาตรา 2", "มาตรา 3"]


BODY = "ให้ยกเว้นเงินได้ที่ได้รับตามกฎหมายนี้ " * 4


def test_headings_and_items_are_taken_at_line_starts():
    items = "\n".join(f"({n}) รายการที่ {n} {PAD}" for n in range(1, 5))
    text = f"กฎกระทรวง\nข้อ 1 ให้ใช้ตามข้อ 2\nข้อ 2 ให้ยกเว้นดังต่อไปนี้\n{items}\n“ข้อ 3 ให้เพิ่ม\nข้อ 4 ผู้รักษาการ\nข้อ 5 ใช้บังคับ"
    _, us = split_instrument("d", text)
    assert [u.label for u in us] == ["ข้อ 1", "(1)", "(2)", "(3)", "(4)", "ข้อ 3", "ข้อ 4", "ข้อ 5"]
    assert us[0].text == "ข้อ 1 ให้ใช้ตามข้อ 2" and us[5].text.startswith("“ข้อ 3")


def test_a_reference_at_a_line_start_is_not_a_heading_unless_it_is_the_next_number():
    _, us = split_instrument("d", "ข้อ 1 ก\nข้อ 3 ให้ใช้ตามที่กำหนด\nข้อ 2 ข\nข้อ 3 ค")
    assert [u.label for u in us] == ["ข้อ 1", "ข้อ 2", "ข้อ 3"] and "ข้อ 3 ให้ใช้ตามที่กำหนด" in us[0].text


def test_the_signature_stays_with_the_last_heading_and_the_note_is_a_unit():
    text = f"ข้อ 1 {BODY}\nข้อ 2 {BODY}\n\nให้ไว้ ณ วันที่ 9 เมษายน พ.ศ. 2567\nจุลพันธ์ อมรวิวัฒน์\nรัฐมนตรีช่วยว่าการฯ ปฏิบัติราชการแทน\nรัฐมนตรีว่าการกระทรวงการคลัง\n\nหมายเหตุ :- เหตุผลในการประกาศใช้ คือ {BODY}"
    _, us = split_instrument("d", text)
    assert [u.label for u in us] == ["ข้อ 1", "ข้อ 2", "หมายเหตุ"]
    assert us[1].text.endswith("รัฐมนตรีว่าการกระทรวงการคลัง") and us[2].text.startswith("หมายเหตุ :-")


def test_an_attachment_after_the_signature_is_an_annex_unit_but_a_pointer_to_one_is_not():
    sign = "\nสั่ง ณ วันที่ 7 กุมภาพันธ์ พ.ศ. 2543\nสุชาติ เชาว์วิศิษฐ\nอธิบดีกรมสรรพากร\n"
    _, us = split_instrument("d", f"ข้อ 1 {BODY}\nข้อ 2 {BODY}{sign}คำขอยื่นแบบแสดงรายการภาษี\n{BODY * 3}")
    assert [u.type for u in us] == ["clause", "clause", "annex"] and us[2].label.startswith("คำขอยื่นแบบ")
    _, us = split_instrument("d", f"ข้อ 1 {BODY}\nข้อ 2 {BODY}{sign}แบบ ล.ย.02 >>")
    assert [u.label for u in us] == ["ข้อ 1", "ข้อ 2"] and us[1].text.endswith("แบบ ล.ย.02 >>")


def test_a_royal_decree_closes_at_the_endorsement_not_at_ให้ไว้_at_the_top():
    text = f"พระราชกฤษฎีกา\nให้ไว้ ณ วันที่ 20 มีนาคม พ.ศ. 2536\nมาตรา 1 {BODY}\nมาตรา 2 {BODY}\nผู้รับสนองพระบรมราชโองการ\nชวน หลีกภัย\nนายกรัฐมนตรี\n-----\nหมายเหตุ :- {BODY}"
    pre, us = split_instrument("d", text)
    assert pre.endswith("20 มีนาคม พ.ศ. 2536") and [u.label for u in us] == ["มาตรา 1", "มาตรา 2", "หมายเหตุ"]
    assert us[1].text.endswith("-----")


def test_an_annex_with_worked_examples_is_cut_at_each_example_and_a_form_pointer_stays_in_the_body():
    sign = "\nสั่ง ณ วันที่ 7 กุมภาพันธ์ พ.ศ. 2543\nสุชาติ เชาว์วิศิษฐ\nอธิบดีกรมสรรพากร\nแบบแจ้งรายการเพื่อการหักลดหย่อน (แบบ ล.ย.01) >>\n"
    examples = "\n".join(f"ตัวอย่างที่ {n}\nกรณีที่ {n}\n{BODY * 2}" for n in (1, 2, 3))
    _, us = split_instrument("d", f"ข้อ 1 {BODY}\nข้อ 2 {BODY}{sign}ตัวอย่างการคำนวณภาษี\n{examples}")
    assert [u.label for u in us] == ["ข้อ 1", "ข้อ 2", "ตัวอย่างที่ 1", "ตัวอย่างที่ 2", "ตัวอย่างที่ 3"]
    assert us[1].text.endswith("(แบบ ล.ย.01) >>") and us[2].text.startswith("ตัวอย่างการคำนวณภาษี") and us[3].text.startswith("ตัวอย่างที่ 2")
    assert [u.type for u in us] == ["clause", "clause", "annex", "annex", "annex"]
