"""Page kind / role / tax year for the first-pass pages. Same rules as notebooks/review.py, so the two agree."""

import re


def kind(p: dict) -> str:
    t = p["text"] or ""
    # Must be numbered ("มาตรา 38", "หมวด 3"): "หมวดค่าลดหย่อนบุตร" is a Q&A category, not a statute.
    if re.match(r"\s*(มาตรา|หมวด|ลักษณะ)\s*\d", p["heading"]):
        return "statute"
    if len(p["content_links"]) >= 50:
        return "index"
    if re.search(r"\|\s*เลขที่หนังสือ\s*\|", t):  # rulings have it as a table row
        return "ruling"
    if re.search(r"^(Q\d+|คำถาม)\s*:", t, re.M):
        return "faq"
    return "article"


def role(p: dict) -> str:
    """hub = page that is mostly a list of links; thin = too short to answer anything."""
    body = len(re.sub(r"\s+", "", p["text"] or ""))
    link_chars = sum(len(re.sub(r"\s+", "", link["title"])) for link in p["content_links"])
    if body < 1000 and link_chars / max(body, 1) > 0.5:
        return "hub"
    return "thin" if body < 300 else "content"


def tax_year(p: dict) -> int | None:
    """Tax year (พ.ศ.) the page is about: heading/title first, then the first mention in the body."""
    for s in (f"{p['heading']} {p['title']}", p["text"] or ""):
        m = re.search(r"ปีภาษี\s*(25\d\d)|ปี\s*(25\d\d)", s)
        if m:
            return int(m.group(1) or m.group(2))
    return None
