import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import json
    import re
    from collections import Counter
    from datetime import datetime
    from pathlib import Path

    import marimo as mo

    ROOT = Path(__file__).resolve().parents[1]

    return ROOT, Counter, Path, datetime, json, mo, re


@app.cell
def _(ROOT, Path, json, mo):
    pages = [json.loads(l) for l in (ROOT / "data/pages.jsonl").read_text(encoding="utf-8").splitlines()]
    for _p in pages:
        _p["id"] = _p["url"].rsplit("/", 1)[-1].removesuffix(".html")
        _p["n_chars"] = len(_p["text"] or "")
    mo.md(f"# First-pass review\n**{len(pages)} pages** loaded from `data/pages.jsonl`.")
    return (pages,)


@app.cell
def _(datetime, mo, pages, re):
    def kind(_p):
        t = _p["text"] or ""
        # Must be numbered ("มาตรา 38", "หมวด 3"): "หมวดค่าลดหย่อนบุตร" is a Q&A category, not a statute.
        if re.match(r"\s*(มาตรา|หมวด|ลักษณะ)\s*\d", _p["heading"]):
            return "statute"
        if len(_p["content_links"]) >= 50:
            return "index/list"
        if re.search(r"\|\s*เลขที่หนังสือ\s*\|", t):  # rulings have it as a table row; plain text also matches หนังสือเดินทาง
            return "ruling (หนังสือตอบข้อหารือ)"
        if re.search(r"^(Q\d+|คำถาม)\s*:", t, re.M):
            return "FAQ"
        return "article"

    def role(_p):
        """hub = page that is mostly a list of links; thin = too short to answer anything."""
        _body = len(re.sub(r"\s+", "", _p["text"] or ""))
        _link_chars = sum(len(re.sub(r"\s+", "", _l["title"])) for _l in _p["content_links"])
        if _body < 1000 and _link_chars / max(_body, 1) > 0.5:
            return "hub"
        return "thin" if _body < 300 else "content"

    def tax_year(_p):
        """Tax year (พ.ศ.) the page is about: heading/title first, then the first mention in the body."""
        for _s in (f"{_p['heading']} {_p['title']}", _p["text"] or ""):
            _m = re.search(r"ปีภาษี\s*(25\d\d)|ปี\s*(25\d\d)", _s)
            if _m:
                return int(_m.group(1) or _m.group(2))
        return None

    for _p in pages:
        _p["kind"] = kind(_p)
        _p["role"] = role(_p)
        _p["tax_year"] = tax_year(_p)

    # Crawl batches: pages fetched within 5 minutes of each other share a batch number.
    _prev, _n = None, 0
    for _p in sorted(pages, key=lambda _p: _p.get("fetched_at") or ""):
        _t = datetime.fromisoformat(_p["fetched_at"]) if _p.get("fetched_at") else None
        if _t is None or _prev is None or (_t - _prev).total_seconds() > 300:
            _n += 1
        _p["batch"] = _n
        _prev = _t

    mo.md("## 1. Overview: page type, role, tax year, freshness")
    return


