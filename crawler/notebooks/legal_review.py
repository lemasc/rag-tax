import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import csv
    import hashlib
    import re
    import subprocess
    from collections import Counter
    from pathlib import Path

    import marimo as mo

    return Counter, Path, csv, hashlib, mo, re, subprocess


@app.cell
def _(Path, csv, hashlib, mo):
    RAW = Path("data/raw/legal")
    catalog = list(csv.DictReader(open("data/legal_catalog.csv", encoding="utf-8")))
    scan = {r["url"]: r for r in csv.DictReader(open("data/legal_scan.csv", encoding="utf-8"))}
    core = {r["url"]: r for r in csv.DictReader(open("data/legal_core.csv", encoding="utf-8"))}
    extracted = {r["url"]: r for r in csv.DictReader(open("data/legal_text.csv", encoding="utf-8"))}

    def group(r):
        """Proposed action, from tier + reason + full-text scan (see docs/plans/legal-source-crawl.md)."""
        if r["tier"] == "C":
            return "skip (tier C)"
        s = scan.get(r["url"])
        if s is None:
            return "not downloaded"
        if int(s["chars"]) < 150:
            return "needs OCR"
        if r["cited"] == "1":
            return "keep (cited by Code)"
        if r["tier"] == "A":
            return "keep (A)"
        pit, corp = int(s["pit"]), int(s["corp"])
        if pit == 0:
            # title-signal B with no PIT words in the body is noise; hub/kind-floor B is income tax by definition: look at it
            return "drop (B, no PIT text)" if r["reason"].startswith("title") else "review (B, floor rule, no PIT text)"
        return "review (B, corp-heavy)" if corp > 2 * pit else "keep (B)"

    for r in catalog:
        r["group"] = group(r)
        s = scan.get(r["url"], {})
        r["pit"] = int(s["pit"]) if s else None
        r["corp"] = int(s["corp"]) if s else None
        r["chars"] = int(s["chars"]) if s else None
        r["file"] = s.get("file")
        r["ext"] = r["url"].rsplit(".", 1)[-1]
        c = core.get(r["url"], {})
        r["core"], r["text"], r["year"] = c.get("decision", ""), c.get("text", ""), c.get("year", "")
    mo.md(f"# Legal-source review\n**{len(catalog)} documents** in `data/legal_catalog.csv`; {len(scan)} A/B documents full-text scanned; "
          f"**{len(core)}** in the core set `data/legal_core.csv`.")
    return RAW, catalog, core, extracted, scan


@app.cell
def _(Counter, core, mo):
    _keep = [r for r in core.values() if r["decision"] == "keep"]
    _text = Counter(r["text"] for r in _keep)
    _kind = Counter(r["kind"].split(":")[0] for r in _keep)
    mo.md(f"""
    ## 0. Core set (what goes into the corpus)

    **Scope rule:** only documents the Code itself cites from ม.38–64 (`cited = 1`, built by `uv run python -m crawler.legal_core`).
    Everything else in the catalogue is out of scope unless an evaluation question needs it. Sections 1 and 4 below are kept as the record of how the 2,200 candidates were narrowed.

    - **{len(core)}** cited → **{len(_keep)} keep**, {len(core) - len(_keep)} drop
    - text: {_text["ok"]} ok · {_text["garbled"]} garbled (broken PDF font encoding → needs OCR) · {_text["missing"]} not downloaded
    - by kind: {", ".join(f"{k} {n}" for k, n in _kind.most_common())}

    **Decisions and caveats**

    - *Dropped:* the ม.47(7)(ข) charity list (`2644.html`, 122K chars of organisation names) — would flood retrieval and answers nothing.
    - *Not duplicates:* `dg457A`/`dg459A` and `dg438A`/`3186.html` share a listing title but are base notice + amendment.
    - *Mislabelled:* `2502.html` is listed as กฎกระทรวง ฉบับที่ 380 but holds the consolidated ฉบับที่ 126 (2509) with amendments — the main ม.42(17) exemption list.
    - *Amendment chains* (e.g. ป.อ. 101→396 loan interest, 193→242 disabled dependants, 146/186/240 WHT certificate, 243/292/326/328 filing) are kept whole with their `year`; retrieving a superseded link is a known failure mode, not resolved by hand.
    - *Garbled text* passed the old 150-char OCR check; `text` is now set by a common-word density check (garbled = 0 per 1k chars, real text ≥ 8).
    """)
    return


