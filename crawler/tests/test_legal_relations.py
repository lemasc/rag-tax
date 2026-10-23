"""crawler.legal_relations: amend and repeal relations proposed from the instruments' own clauses."""

from crawler.legal_relations import own_number, proposals

HEAD = "ประกาศอธิบดีกรมสรรพากร เกี่ยวกับภาษีเงินได้ (ฉบับที่ {n})\nอาศัยอำนาจตามความในมาตรา 3 อัฏฐ แห่งประมวลรัษฎากร ซึ่งแก้ไขเพิ่มเติมโดยพระราชบัญญัติแก้ไขเพิ่มเติมประมวลรัษฎากร (ฉบับที่ 10)"


def doc(doc_id, n, title=None):
    return dict(doc_id=doc_id, source="legal", kind="ประกาศอธิบดี", title=title or f"ฉบับที่ {n} เรื่อง", text=HEAD.format(n=n))


def test_the_heading_number_beats_the_listing_title():
    assert own_number(doc("a", 165, title="ฉบับที่ 224 กำหนดหลักเกณฑ์")) == "165"  # consolidated, listed under its last amendment
    assert own_number(dict(doc("b", 86), title="เรื่อง หลักฐานการหักลดหย่อน")) is None  # no number of its own


def test_a_listed_repeal_names_each_instrument():
    text = ("ข้อ 1 ให้ยกเลิก\n(1) ประกาศอธิบดีกรมสรรพากร เกี่ยวกับภาษีเงินได้ (ฉบับที่ 58) เรื่อง กำหนดแบบ\n"
            "(2) ประกาศอธิบดีกรมสรรพากร เกี่ยวกับภาษีเงินได้ (ฉบับที่ 438) เรื่อง กำหนดแบบ")
    rows = proposals([doc("new", 451), doc("old", 438)], [dict(unit_id="new#001", doc_id="new", text=text)])
    assert [(r["relation"], r["target_number"], r["target_doc_id"]) for r in rows] == [("repeals", "58", ""), ("repeals", "438", "old")]


def test_repealing_a_part_is_an_amendment_with_its_scope():
    text = "ข้อ 1 ให้ยกเลิกข้อ 4 ของประกาศอธิบดีกรมสรรพากร เกี่ยวกับภาษีเงินได้ (ฉบับที่ 182) เรื่อง กำหนดหลักเกณฑ์"
    (row,) = proposals([doc("new", 242)], [dict(unit_id="new#001", doc_id="new", text=text)])
    assert (row["relation"], row["scope"], row["target_number"]) == ("amends", "ข้อ 4 ของ", "182")


def test_the_code_amendment_act_is_not_a_target():
    text = "ข้อ 1 ให้เพิ่มความต่อไปนี้ ตามมาตรา 42 แห่งประมวลรัษฎากร ซึ่งแก้ไขเพิ่มเติมโดยพระราชบัญญัติแก้ไขเพิ่มเติมประมวลรัษฎากร (ฉบับที่ 10)"
    assert proposals([doc("new", 1)], [dict(unit_id="new#001", doc_id="new", text=text)]) == []
