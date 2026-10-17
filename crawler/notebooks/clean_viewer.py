import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import csv
    import hashlib
    import html
    import json
    import re
    from collections import Counter
    from pathlib import Path

    import marimo as mo

    from crawler.clean.text import normalize

    return Counter, Path, csv, hashlib, html, json, mo, normalize, re


@app.cell
def _(Path, json, mo):
    docs = [json.loads(l) for l in Path("data/clean/documents.jsonl").read_text(encoding="utf-8").splitlines()]
    units = [json.loads(l) for l in Path("data/clean/units.jsonl").read_text(encoding="utf-8").splitlines()]
    by_id = {_d["doc_id"]: _d for _d in docs}
    units_of = {}
    for _u in units:
        units_of.setdefault(_u["doc_id"], []).append(_u)
    mo.md(f"""
    # Cleaned data viewer

    **{len(docs)} documents** ({sum(_d["include"] for _d in docs)} included) and **{len(units)} units** from `data/clean/`
    (built by `uv run python -m crawler.clean.build`). Pick a document to compare the **original** with the **cleaned** text side by side
    (PDFs are embedded when `data/raw/legal` is present), see what `normalize` changed, and check the numbers (useful for the 11 OCR documents).
    Units (FAQ items, statute sections) are browsed in section 2.
    """)
    return by_id, docs, units, units_of


@app.cell
def _(Path, csv, hashlib, html, json, mo, re):
    from crawler.clean.audit import page_source_parts
    from crawler.legal import doc_text

    RAW = Path("data/raw")
    page_raw = {
        _p["url"].rsplit("/", 1)[-1].removesuffix(".html"): _p["text"] or ""
        for _p in map(json.loads, Path("data/pages.jsonl").open(encoding="utf-8"))
    }
    legal_file = {_r["url"]: _r["file"] for _r in csv.DictReader(Path("data/legal_text.csv").open(encoding="utf-8"))}

    def pre_clean_text(d):
        """The text as it was before `normalize` (trafilatura output / cached legal text)."""
        if d["source"] == "page":
            return page_raw[d["doc_id"]]
        return Path("data/text/legal", legal_file[d["url"]]).read_text(encoding="utf-8")

    def pdf_path(d):
        if d["source"] == "legal" and d["url"].endswith(".pdf"):
            _p = RAW / "legal" / (hashlib.sha1(d["url"].encode()).hexdigest()[:12] + ".pdf")
            return _p if _p.exists() else None

    def original_text(d):
        """Visible text of the raw HTML source, or None if there is none / it is not downloaded."""
        if d["source"] == "page":
            _p = RAW / f"{d['doc_id']}.html"
            return "\n".join(page_source_parts(_p)) if _p.exists() else None
        if d["url"].endswith(".html"):
            _p = RAW / "legal" / (hashlib.sha1(d["url"].encode()).hexdigest()[:12] + ".html")
            return doc_text(_p) if _p.exists() else None

    def scroll(text, height="72vh"):
        return mo.Html(
            f'<div style="height:{height};overflow:auto;white-space:pre-wrap;font-size:13px;line-height:1.55;'
            f'border:1px solid var(--gray-6, #ccc);border-radius:6px;padding:10px">{html.escape(text)}</div>'
        )

    def visible(s):
        """Make invisible characters show up: nbsp, zero-width and cp1252 control characters."""
        s = re.sub(r"[\x80-\x9f]", lambda m: f"⟨x{ord(m.group()):02x}⟩", s)
        return s.replace("\xa0", "⍽").replace("​", "⟨zw⟩")

    return original_text, pdf_path, pre_clean_text, scroll, visible


@app.cell
def _(docs, mo):
    f_source = mo.ui.multiselect(["page", "legal"], value=["page", "legal"], label="Source")
    f_kind = mo.ui.multiselect(sorted({_d["kind"] for _d in docs}), label="Kind (empty = all)")
    f_method = mo.ui.multiselect(sorted({_d["text_method"] for _d in docs}), label="Text method (empty = all)")
    f_inc = mo.ui.radio(["all", "included", "excluded"], value="all", inline=True, label="Include rule")
    f_units = mo.ui.checkbox(label="Has units")
    f_flags = mo.ui.checkbox(label="Has known issue")
    f_q = mo.ui.text(placeholder="id, name (mr397), title or URL contains…", label="Search")
    mo.vstack([
        mo.md("## 1. Documents"),
        mo.hstack([f_source, f_kind, f_method, f_inc], justify="start", gap=2, wrap=True),
        mo.hstack([f_units, f_flags, f_q], justify="start", gap=2, align="end"),
    ])
    return f_flags, f_inc, f_kind, f_method, f_q, f_source, f_units