@app.cell
def _(datetime, mo, pages):
    def year(_p):
        d = _p["last_update"]
        return datetime.strptime(d, "%d-%m-%Y").year if d else None

    rows = [
        {
            "id": _p["id"], "url": _p["url"], "kind": _p["kind"], "role": _p["role"], "tax_year": _p["tax_year"], "heading": _p["heading"][:60],
            "batch": _p["batch"], "fetched": (_p.get("fetched_at") or "")[:16].replace("T", " "),
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
    _batches = {}
    for r in rows:
        _batches.setdefault(r["batch"], []).append(r["fetched"])
    mo.md(
        "**By crawl batch:** " + ", ".join(f"#{b}: {len(v)} pages ({min(v)})" for b, v in sorted(_batches.items()))
        + "\n\n**By kind:** " + ", ".join(f"{k}: {v}" for k, v in kinds.most_common())
        + "\n\n**By role:** " + ", ".join(f"{k}: {v}" for k, v in Counter(r["role"] for r in rows).most_common())
        + "\n\n**By last-update year:** " + ", ".join(f"{k}: {v}" for k, v in sorted(years.items(), key=lambda x: str(x[0])))
        + "\n\n**By tax year the page is about (พ.ศ.):** " + ", ".join(f"{k}: {v}" for k, v in sorted(Counter(r["tax_year"] for r in rows).items(), key=lambda x: str(x[0])))
        + "\n\n> Review: `last_update` is when the page was edited, not which tax year it describes; a 2021 edit can still be 2560 content. "
        "Decide how stale tax years and `hub`/`thin` pages should be treated downstream."
    )
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2. Extraction quality (what was lost, not how clean it is)
    """)
    return


@app.cell
def _(mo, pages, re):
    checks = []
    for _p in pages:
        t = _p["text"] or ""
        issues = []
        if _p["role"] != "content":
            issues.append(_p["role"])
        if _p["n_chars"] > 15000:
            issues.append("very long")
        if re.search(r"\|.*\|", t):
            issues.append("has table(s)")
        if re.search(r"(ดู|คลิก|ที่นี่)", t) and _p["content_links"]:
            issues.append("text refers to links we dropped")
        if any(_l["url"].lower().split("?")[0].endswith((".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx")) for _l in _p["content_links"]):
            issues.append("content in non-HTML file")
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
    ## 3. Page viewer
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
        f"role {sel['role']} · tax year {sel['tax_year'] or '?'} · {sel['n_chars']:,} chars · {len(sel['content_links'])} body links · {len(sel['related_links'])} sidebar links\n\n"
        f"breadcrumb: {' > '.join(sel['breadcrumb'])}"
    )
    _body = mo.md(to_markdown(sel["text"])) if view.value == "rendered" else mo.md("```text\n" + (sel["text"] or "") + "\n```")
    mo.vstack([_meta, mo.callout(_body, kind="neutral")])
    return


@app.cell
def _(mo):
    mo.md("""
    ## 3b. Page decisions

    Mark crawled pages as **keep**, **exclude** (drop from the corpus) or **flag** (needs another look, e.g. content lives in a PDF).
    Decisions and notes are saved to `data/page_decisions.csv`, which is the source of truth for downstream stages.
    To undo a decision, delete its row from the CSV.
    """)
    return


@app.cell
def _(ROOT, Path, mo):
    import csv as _csv

    PAGE_DECISIONS_PATH = ROOT / "data/page_decisions.csv"
    PAGE_DECISION_FIELDS = ["id", "decision", "note", "decided_at"]

    def load_page_decisions():
        if not PAGE_DECISIONS_PATH.exists():
            return {}
        with PAGE_DECISIONS_PATH.open(encoding="utf-8", newline="") as _f:
            return {_r["id"]: _r for _r in _csv.DictReader(_f)}

    get_page_decisions, set_page_decisions = mo.state(load_page_decisions())
    return (
        PAGE_DECISIONS_PATH,
        PAGE_DECISION_FIELDS,
        get_page_decisions,
        set_page_decisions,
    )


@app.cell
def _(mo, pages):
    pf_status = mo.ui.multiselect(
        ["undecided", "keep", "exclude", "flag"], value=["undecided"], label="Decision status",
    )
    pf_role = mo.ui.multiselect(
        sorted({_p["role"] for _p in pages}), value=sorted({_p["role"] for _p in pages}), label="Role",
    )
    pf_kind = mo.ui.multiselect(
        sorted({_p["kind"] for _p in pages}), value=sorted({_p["kind"] for _p in pages}), label="Kind",
    )
    _years = sorted({_p["tax_year"] for _p in pages if _p["tax_year"]})
    pf_year = mo.ui.multiselect(
        [str(_y) for _y in _years] + ["unknown"], value=[str(_y) for _y in _years] + ["unknown"], label="Tax year",
    )
    pf_action = mo.ui.radio(["keep", "exclude", "flag"], value="keep", inline=True, label="Decision for selected")
    pf_note = mo.ui.text(placeholder="optional note, applied to all selected", label="Note", full_width=True)
    mo.vstack([
        mo.hstack([pf_status, pf_role, pf_kind, pf_year], justify="start", gap=2),
        mo.hstack([pf_action, pf_note], justify="start", gap=2, align="end"),
    ])
    return pf_action, pf_kind, pf_note, pf_role, pf_status, pf_year


@app.cell
def _(get_page_decisions, mo, pages, pf_kind, pf_role, pf_status, pf_year):
    _decided = get_page_decisions()
    page_rows = [
        {
            "id": _p["id"], "url": _p["url"], "decision": _decided[_p["id"]]["decision"] if _p["id"] in _decided else "",
            "note": _decided[_p["id"]]["note"] if _p["id"] in _decided else "",
            "kind": _p["kind"], "role": _p["role"], "tax_year": _p["tax_year"], "updated": _p["last_update"],
            "chars": _p["n_chars"], "heading": _p["heading"][:60],
        }
        for _p in pages
        if (_decided[_p["id"]]["decision"] if _p["id"] in _decided else "undecided") in pf_status.value
        and _p["role"] in pf_role.value
        and _p["kind"] in pf_kind.value
        and str(_p["tax_year"] or "unknown") in pf_year.value
    ]
    page_table = mo.ui.table(
        page_rows, selection="multi", page_size=25,
        label=f"{len(page_rows)} of {len(pages)} pages ({len(_decided)} decided; pick statuses above to show them)",
    )
    page_table
    return (page_table,)


@app.cell
def _(mo, page_table, pf_action):
    page_write_btn = mo.ui.run_button(
        label=f"Apply '{pf_action.value}' to {len(page_table.value)} selected",
        disabled=len(page_table.value) == 0,
    )
    page_write_btn
    return (page_write_btn,)


@app.cell
def _(
    PAGE_DECISIONS_PATH,
    PAGE_DECISION_FIELDS,
    csv,
    datetime,
    mo,
    page_table,
    page_write_btn,
    pf_action,
    pf_note,
    set_page_decisions,
):
    mo.stop(not page_write_btn.value)
    _now = datetime.now().isoformat(timespec="seconds")
    _new = {
        r["id"]: {"id": r["id"], "decision": pf_action.value, "note": pf_note.value.strip(), "decided_at": _now}
        for r in page_table.value
    }

    def _merge_pages(current):
        merged = {**current, **_new}
        PAGE_DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with PAGE_DECISIONS_PATH.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=PAGE_DECISION_FIELDS)
            w.writeheader()
            w.writerows(merged.values())
        return merged

    set_page_decisions(_merge_pages)
    mo.md(f"Marked **{len(_new)}** page(s) as `{pf_action.value}` in `{PAGE_DECISIONS_PATH}`")
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
def _(ROOT, Path, pages):
    from urllib.parse import urlparse as _urlparse

    def link_type(url):
        _path = _urlparse(url).path.lower()
        if _path.endswith((".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar", ".ppt", ".pptx")):
            return "file"
        if _path.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
            return "image"
        if _path.endswith(".html"):
            return "page"
        return "other"

    def norm(url):
        return url.replace("http://", "https://").replace("://rd.go.th", "://www.rd.go.th").replace("://cmsinteradmin.rd.go.th", "://www.rd.go.th").rstrip("/")

    _seen_urls = {norm(_l.strip()) for _l in (ROOT / "links.txt").read_text().splitlines() if _l.strip()}
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
def _(ROOT, Path, mo):
    import csv

    DECISIONS_PATH = ROOT / "data/link_decisions.csv"
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
    ## 6. Review checklist

    What to judge here:

    1. **Staleness**: `tax_year` vs `last_update`. Do old tax years (2560 deductions, 2016 explainers) stay, get flagged, or go?
    2. **Role**: `hub` and `thin` pages carry no answer by themselves. Keep for breadcrumb context only, or exclude?
    3. **Kind-specific structure**: rulings need `เรื่อง` promoted to title; statute pages and FAQs are long and have natural sections.
    4. **Table fidelity**: tables flatten to `| a | b |` rows. Compare wide ones (e.g. `59674`) with the source.
    5. **Content outside HTML**: PDFs and images hold rates, deduction tables and infographics (see "content in non-HTML file").
    6. **Dropped inline links**: text like "ดู…" loses its target since `include_links=False`.
    7. **Date format**: `last_update` is `dd-mm-yyyy`, text uses Buddhist years (พ.ศ.).

    **Deliberately not handled here** (needs its own pass once PDF/image formats are in): whitespace and `nbsp`
    cleanup, boilerplate stripping, exact and semantic deduplication.
    """)
    return


if __name__ == "__main__":
    app.run()
