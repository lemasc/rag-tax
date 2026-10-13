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
    ## 5. Candidate links to crawl next

    Every sidebar and body link found so far, deduplicated. Filter, select rows, pick a decision
    (**crawl** / **defer** / **drop**) and apply. Decisions are saved to `data/link_decisions.csv`
    and decided links are hidden from the table (also on the next run). To undo a decision, delete its row from the CSV.
    """)
    return


@app.cell
def _(Path, pages):
    from urllib.parse import urlparse as _urlparse

    def link_type(url):
        _path = _urlparse(url).path.lower()
        if _path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".ppt", ".pptx")):
            return "file"
        if _path.endswith(".html"):
            return "page"
        return "other"

    def norm(url):
        return url.replace("http://", "https://").replace("://rd.go.th", "://www.rd.go.th").rstrip("/")

    _seen_urls = {norm(_l.strip()) for _l in Path("links.txt").read_text().splitlines() if _l.strip()}
    _seen_urls |= {norm(_p["url"]) for _p in pages}

    _cand = {}
    for _p in pages:
        for _src, _links in (("sidebar", _p["related_links"]), ("body", _p["content_links"])):
            for _l in _links:
                _u = norm(_l["url"])
                _c = _cand.setdefault(_u, {"url": _u, "title": _l["title"], "sources": set(), "linked_from": {}})
                _c["sources"].add(_src)
                _c["linked_from"].setdefault(_p["id"], set()).add(_src)
                if len(_l["title"]) > len(_c["title"]):
                    _c["title"] = _l["title"]

    _heading = {_p["id"]: _p["heading"] for _p in pages}

    def _parent_summary(parents, max_titles=2, max_len=24):
        _ids = sorted(parents)
        _titles = [_heading[_i] if len(_heading[_i]) <= max_len else _heading[_i][:max_len] + "…" for _i in _ids[:max_titles]]
        return f"{len(_ids)}: " + "; ".join(_titles) + (" …" if len(_ids) > max_titles else "")

    candidates = [
        {
            "url": _c["url"],
            "title": _c["title"][:90],
            "type": link_type(_c["url"]),
            "domain": _urlparse(_c["url"]).netloc,
            "source": "+".join(sorted(_c["sources"])),
            "n_pages": len(_c["linked_from"]),
            "linked_from": _parent_summary(_c["linked_from"]),
            "crawled": _c["url"] in _seen_urls,
        }
        for _c in _cand.values()
    ]
    candidates.sort(key=lambda r: (-r["n_pages"], r["url"]))
    parents_of = {_u: _c["linked_from"] for _u, _c in _cand.items()}  # url -> {parent id: {sources}}
    return candidates, parents_of


@app.cell
def _(Path, mo):
    import csv

    DECISIONS_PATH = Path("data/link_decisions.csv")
    DECISION_FIELDS = ["url", "decision", "tier", "title", "type", "domain", "n_pages", "decided_at"]

    def load_decisions():
        if not DECISIONS_PATH.exists():
            return {}
        with DECISIONS_PATH.open(encoding="utf-8", newline="") as _f:
            return {_r["url"]: _r for _r in csv.DictReader(_f)}

    get_decisions, set_decisions = mo.state(load_decisions())
    return DECISIONS_PATH, DECISION_FIELDS, csv, get_decisions, set_decisions


@app.cell
def _(candidates, mo, pages):
    def _opts(key):
        return sorted({r[key] for r in candidates})

    f_type = mo.ui.multiselect(_opts("type"), value=["page"], label="Type")
    f_source = mo.ui.multiselect(_opts("source"), value=_opts("source"), label="Found in")
    f_domain = mo.ui.multiselect(_opts("domain"), value=["www.rd.go.th"], label="Domain")
    f_new = mo.ui.checkbox(value=True, label="Hide already crawled")
    f_status = mo.ui.multiselect(
        ["undecided", "crawl", "defer", "drop"], value=["undecided"], label="Decision status",
    )
    f_text = mo.ui.text(placeholder="title or URL contains…", label="Search")
    _label = {f"{_p['id']} · {_p['kind']} · {_p['heading'][:40]}": _p["id"] for _p in pages}
    f_parent = mo.ui.multiselect(_label, value=list(_label), label="Linked from page", full_width=True)
    f_max = mo.ui.slider(1, max(r["n_pages"] for r in candidates), value=1, label="Min. pages linking")
    # Lives here (not next to the apply button) so ticking rows doesn't reset it.
    action = mo.ui.radio(["crawl", "defer", "drop"], value="crawl", inline=True, label="Decision for selected")
    tier = mo.ui.text(value="later", label="Defer tier name")
    mo.vstack([
        mo.hstack([f_type, f_source, f_domain, f_status], justify="start", gap=2),
        mo.hstack([f_text, f_max, f_new], justify="start", gap=2, align="end"),
        f_parent,
    ])
    return (
        action,
        f_domain,
        f_max,
        f_new,
        f_parent,
        f_source,
        f_status,
        f_text,
        f_type,
        tier,
    )


@app.cell
def _(
    candidates,
    f_domain,
    f_max,
    f_new,
    f_parent,
    f_source,
    f_status,
    f_text,
    f_type,
    get_decisions,
    mo,
    parents_of,
):
    _q = f_text.value.strip().lower()
    _parent_ids = set(f_parent.value)
    _decided = get_decisions()

    def _status(url):
        return _decided[url]["decision"] if url in _decided else "undecided"

    def _decision_label(url):
        if url not in _decided:
            return ""
        _d = _decided[url]
        return f"{_d['decision']}: {_d['tier']}" if _d.get("tier") else _d["decision"]

    filtered = [
        {**r, "decision": _decision_label(r["url"])} for r in candidates
        if _status(r["url"]) in f_status.value
        and r["type"] in f_type.value
        and _parent_ids & set(parents_of[r["url"]])
        and r["source"] in f_source.value
        and r["domain"] in f_domain.value
        and r["n_pages"] >= f_max.value
        and not (f_new.value and r["crawled"])
        and (not _q or _q in r["title"].lower() or _q in r["url"].lower())
    ]
    table = mo.ui.table(filtered, selection="multi", page_size=25, label=f"{len(filtered)} of {len(candidates)} candidates ({len(_decided)} decided in total; pick statuses above to show them)")
    # Separate from the table's selection, so viewing parents never changes what gets written.
    view_link = mo.ui.dropdown(
        {f"{r['title'][:50] or r['url']} · {r['n_pages']}p · {r['url'].rsplit('/', 1)[-1]}": r["url"] for r in filtered[:500]},
        value=None, searchable=True, label="View parents of", full_width=True,
    )
    mo.vstack([view_link, table])
    return table, view_link


@app.cell
def _(mo, pages, parents_of, view_link):
    mo.stop(view_link.value is None)
    _by_id = {_p["id"]: _p for _p in pages}
    _rows = [
        {"parent": _id, "kind": _by_id[_id]["kind"], "heading": _by_id[_id]["heading"][:70],
         "via": "+".join(sorted(_srcs)), "breadcrumb": " > ".join(_by_id[_id]["breadcrumb"][-2:])}
        for _id, _srcs in sorted(parents_of[view_link.value].items())
    ]
    mo.vstack([mo.md(f"**{len(_rows)} parent page(s)** of `{view_link.value}`"), mo.ui.table(_rows, selection=None, page_size=10)])
    return


@app.cell
def _(action, mo, table, tier):
    _n = len(table.value)
    _tier = tier.value.strip()
    _is_defer = action.value == "defer"
    _label = f"Apply 'defer: {_tier}'" if _is_defer else f"Apply '{action.value}'"
    write_btn = mo.ui.run_button(
        label=f"{_label} to {_n} selected",
        disabled=_n == 0 or (_is_defer and not _tier),
    )
    mo.hstack([action, tier if _is_defer else mo.md(""), write_btn], justify="start", gap=2, align="end")
    return (write_btn,)


@app.cell
def _(
    DECISIONS_PATH,
    DECISION_FIELDS,
    action,
    csv,
    datetime,
    mo,
    set_decisions,
    table,
    tier,
    write_btn,
):
    mo.stop(not write_btn.value)
    _now = datetime.now().isoformat(timespec="seconds")
    _tier = tier.value.strip() if action.value == "defer" else ""
    _new = {
        r["url"]: {
            **{k: r[k] for k in ("url", "title", "type", "domain", "n_pages")},
            "decision": action.value, "tier": _tier, "decided_at": _now,
        }
        for r in table.value
    }

    def _merge(current):
        merged = {**current, **_new}
        DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DECISIONS_PATH.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=DECISION_FIELDS)
            w.writeheader()
            w.writerows(merged.values())
        return merged

    set_decisions(_merge)  # re-runs the filter cell, so these rows disappear from the table
    mo.md(f"Marked **{len(_new)}** link(s) as `{action.value}{': ' + _tier if _tier else ''}` in `{DECISIONS_PATH}`")
    return


@app.cell
def _(mo):
    mo.md("""
    ## 6. Review checklist (beyond related-link filtering)

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
