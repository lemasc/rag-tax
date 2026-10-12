import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import re
    from collections import Counter
    from datetime import datetime
    from itertools import combinations
    from pathlib import Path

    import marimo as mo

    return Counter, Path, combinations, datetime, json, mo, re


@app.cell
def _(Path, json, mo):
    pages = [json.loads(l) for l in Path("data/pages.jsonl").read_text(encoding="utf-8").splitlines()]
    for _p in pages:
        _p["id"] = _p["url"].rsplit("/", 1)[-1].removesuffix(".html")
        _p["n_chars"] = len(_p["text"] or "")
    mo.md(f"# First-pass review\n**{len(pages)} pages** loaded from `data/pages.jsonl`.")
    return (pages,)


@app.cell
def _(mo, pages, re):
    def kind(_p):
        t = _p["text"] or ""
        if re.match(r"\s*มาตรา|หมวด", _p["heading"]):
            return "statute"
        if len(_p["content_links"]) >= 50:
            return "index/list"
        if re.search(r"เลขที่หนังสือ", t):
            return "ruling (หนังสือตอบข้อหารือ)"
        if re.search(r"^Q\d+\s*:", t, re.M):
            return "FAQ"
        return "article"

    for _p in pages:
        _p["kind"] = kind(_p)

    mo.md("## 1. Overview: page type, size, freshness")
    return


@app.cell
def _(datetime, mo, pages):
    def year(_p):
        d = _p["last_update"]
        return datetime.strptime(d, "%d-%m-%Y").year if d else None

    rows = [
        {
            "id": _p["id"], "kind": _p["kind"], "heading": _p["heading"][:60],
            "chars": _p["n_chars"], "updated": _p["last_update"], "year": year(_p),
            "body_links": len(_p["content_links"]), "side_links": len(_p["related_links"]),
            "breadcrumb": " > ".join(_p["breadcrumb"][-3:]),
        }
        for _p in pages
    ]
    mo.ui.table(rows, page_size=40, selection=None)
    return (rows,)


@app.cell
def _(Counter, mo, rows):
    kinds = Counter(r["kind"] for r in rows)
    years = Counter(r["year"] for r in rows)
    mo.md(
        "**By kind:** " + ", ".join(f"{k}: {v}" for k, v in kinds.most_common())
        + "\n\n**By last-update year:** " + ", ".join(f"{k}: {v}" for k, v in sorted(years.items(), key=lambda x: str(x[0])))
        + "\n\n> Review: do you want rulings/old pages treated differently? "
        "Tax law changes yearly, so stale pages (2020) can contradict newer ones."
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2. Duplicates: exact and near
    """)
    return


@app.cell
def _(combinations, mo, pages, re):
    def shingles(t, n=5):
        t = re.sub(r"\s+", "", t or "")
        return {t[i:i + n] for i in range(max(len(t) - n + 1, 1))}

    sh = {_p["id"]: shingles(_p["text"]) for _p in pages}
    pairs = []
    for a, b in combinations(pages, 2):
        sa, sb = sh[a["id"]], sh[b["id"]]
        j = len(sa & sb) / len(sa | sb)
        contain = len(sa & sb) / min(len(sa), len(sb))  # catches "A is a subset of B"
        if j > 0.3 or contain > 0.6:
            pairs.append({"a": a["id"], "b": b["id"], "jaccard": round(j, 2), "containment": round(contain, 2),
                          "a_head": a["heading"][:35], "b_head": b["heading"][:35]})
    pairs.sort(key=lambda x: -x["containment"])
    mo.vstack([mo.md(f"Pairs with Jaccard > 0.3 or containment > 0.6: **{len(pairs)}**"), mo.ui.table(pairs, selection=None)])
    return


@app.cell
def _(Counter, mo, pages):
    # Boilerplate: lines repeated across many pages
    line_pages = Counter()
    for _p in pages:
        for ln in {l.strip() for l in (_p["text"] or "").splitlines() if len(l.strip()) > 15}:
            line_pages[ln] += 1
    rep = [{"pages": c, "line": l[:120]} for l, c in line_pages.most_common(15) if c > 1]
    mo.vstack([mo.md("### Lines repeated across pages (boilerplate / shared paragraphs)"), mo.ui.table(rep, selection=None)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3. Extraction quality
    """)
    return