@app.cell
def _(Counter, catalog, mo):
    _kinds = sorted({r["kind"].split(":")[0] for r in catalog})
    _groups = ["keep (cited by Code)", "keep (A)", "keep (B)", "review (B, corp-heavy)", "review (B, floor rule, no PIT text)", "drop (B, no PIT text)", "needs OCR", "skip (tier C)"]
    _cnt = Counter((r["kind"].split(":")[0], r["group"]) for r in catalog)
    _table = "| kind | " + " | ".join(_groups) + " | total |\n|---|" + "---|" * (len(_groups) + 1) + "\n"
    for _k in _kinds:
        _row = [_cnt[(_k, g)] for g in _groups]
        _table += f"| {_k} | " + " | ".join(str(x) for x in _row) + f" | {sum(_row)} |\n"
    _tot = [sum(_cnt[(k, g)] for k in _kinds) for g in _groups]
    _table += "| **all** | " + " | ".join(f"**{x}**" for x in _tot) + f" | **{sum(_tot)}** |\n"
    mo.md(f"""
    ## 1. How candidates were narrowed: what the tier filter proposed

    {_table}

    - **tier A** = title has an explicit personal-income-tax signal, or the Code (ม.38–64) cites it; **B** = generic income-tax signal, income-tax hub (ประกาศอธิบดี เกี่ยวกับภาษีเงินได้), คำวินิจฉัย, or body text with PIT terms; **C** = other. `reason` says which rule fired; `tier_v1` is the first title-only tiering.
    - **needs OCR** = PDF has <150 extractable chars (image-only).
    - Rule: keep all A; keep B only if the body mentions PIT terms and not mostly corporate/VAT/stamp terms.
    - *Known weakness*: a title-only filter misses things like donation decrees (zero PIT words in body) — that is why A is kept regardless of the body scan.
    """)
    return


@app.cell
def _(mo):
    mo.md("""
    ## 2. Browse and filter the catalogue

    Opens on the core set; untick it to browse the whole catalogue.
    """)
    return


@app.cell
def _(catalog, mo):
    f_core = mo.ui.checkbox(value=True, label="Core set only")
    f_kind = mo.ui.multiselect(sorted({r["kind"] for r in catalog}), label="Kind")
    f_group = mo.ui.multiselect(sorted({r["group"] for r in catalog}), label="Proposed")
    f_text = mo.ui.text(label="Title contains", placeholder="e.g. ลดหย่อน, บริจาค, มาตรา 47")
    mo.hstack([f_core, f_kind, f_group, f_text], justify="start", gap=2, wrap=True)
    return f_core, f_group, f_kind, f_text


@app.cell
def _(catalog, f_core, f_group, f_kind, f_text, mo):
    shown = [
        r for r in catalog
        if (not f_core.value or r["core"])
        and (not f_kind.value or r["kind"] in f_kind.value)
        and (not f_group.value or r["group"] in f_group.value)
        and (not f_text.value or f_text.value in r["title"])
    ]
    table = mo.ui.table(
        [
            {"core": r["core"], "text": r["text"], "year": r["year"], "kind": r["kind"], "tier": r["tier"], "was": r["tier_v1"], "reason": r["reason"], "group": r["group"], "pit": r["pit"], "corp": r["corp"],
             "chars": r["chars"], "title": r["title"][:140], "url": r["url"]}
            for r in shown
        ],
        page_size=25, selection="single",
    )
    mo.vstack([mo.md(f"**{len(shown)}** documents match. Select a row to read it below."), table])
    return (table,)


@app.cell
def _(mo):
    mo.md("""
    ## 3. Document viewer
    """)
    return