@app.cell
def _(docs, f_flags, f_inc, f_kind, f_method, f_q, f_source, f_units, mo):
    _q = f_q.value.strip().lower()
    shown = [
        _d for _d in docs
        if _d["source"] in f_source.value
        and (not f_kind.value or _d["kind"] in f_kind.value)
        and (not f_method.value or _d["text_method"] in f_method.value)
        and (f_inc.value == "all" or _d["include"] == (f_inc.value == "included"))
        and (not f_units.value or _d["n_units"])
        and (not f_flags.value or _d["flags"])
        and (not _q or _q in _d["doc_id"].lower() or _q in _d["title"].lower() or _q in _d["url"].lower())
    ]
    table = mo.ui.table(
        [
            {
                "id": _d["doc_id"], "name": _d["url"].rsplit("/", 1)[-1], "source": _d["source"], "kind": _d["kind"], "method": _d["text_method"], "role": _d["role"],
                "year": _d.get("year") or _d.get("tax_year") or "", "chars": _d["n_chars"], "units": _d["n_units"],
                "issue": "yes" if _d["flags"] else "", "title": _d["title"][:90],
            }
            for _d in shown
        ],
        selection="single", page_size=12, label=f"{len(shown)} of {len(docs)} documents. Select one to view it below.",
    )
    table
    return (table,)


@app.cell
def _(mo):
    mo.md("""
    ### Selected document
    """)
    return


@app.cell
def _(by_id, html, mo, normalize, original_text, pdf_path, pre_clean_text, re, scroll, table, visible):
    mo.stop(not table.value, mo.md("*Select a document in the table above.*"))
    d = by_id[table.value[0]["id"]]
    cleaned = d["text"]
    _pdf = pdf_path(d)
    _orig = original_text(d)

    _head = mo.md(
        f"**{d['title']}**  \n"
        f"`{d['doc_id']}` · {d['source']} · **{d['kind']}** · role {d['role']} · text via **{d['text_method']}** · "
        f"{d['n_chars']:,} chars · {d['n_units']} units · year {d.get('year') or d.get('tax_year') or '?'} · [open online]({d['url']})"
    )
    _notes = []
    if d["text_method"] == "ocr":
        _notes.append(mo.callout(mo.md("**OCR text.** Not verified against a source by any script. Check amounts, dates and `ข้อ` numbers against the PDF."), kind="warn"))
    for _f in d["flags"]:
        _notes.append(mo.callout(mo.md(f"**Known issue:** {_f}"), kind="danger"))
    if d["preamble"]:
        _notes.append(mo.accordion({"Preamble (before the first unit)": scroll(d["preamble"], "auto")}))

    # --- side by side
    if _pdf is not None:
        _left = mo.vstack([mo.md("**Original PDF**"), mo.pdf(src=_pdf, height="72vh")])
    elif _orig is not None:
        _left = mo.vstack([mo.md("**Original (visible text of the raw source)**"), scroll(_orig)])
    else:
        _left = mo.md("**Original not available** (`data/raw` not downloaded for this document).")
    side = mo.hstack([_left, mo.vstack([mo.md("**Cleaned text**"), scroll(cleaned)])], widths="equal", gap=1, align="start")

    # --- what normalize changed
    _raw = pre_clean_text(d)
    _changes = []
    for _ln in _raw.split("\n"):
        _c = normalize(_ln)
        if _ln.strip() and " ".join(_ln.split()) != _c:  # ignore whitespace-only differences
            _changes.append((visible(_ln.strip()), _c))
    _rows = "".join(
        f'<div style="margin:6px 0;font-size:13px"><div style="background:#fde8e8;padding:2px 6px;white-space:pre-wrap">− {html.escape(a)}</div>'
        f'<div style="background:#e6f4ea;padding:2px 6px;white-space:pre-wrap">+ {html.escape(b)}</div></div>'
        for a, b in _changes[:200]
    )
    diff = mo.vstack([
        mo.md(f"**{len(_changes)} line(s) changed** by `normalize` beyond whitespace trimming"
              + (" (first 200 shown)" if len(_changes) > 200 else "")
              + ". `⍽` = no-break space, `⟨xNN⟩` = control character, `⟨zw⟩` = zero-width space."),
        mo.Html(f'<div style="max-height:72vh;overflow:auto">{_rows or "<i>nothing but whitespace changed</i>"}</div>'),
    ])

    # --- numbers and section labels (for checking against the original)
    _ctx = {}
    for _m in re.finditer(r"\d[\d,.]*\d|\d", cleaned):
        _ctx.setdefault(_m.group().rstrip(".,"), []).append(cleaned[max(0, _m.start() - 28) : _m.end() + 28].replace("\n", " "))
    _nums = [{"number": k, "count": len(v), "first context": v[0]} for k, v in sorted(_ctx.items(), key=lambda kv: -len(kv[1]))]
    _labels = [int(x) for x in re.findall(r"(?:^|\s)ข้อ\s*(\d+)(?!\s*(?:แห่ง|ของ|วรรค))(?=\s)", cleaned)]
    _marks = " ".join(map(str, _labels)) or "none found"
    _jumps = [(a, b) for a, b in zip(_labels, _labels[1:]) if b != a + 1]
    numbers = mo.vstack([
        mo.md(f"**`ข้อ` numbers in order:** {_marks}  \n" + (f"**Breaks in sequence:** {_jumps}" if _jumps else "No breaks in sequence." if _labels else "")),
        mo.md(f"**{len(_nums)} distinct numbers.** Tick them off against the original; amounts, rates, dates and years matter most."),
        mo.ui.table(_nums, selection=None, page_size=15),
    ])

    tabs = mo.ui.tabs({"Side by side": side, "Cleaned only": scroll(cleaned, "75vh"), "What cleaning changed": diff, "Numbers": numbers})
    mo.vstack([_head, *_notes, tabs])
    return (d,)