@app.cell
def _(mo, pages, re):
    checks = []
    for _p in pages:
        t = _p["text"] or ""
        issues = []
        if _p["n_chars"] < 300:
            issues.append("very short")
        if _p["n_chars"] > 15000:
            issues.append("needs chunking")
        if "&nbsp;" in t or "\xa0" in t:
            issues.append("nbsp")
        if re.search(r"\|.*\|", t):
            issues.append("has table(s)")
        if re.search(r"  +", t):
            issues.append("multi-space")
        if len(re.findall(r"\n\n\n", t)):
            issues.append("blank-line runs")
        if re.search(r"(ดู|คลิก|ที่นี่)", t) and _p["content_links"]:
            issues.append("text refers to links we dropped")
        if not _p["breadcrumb"]:
            issues.append("no breadcrumb")
        if _p["heading"] == _p["title"] and _p["kind"].startswith("ruling"):
            issues.append("title is doc number only")
        if issues:
            checks.append({"id": _p["id"], "kind": _p["kind"], "chars": _p["n_chars"], "issues": ", ".join(issues)})
    mo.ui.table(checks, selection=None, page_size=40)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3b. Page viewer
    """)
    return


@app.cell
def _(mo, pages):
    _label = lambda _p: f"{_p['id']} · {_p['kind']} · {_p['heading'][:50]}"
    pick = mo.ui.dropdown(
        {_label(_p): _p["id"] for _p in pages}, value=_label(pages[0]), label="Page", searchable=True,
    )
    view = mo.ui.radio(["rendered", "raw text"], value="rendered", inline=True, label="View")
    mo.hstack([pick, view], justify="start", gap=2)
    return pick, view


@app.cell
def _(mo, pages, pick, view):
    def to_markdown(text: str) -> str:
        """Trafilatura's txt output -> renderable markdown.

        Lines are separate paragraphs; consecutive `| a | b |` rows become a table
        (a separator row is inserted after the first row, which markdown requires).
        """
        out, in_table = [], False
        for line in (text or "").replace("\xa0", " ").splitlines():
            line = line.rstrip()
            if line.startswith("|") and line.endswith("|"):
                if not in_table:
                    out.append("")
                    out.append(line)
                    out.append("|" + "---|" * (line.count("|") - 1))
                    in_table = True
                else:
                    out.append(line)
                continue
            if in_table:
                out.append("")
                in_table = False
            if line.strip():
                out.append(line)
                out.append("")
        return "\n".join(out)

    sel = next(_p for _p in pages if _p["id"] == pick.value)
    _meta = mo.md(
        f"### {sel['heading']}\n"
        f"[{sel['url']}]({sel['url']}) · **{sel['kind']}** · updated {sel['last_update']} · "
        f"{sel['n_chars']:,} chars · {len(sel['content_links'])} body links · {len(sel['related_links'])} sidebar links\n\n"
        f"breadcrumb: {' > '.join(sel['breadcrumb'])}"
    )
    _body = mo.md(to_markdown(sel["text"])) if view.value == "rendered" else mo.md("```text\n" + (sel["text"] or "") + "\n```")
    mo.vstack([_meta, mo.callout(_body, kind="neutral")])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. Body links (separate from sidebar related links)
    """)
    return


@app.cell
def _(Counter, mo, pages):
    from urllib.parse import urlparse

    def cls(u):
        h = urlparse(u)
        if u.lower().split("?")[0].endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip")):
            return "file"
        return "rd.go.th page" if h.netloc.endswith("rd.go.th") else "external"

    c = Counter(cls(l["url"]) for _p in pages for l in _p["content_links"])
    top = [{"id": _p["id"], "heading": _p["heading"][:40], "body_links": len(_p["content_links"]),
            **{k: sum(cls(l["url"]) == k for l in _p["content_links"]) for k in ("rd.go.th page", "file", "external")}}
           for _p in sorted(pages, key=lambda _p: -len(_p["content_links"])) if _p["content_links"]][:12]
    mo.vstack([mo.md("Link targets in article bodies: " + str(dict(c))), mo.ui.table(top, selection=None)])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Review checklist (beyond related-link filtering)

    1. **Staleness / superseded content**: check `year` column. Multiple tax years (e.g. 2560 deduction table vs current) may conflict.
       Decide whether to keep `last_update` as metadata and whether to drop or flag old pages.
    2. **Near-duplicates**: sidebar-driven page sets repeat statements; see pair table. Pick keep rule (newest? longest?).
    3. **Page-type specific handling**: rulings need `เรื่อง`/`ข้อกฎหมาย` fields promoted to title; statute pages are huge → chunk by `มาตรา`; FAQs → chunk by Q/A.
    4. **Table fidelity**: tables flatten to `| a | b |` rows; cell line breaks are lost; wide deduction tables may be unreadable. Compare against the source for those pages.
    5. **Thin pages**: very short pages (< 300 chars) may be low-value without their siblings; consider merging into parent via breadcrumb.
    6. **Non-HTML targets**: PDFs referenced from body/sidebar hold substantive content (rates, deductions) that this pass doesn't capture.
    7. **Date format**: `last_update` is `dd-mm-yyyy` and may be Gregorian; text uses Buddhist years (พ.ศ.). Normalize before comparing.
    8. **Dropped inline links**: text such as "ดู…" loses its target since `include_links=False`.
    9. **Inline `<typohead>`/styled headings**: some pages (e.g. `59674`) use custom tags; heading is only recovered from `<title>`.
    """)
    return


if __name__ == "__main__":
    app.run()
