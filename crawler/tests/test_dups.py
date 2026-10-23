"""crawler.dups: near-duplicate pairs and what kind of overlap each is."""

from crawler.dups import case, pairs

BODY = "ผู้มีเงินได้มีสิทธิหักลดหย่อนเบี้ยประกันชีวิตตามที่จ่ายจริงแต่ไม่เกินหนึ่งแสนบาท โดยต้องมีหลักฐานจากบริษัทประกันชีวิต "


def row(id_, family, text):
    return dict(id=id_, doc_id=id_.split("#")[0], family=family, text=text)


def test_a_copy_is_paired_and_a_short_line_is_not():
    rows = [row("Ins90#001", "guide", BODY * 2), row("Ins91#001", "guide", "**" + BODY * 2 + "**"), row("x#001", "legal", "ร้อยละ 60")]
    assert [(i, j) for i, j, *_ in pairs(rows)] == [(0, 1)]


def test_cases():
    g90, g91 = row("Ins90#001", "guide", ""), row("Ins91#001", "guide", "")
    old, new, faq = row("old#001", "legal", ""), row("new#001", "legal", ""), row("60056#001", "explainer", "")
    assert case(g90, g91, set()) == "guide_copy"
    assert case(old, new, {frozenset(("old", "new"))}) == "legal_version"
    assert case(old, new, set()) == "legal_shared"
    assert case(faq, old, set()) == "quotation"
    assert case(old, row("old#002", "legal", ""), set()) == "same_doc"