@app.cell
def _(mo):
    mo.md("""
    ## 2. Units (FAQ items and statute sections)

    Browse every unit, or only the selected document's. `section_guessed`, `title_inherited`, `marker_q_lost` and `has_repeal_note` are the cases worth reading.
    """)
    return


@app.cell
def _(mo, units):
    u_type = mo.ui.multiselect(sorted({_u["type"] for _u in units}), value=sorted({_u["type"] for _u in units}), label="Type")
    u_flag = mo.ui.multiselect(sorted({_f for _u in units for _f in _u["flags"]}), label="Has flag (empty = any)")
    u_doc = mo.ui.checkbox(value=True, label="Only the selected document (if it has units)")
    u_q = mo.ui.text(placeholder="text contains…", label="Search")
    mo.hstack([u_type, u_flag, u_doc, u_q], justify="start", gap=2, align="end", wrap=True)
    return u_doc, u_flag, u_q, u_type


@app.cell
def _(mo, table, u_doc, u_flag, u_q, u_type, units, units_of):
    _sel = table.value[0]["id"] if table.value else None
    _only = _sel if (u_doc.value and _sel in units_of) else None
    _q = u_q.value.strip()
    shown_units = [
        _u for _u in units
        if _u["type"] in u_type.value
        and (_only is None or _u["doc_id"] == _only)
        and (not u_flag.value or set(u_flag.value) & set(_u["flags"]))
        and (not _q or _q in _u["text"])
    ]
    unit_table = mo.ui.table(
        [
            {"unit": _u["unit_id"], "label": _u["label"], "section": (_u["section"] or "")[:40], "title": (_u["title"] or "")[:40],
             "chars": len(_u["text"]), "flags": ", ".join(_u["flags"]), "notes": len(_u["notes"]), "start": _u["text"][:70].replace("\n", " ")}
            for _u in shown_units
        ],
        selection="single", page_size=10,
        label=f"{len(shown_units)} units" + (f" in document {_only}" if _only else " across the corpus") + ". Select one to read it.",
    )
    unit_table
    return (unit_table,)


@app.cell
def _(mo, scroll, unit_table, units, units_of):
    mo.stop(not unit_table.value, mo.md("*Select a unit above.*"))
    _u = next(x for x in units if x["unit_id"] == unit_table.value[0]["unit"])
    _sibs = units_of[_u["doc_id"]]
    _i = _sibs.index(_u)
    _nb = f"previous: **{_sibs[_i - 1]['label']}**" if _i else "first unit"
    _nb += f" · next: **{_sibs[_i + 1]['label']}**" if _i + 1 < len(_sibs) else " · last unit"
    _meta = (
        f"**{_u['label']}** · `{_u['unit_id']}` · {_u['type']} · {len(_u['text']):,} chars · {_nb}"
        + (f"  \nsection: {_u['section']}" if _u["section"] else "")
        + (f"  \ntitle: {_u['title']}" if _u["title"] else "")
        + (f"  \nflags: `{'`, `'.join(_u['flags'])}`" if _u["flags"] else "")
    )
    _parts = [mo.md(_meta), scroll(_u["text"], "50vh")]
    if _u["notes"]:
        _parts.append(mo.md(f"**{len(_u['notes'])} note(s)** (kept in the text, listed here as metadata)"))
        _parts.append(mo.ui.table([{"type": n["type"], "text": n["text"]} for n in _u["notes"]], selection=None, page_size=10))
    mo.vstack(_parts)
    return


if __name__ == "__main__":
    app.run()