@app.cell
def _(Path, RAW, catalog, extracted, hashlib, mo, re, subprocess, table):
    _TH = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")

    def extract(url: str) -> str:
        _f = RAW / (hashlib.sha1(url.encode()).hexdigest()[:12] + "." + url.rsplit(".", 1)[-1])
        if not _f.exists():
            return ""
        if _f.suffix == ".pdf":
            _t = subprocess.run(["pdftotext", "-layout", str(_f), "-"], capture_output=True, text=True).stdout
        else:
            _t = re.sub(r"<[^>]+>", " ", _f.read_text(errors="ignore"))
        _t = _t.translate(_TH)
        # PDFs with justified text come out letter-spaced ("ก ร ม ส ร ร พ า ก ร"): rejoin Thai letters.
        return re.sub(r"(?<=[฀-๿]) (?=[฀-๿])", "", _t)

    if not table.value:
        mo.output.replace(mo.md("*Select a row in the table above.*"))
    else:
        _url = table.value[0]["url"]
        _r = next(r for r in catalog if r["url"] == _url)
        _x = extracted.get(_url, {})
        _cached = _x.get("status") == "ok"
        _text = Path("data/text/legal", _x["file"]).read_text(encoding="utf-8") if _cached else extract(_url)
        _pdf = f"[open original]({_url})" + (f" · text from `data/text/legal/{_x['file']}` ({_x['method']})" if _cached else "")
        _body = (
            mo.ui.text_area(_text, rows=28, full_width=True, disabled=True)
            if _cached
            else mo.md("**No extractable text — image-only PDF. Needs OCR.** " + _pdf)
            if len(_text) < 150
            else mo.md("**Garbled text layer (broken font encoding). Needs OCR.** " + _pdf)
            if _r["text"] == "garbled"
            else mo.ui.text_area(_text, rows=28, full_width=True, disabled=True)
        )
        mo.output.replace(mo.vstack([
            mo.md(f"### {_r['title']}\n" + (f"core **{_r['core']}** · {_r['year'] or 'no year'} · " if _r["core"] else "") + f"`{_r['kind']}` · tier **{_r['tier']}** · proposed **{_r['group']}** · "
                  f"PIT hits {_r['pit']} / corp hits {_r['corp']} · {_r['chars']} chars · {_pdf}"),
            _body,
        ]))
    return


@app.cell
def _(mo):
    mo.md("""
    ## 4. Sampling the borderline groups (narrowing record)

    Spot-check of the tier filter, kept as evidence for the narrowing step; not needed for the core set. Each table shows 25 random-ish rows (every n-th) from the group.
    """)
    return


@app.cell
def _(catalog, mo):
    def sample(group, n=25):
        _rows = [r for r in catalog if r["group"] == group]
        _step = max(1, len(_rows) // n)
        return mo.ui.table(
            [{"kind": r["kind"], "pit": r["pit"], "corp": r["corp"], "title": r["title"][:150], "url": r["url"]} for r in _rows[::_step][:n]],
            selection=None, page_size=25,
        )

    mo.ui.tabs({
        "drop (B, no PIT text) — did we lose anything?": sample("drop (B, no PIT text)"),
        "review (B, floor rule)": sample("review (B, floor rule, no PIT text)"),
        "review (B, corp-heavy)": sample("review (B, corp-heavy)"),
        "needs OCR": sample("needs OCR"),
        "skip (tier C) — false negatives?": sample("skip (tier C)"),
    })
    return


@app.cell
def _(mo):
    mo.md("""
    ## 5. Other places to collect from — deferred

    Not planned. Revisit only if an evaluation question has no source in the corpus.

    | Source | Page / how | Why |
    |---|---|---|
    | พ.ร.บ. แก้ไขประมวลรัษฎากร (ฉบับที่ 1–54) | rd.go.th/62258.html | Amendment Acts — where the Code text changed |
    | พ.ร.ก. แก้ไขประมวลรัษฎากร (ฉบับที่ 1–19) | rd.go.th/62417.html | incl. ฉบับที่ 19/2561 (digital assets) |
    | พ.ร.ก. แลกเปลี่ยนข้อมูล (CRS) 2566, ภาษีการรับมรดก 2558, ยกเว้นเบี้ยปรับ 2562, กยศ. 2560 | rd.go.th/63929, 61303, 61381, 62015 | Acts hosted by RD |
    | คำพิพากษาฎีกา 2520–2560 | rd.go.th/62653 (per-year indexes) | Court interpretation |
    | ประมวลรัษฎากร ม.1–37 | rd.go.th/2600, 2591, 2599, 2598, 21456 | Filing, assessment, penalties, appeals — missing |
    | ข้อหารือ 2540–2569 | rd.go.th/68689 (+ per-year) | Filter by ม.40–64 / บุคคลธรรมดา |
    | พ.ร.บ. กองทุนสำรองเลี้ยงชีพ 2530 | sec.or.th | PVD deduction |
    | พ.ร.บ. ประกันสังคม 2533, กบข. 2539, กอช. 2554, คนพิการ 2550, คุ้มครองแรงงาน 2541, พรรคการเมือง 2560 | krisdika.go.th (unreachable by curl — needs browser) | Statutes the Code's deductions/exemptions refer to |

    See `docs/plans/legal-source-crawl.md` for the full plan.
    """)
    return


if __name__ == "__main__":
    app.run()
