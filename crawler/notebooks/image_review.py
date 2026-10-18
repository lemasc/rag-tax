import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import os
    from datetime import datetime
    from pathlib import Path

    import marimo as mo

    ROOT = Path(__file__).resolve().parents[1]
    os.chdir(ROOT)  # crawler.* resolves data/ relative to the working directory

    from crawler import images
    from crawler.extract import ocr, ocr_up

    return datetime, images, mo, ocr, ocr_up


@app.cell
def _(mo):
    mo.md(r"""
    # Image review

    Images inside the `col-main` block of HTML pages, from `python -m crawler.images`. An image becomes a document only
    when its decision here is **keep**; the OCR text is then exported to `data/text/image/` and `clean.build` picks it up.

    Overlap is the share of the OCR text's 6-character shingles already present in the clean corpus: **page** in the image's
    own page, **elsewhere** in any other document. A high *elsewhere* means a copy of something we already have; a low
    number means new content or an OCR misreading, so compare the image with the text before deciding.
    """)
    return


@app.cell
def _(images, mo):
    index = images.load_index()
    corpus = images.corpus_shingles()
    get_decisions, set_decisions = mo.state(images.load_decisions())
    return corpus, get_decisions, index, set_decisions


@app.cell
def _(corpus, get_decisions, images, index, mo):
    _rows = []
    for _r in index:
        _text = images.ocr_text(_r["image_id"])
        _page = _else = None
        if _text:
            _page = round(images.overlap(_text, {_r["page_id"]: corpus.get(_r["page_id"], set())}, _r["page_id"])["page"], 2)
            _else = round(images.overlap(_text, {k: v for k, v in corpus.items() if k != _r["page_id"]})["corpus"], 2)
        _rows.append({
            "image_id": _r["image_id"], "page": _r["page_id"], "size": f"{_r['width'] or '?'}x{_r['height'] or '?'}",
            "downloaded": bool(_r["bytes"]), "ocr chars": len(_text) if _text else None, "in page": _page, "elsewhere": _else,
            "decision": get_decisions().get(_r["image_id"], {}).get("decision", ""),
            "source": get_decisions().get(_r["image_id"], {}).get("source", ""),
            "verified": get_decisions().get(_r["image_id"], {}).get("verified", ""),
        })
    table = mo.ui.table(_rows, selection="single", page_size=25, label=f"{len(_rows)} images")
    undecided = sum(1 for _r in _rows if not _r["decision"])
    unverified = sum(1 for _r in _rows if _r["decision"] == "keep" and not _r["verified"])
    mo.vstack([mo.md(f"**{undecided}** undecided of {len(_rows)}; **{unverified}** kept but not verified against the image. Select one to review it."), table])
    return (table,)


@app.cell
def _(corpus, images, index, mo, table):
    mo.stop(not table.value, mo.md("*Select an image above.*"))
    image_id = table.value[0]["image_id"]
    row = next(_r for _r in index if _r["image_id"] == image_id)
    path = images.IMG / row["file"]
    text = images.ocr_text(image_id)
    _left = mo.image(path.read_bytes(), width=420) if path.exists() else mo.md("*not downloaded*")
    if text:
        _ov = images.overlap(text, corpus, row["page_id"])
        _lines = images.unmatched_lines(text, corpus)
        _right = mo.vstack([
            mo.md(f"**{image_id}** on page [{row['page_id']}](https://www.rd.go.th/{row['page_id']}.html), alt: `{row['alt'] or '-'}`"),
            mo.md(f"overlap with the corpus: **{_ov['corpus']:.0%}** · own page {_ov['page']:.0%} · best matches {_ov['best']}"),
            mo.accordion({f"Lines mostly absent from the corpus ({len(_lines)})": mo.md("\n".join(f"- {_l}" for _l in _lines) or "*none*")}),
            mo.ui.text_area(text, rows=26, full_width=True, disabled=True, label="OCR text (read-only)"),
        ])
    else:
        _right = mo.md(f"**{image_id}**: no OCR yet.")
    mo.hstack([_left, _right], widths=[1, 2], align="start", gap=2)
    return image_id, row, text


@app.cell
def _(mo, ocr_up, text):
    ocr_btn = mo.ui.run_button(label="OCR this image (needs the vLLM server)", disabled=bool(text) or not ocr_up())
    ocr_btn
    return (ocr_btn,)


@app.cell
def _(image_id, images, mo, ocr, ocr_btn, row):
    mo.stop(not ocr_btn.value)
    _ok = ocr(images.IMG / row["file"]) is not None
    mo.md(f"OCR of `{image_id}` {'done: reselect the row to see it' if _ok else 'FAILED'}")
    return


@app.cell
def _(image_id, images, mo, text):
    # Starts from the corrected file when the image is already `manual`, otherwise from the OCR text. It reads the
    # decisions file rather than the state so that saving does not rebuild the editor and wipe its confirmation.
    _path = images.TEXT / f"{image_id}.md"
    _manual = images.load_decisions().get(image_id, {}).get("source") == "manual" and _path.exists()
    editor = mo.ui.text_area(_path.read_text(encoding="utf-8") if _manual else (text or ""), rows=28, full_width=True,
                             label="Text for the corpus" + (" (hand-corrected file)" if _manual else " (starts from the OCR text)"))
    edit_btn = mo.ui.run_button(label="Save edited text (source = manual, verified cleared)")
    mo.vstack([
        mo.md("### Edit the text\nSaving writes `data/text/image/<id>.md`, marks the image `manual` and clears `verified`: "
              "changed text has to be compared with the image again. Then set the decision below."),
        editor, edit_btn,
    ])
    return edit_btn, editor


@app.cell
def _(datetime, edit_btn, editor, image_id, images, mo, set_decisions):
    mo.stop(not edit_btn.value)
    mo.stop(not editor.value.strip(), mo.md("*Empty text is not saved.*"))
    images.TEXT.mkdir(parents=True, exist_ok=True)
    (images.TEXT / f"{image_id}.md").write_text(editor.value.strip() + "\n", encoding="utf-8")
    _old = images.load_decisions().get(image_id, {})
    _edited = {
        "title": "", "note": "", **_old, "image_id": image_id, "decision": _old.get("decision") or "keep",
        "source": "manual", "verified": "", "decided_at": datetime.now().date().isoformat(),
    }

    def _merge_edit(current):
        merged = {**current, image_id: _edited}
        images.save_decisions(merged)
        return merged

    set_decisions(_merge_edit)
    mo.md(f"Saved the text of `{image_id}` ({len(editor.value.strip())} characters), decision **{_edited['decision']}**, source **manual**, not verified. "
          "Re-run `python -m crawler.clean.build` to rebuild the corpus.")
    return


@app.cell
def _(get_decisions, image_id, mo):
    _cur = get_decisions().get(image_id, {})
    choice = mo.ui.radio(["keep", "drop"], value=_cur.get("decision") or None, inline=True, label="Decision")
    title = mo.ui.text(value=_cur.get("title", ""), placeholder="keep only; default: first heading of the text", label="Title", full_width=True)
    note = mo.ui.text(value=_cur.get("note", ""), placeholder="why, in a few words", label="Note", full_width=True)
    source = mo.ui.radio(["ocr", "manual"], value=_cur.get("source") or "ocr", inline=True, label="Text source")
    verified = mo.ui.checkbox(value=bool(_cur.get("verified")), label="A person compared this text with the image")
    mo.vstack([
        mo.md(f"Current: **{_cur['decision']}**, source {_cur['source']}, verified {_cur['verified'] or 'no'} ({_cur['decided_at']})" if _cur else "Current: *undecided*"),
        choice, title, note,
        mo.hstack([source, verified], justify="start", gap=2),
        mo.md("`manual`: the text is `data/text/image/<id>.md`, edited by hand; saving never overwrites it. Keeping the existing `verified` date needs the box ticked."),
    ])
    return choice, note, source, title, verified


@app.cell
def _(choice, image_id, images, mo, source, text):
    _has_text = bool(text) or (source.value == "manual" and (images.TEXT / f"{image_id}.md").exists())
    _blocked = not choice.value or (choice.value == "keep" and not _has_text)
    save_btn = mo.ui.run_button(
        label=f"Save '{choice.value}'" if choice.value else "Pick a decision to save",
        disabled=_blocked,
    )
    mo.hstack([save_btn, mo.md("*keep needs OCR text (or a manual text file) first*" if choice.value == "keep" and not _has_text else "")], justify="start", align="center")
    return (save_btn,)


@app.cell
def _(
    choice,
    datetime,
    image_id,
    images,
    mo,
    note,
    save_btn,
    set_decisions,
    source,
    title,
    verified,
):
    mo.stop(not save_btn.value)
    _old = images.load_decisions().get(image_id, {}).get("verified", "")
    _row = {
        "image_id": image_id, "decision": choice.value, "title": title.value.strip() if choice.value == "keep" else "",
        "note": note.value.strip(), "decided_at": datetime.now().date().isoformat(), "source": source.value,
        "verified": (_old or datetime.now().date().isoformat()) if verified.value else "",
    }

    def _merge(current):
        merged = {**current, image_id: _row}
        images.save_decisions(merged)
        return merged

    set_decisions(_merge)
    _exported = images.export_kept()
    mo.md(f"Saved **{_row['decision']}** for `{image_id}` to `{images.DECISIONS.name}`. "
          f"Exported text for: {', '.join(_exported) or 'none'}. Re-run `python -m crawler.clean.build` to rebuild the corpus.")
    return


if __name__ == "__main__":
    app.run()
