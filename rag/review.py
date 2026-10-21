import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium", app_title="RAG answer review")


@app.cell
def _():
    """Review answers of a run: chunk relevance, rubric scores, failure tags. Labels go to rag/eval/labels/<name>/
    (one directory per reviewer); the rubric is docs/plans/review-rubric.md.

    Run: uv run marimo run rag/review.py --token-password <password>   (to share: ngrok http 2718)
    """
    import html
    import json
    import sys
    from pathlib import Path

    import marimo as mo

    ROOT = Path(__file__).parent.parent
    sys.path.insert(0, str(ROOT))  # `marimo run` does not put the repo root on the path
    from rag import labels
    from rag.answer import KIND_TH, year_label
    from rag.questions import BEHAVIOURAL, load

    return BEHAVIOURAL, KIND_TH, ROOT, html, json, labels, load, mo, year_label


@app.cell
def _(ROOT, labels, mo):
    known = labels.reviewers()
    pick_name = mo.ui.dropdown(known, label="ผู้ตรวจ (Reviewer)", value=known[0] if len(known) == 1 else None)
    new_name = mo.ui.text(label="หรือชื่อใหม่", placeholder="a-z 0-9 - _")
    pick_run = mo.ui.dropdown(labels.runs(), value=(labels.runs() or [None])[0], label="Run")
    _rubric = (ROOT / "docs" / "plans" / "review-rubric.th.md").read_text(encoding="utf-8").split("\n", 1)[1]  # line 1 is for maintainers
    _changes = mo.callout(mo.md(f"""**เกณฑ์การตรวจปรับเป็น {labels.RUBRIC_VERSION} (21 ต.ค. 2569)** กรุณาอ่านเกณฑ์ด้านล่างก่อนตรวจต่อ สิ่งที่เปลี่ยนจากที่ทำกันมา:

- **behaviour** ให้เฉพาะคำถามที่ "ควรถามกลับ" "ควรแก้ความเข้าใจผิด" หรือ "นอกขอบเขต" เท่านั้น ข้ออื่นไม่มีช่องนี้แล้ว (เดิมหลายคนใช้เป็นคะแนนว่าตอบดี)
- **คำตอบที่ปฏิเสธหรือบอกว่าเอกสารไม่ครอบคลุม**: correct ดูจากสิ่งที่พูดจริง ส่วนที่ไม่ได้ตอบให้หักที่ useful
- **แท็ก**: เพิ่ม `ignored_source` (ดึงเอกสารมาได้แต่ไม่ใช้) · `retrieval_miss` ใช้เมื่อไม่มีเอกสารไหนตอบได้เท่านั้น · `outdated` ใช้เมื่อคำตอบใช้ข้อมูลเก่าเท่านั้น
- **ข้อในชุดร่วม (★) ที่ตรวจด้วยเกณฑ์เดิมจะกลับมาอยู่ในคิว** ขอให้ตรวจใหม่ ค่าเดิมเติมไว้ให้แล้ว แก้เฉพาะที่ไม่ตรงเกณฑ์ใหม่"""), kind="warn")
    mo.vstack([
        mo.md("## ตรวจคำตอบ (Answer review)"), _changes,
        mo.accordion({"📋 เกณฑ์การตรวจ (อ่านก่อนเริ่ม)": mo.md(_rubric)}),
        mo.hstack([pick_name, new_name], justify="start"), pick_run,
    ])
    return new_name, pick_name, pick_run


@app.cell
def _(labels, mo, new_name, pick_name, pick_run):
    _raw = new_name.value.strip() or pick_name.value or ""
    reviewer, name_error = None, None
    if _raw:
        try:
            reviewer = labels.check_name(_raw)
        except ValueError as e:
            name_error = str(e)
    mo.stop(not reviewer or not pick_run.value, mo.callout(name_error or "เลือกหรือพิมพ์ชื่อผู้ตรวจ และเลือก run", kind="warn" if name_error else "info"))
    run_id = pick_run.value
    return reviewer, run_id


@app.cell
def _(ROOT, json, labels, load, mo, run_id):
    _dir = labels.RUNS / run_id
    records = {r["id"]: r for r in map(json.loads, (_dir / "answers.jsonl").open(encoding="utf-8"))}
    config = json.loads((_dir / "config.json").read_text(encoding="utf-8"))
    chunks = {c["chunk_id"]: c for c in map(json.loads, (ROOT / "rag" / "out" / "chunks.jsonl").open(encoding="utf-8"))}
    questions = {q.id: q for q in load()}
    shared = labels.shared_ids()
    _missing = sorted({h["chunk_id"] for r in records.values() for h in r["hits"]} - set(chunks))
    _warn = mo.callout(f"chunks.jsonl changed since this run: {len(_missing)} retrieved chunks are missing and show without text", kind="warn") if _missing else None
    _warn
    return chunks, config, questions, records, shared


@app.cell
def _(mo):
    get_saved, set_saved = mo.state(0)  # bumped after each save, so the queue and progress recompute
    return get_saved, set_saved


@app.cell
def _(get_saved, labels, mo, records, reviewer, run_id, shared):
    get_saved()
    todo, items = labels.queue(reviewer, run_id, list(records), shared)
    _mine = sum(reviewer in i.done_by for i in items)
    _shared_done = len(shared) - sum(i.shared for i in todo)  # under the current rubric
    _any = sum(bool(i.done_by) for i in items)
    mo.md(
        f"**{reviewer}**: ตรวจแล้ว {_mine} ข้อ · ชุดร่วม {_shared_done}/{len(shared)} · "
        f"ทั้ง run มีคนตรวจแล้ว {_any}/{len(items)} ข้อ · คิวของคุณเหลือ {len(todo)} ข้อ"
    )
    return items, todo


@app.cell
def _(mo):
    show_all = mo.ui.switch(label="แสดงทุกข้อใน run (รวมที่ตรวจแล้ว)")
    return (show_all,)


@app.cell
def _(items, mo, questions, reviewer, show_all, todo):
    def _label(i):
        q = questions[i.question_id]
        redo = i.shared and reviewer in i.done_by and i in todo  # labelled under an older rubric
        tag = ("★ ชุดร่วม · " if i.shared else "") + ("ตรวจใหม่ตามเกณฑ์ใหม่ · " if redo else "")
        turn = f" [ชุด {q.set} รอบ {q.turn}]" if q.set else ""
        by = f" · ตรวจโดย {', '.join(i.done_by)}" if i.done_by else ""
        return f"{tag}{q.id}{turn} {q.text[:60]}{by}"

    _pool = items if show_all.value else todo
    _options = {_label(i): i.question_id for i in _pool}
    pick_q = mo.ui.dropdown(_options, value=next(iter(_options), None), label="คำถาม", full_width=True)
    mo.vstack([show_all, pick_q] if _options else [show_all, mo.callout("คิวของคุณว่างแล้ว ขอบคุณครับ/ค่ะ", kind="success")])
    return (pick_q,)


@app.cell
def _(BEHAVIOURAL, KIND_TH, chunks, html, labels, mo, pick_q, questions, records, reviewer, run_id, year_label):
    mo.stop(not pick_q.value)
    qid = pick_q.value
    rec, q = records[qid], questions[qid]
    _prev_a = labels.answer_labels(reviewer).get((run_id, qid), {})
    _prev_c = labels.chunk_labels(reviewer)

    def _esc(s):  # chunk text goes into a batch template: escape HTML and the template's braces
        return html.escape(s).replace("{", "{{").replace("}", "}}").replace("\n", "<br>")

    # labels.py maps stored value -> shown label; marimo options map shown label -> returned value
    def _radio(choices, saved):
        return mo.ui.radio({lab: val for val, lab in choices.items()}, inline=True, value=choices.get(saved))

    _blocks, _elements = [], {}
    for _n, _h in enumerate(rec["hits"], 1):
        _c = chunks.get(_h["chunk_id"], {})
        _cited = "✓ อ้างอิงในคำตอบ" if _h["chunk_id"] in rec["cited"] else ""
        _meta = f"{KIND_TH.get(_c.get('kind'), _c.get('kind', '?'))} · {year_label(_c) if _c else '?'} · {_h['chunk_id']} {_cited}"
        _elements[f"c{_n}"] = _radio(labels.RELEVANCE, _prev_c.get((qid, _h["chunk_id"]), {}).get("relevance"))
        _blocks.append(
            f"<details {'open' if _n <= 2 else ''}><summary><b>[{_n}] {_esc(_c.get('header', '(chunk missing)'))}</b>"
            f"<br><small>{_esc(_meta)}</small></summary><div style='font-size:0.9em;margin:0.5em 0'>{_esc(_c.get('text', ''))}</div>"
            f"<small><a href='{html.escape(_c.get('url', ''))}' target='_blank'>{html.escape(_c.get('url', ''))}</a></small></details>"
            f"<div>ความเกี่ยวข้องกับคำถาม: {{c{_n}}}</div><hr>"
        )
    for _f, _desc in labels.RUBRIC.items():
        _elements[_f] = _radio(labels.SCORES, _prev_a.get(_f))
    if q.kind in BEHAVIOURAL:  # elsewhere behaviour is saved as "na" without asking
        _elements["behaviour"] = _radio(labels.BEHAVIOUR, _prev_a.get("behaviour"))
    _tag_opts = {f"{t}: {d}": t for t, d in labels.TAGS.items()}
    _elements["tags"] = mo.ui.multiselect(_tag_opts, value=[k for k, t in _tag_opts.items() if t in _prev_a.get("tags", "").split(";")])
    _elements["note"] = mo.ui.text_area(value=_prev_a.get("note", ""), full_width=True)
    _rubric = "".join(f"<p><b>{_f}</b>: {_esc(_d)}<br>{{{_f}}}</p>" for _f, _d in labels.RUBRIC.items())
    _behaviour = {"ask_back": "ถามกลับเพื่อขอข้อมูลที่ขาดหรือไม่", "misconception": "ชี้แจงความเข้าใจผิดในคำถามหรือไม่",
                  "out_of_scope": "บอกว่าเรื่องนี้อยู่นอกขอบเขตเอกสารหรือไม่ โดยไม่ตอบผิด ๆ"}.get(q.kind)
    _template = (
        "<h3>แหล่งอ้างอิงที่ดึงมา</h3>" + "".join(_blocks)
        + "<h3>ให้คะแนนคำตอบ</h3>" + _rubric
        + f"<p><small>{_esc(labels.REFUSAL_RULE)}</small></p>"
        + (f"<p><b>behaviour</b>: {_behaviour}<br>{{behaviour}}</p>" if _behaviour else "")
        + "<p><b>tags</b><br>{tags}</p><p><b>หมายเหตุ</b><br>{note}</p>"
    )
    form = mo.ui.batch(mo.Html(_template), _elements).form(submit_button_label="บันทึก (Save)", bordered=True)
    hits = rec["hits"]
    return form, hits, q, qid, rec


@app.cell
def _(mo, q, questions, rec, records):
    _earlier = [records[p.id] for p in sorted(questions.values(), key=lambda p: p.turn or 0)
                if q.set and p.set == q.set and p.turn < q.turn and p.id in records]
    _history = [mo.md(f"**รอบ {questions[r['id']].turn}:** {r['question']}\n\n> {r['answer'][:500]}") for r in _earlier]
    _kind = {"normal": "", "multi_turn": "คำถามหลายรอบ", "ask_back": "ควรถามกลับ (ข้อมูลไม่ครบ)",
             "misconception": "ควรแก้ความเข้าใจผิด", "out_of_scope": "นอกขอบเขต"}[q.kind]
    mo.vstack([
        mo.md(f"### {q.id} · {q.category} · {q.difficulty or '-'}" + (f" · **{_kind}**" if _kind else "")),
        *([mo.accordion({"รอบก่อนหน้า": mo.vstack(_history)})] if _history else []),
        mo.md(f"**คำถาม:** {q.text}"),
        mo.callout(mo.md(rec["answer"]), kind="neutral"),
        mo.md(f"<small>อ้างอิงที่ไม่มีอยู่จริง: {rec['bad_citations']}</small>") if rec["bad_citations"] else mo.md(""),
    ])
    return


@app.cell
def _(form):
    form
    return


@app.cell
def _(form, hits, labels, mo, qid, reviewer, run_id, set_saved):
    mo.stop(form.value is None)
    _v = form.value
    _missing = [k for k in ("grounded", "correct", "useful", "behaviour") if k in _v and not _v[k]]
    _missing += [f"chunk {i}" for i in range(1, len(hits) + 1) if not _v[f"c{i}"]]
    _answer = dict(grounded=_v["grounded"] or "", correct=_v["correct"] or "", useful=_v["useful"] or "",
                   behaviour=_v.get("behaviour", "na") or "", tags=";".join(_v["tags"]), note=_v["note"].strip())
    _chunks = {h["chunk_id"]: dict(relevance=_v[f"c{i}"] or "") for i, h in enumerate(hits, 1)}
    labels.save(reviewer, run_id, qid, _answer, _chunks)
    set_saved(lambda n: n + 1)
    mo.callout(f"บันทึก {qid} แล้ว" + (f" (ยังไม่ครบ: {', '.join(_missing)}; ข้อนี้จะยังอยู่ในคิว)" if _missing else ""),
               kind="warn" if _missing else "success")
    return


@app.cell
def _(get_saved, labels, mo, run_id, shared):
    get_saved()
    _agr = labels.agreement(run_id, shared)
    _rows = "\n".join(f"| {f} | {n} | {'-' if n == 0 else f'{a:.0%}'} |" for f, (n, a) in _agr.items())
    mo.accordion({"ความสอดคล้องระหว่างผู้ตรวจ (ชุดร่วม)": mo.md(
        "| item | pairs | exact agreement |\n|---|---|---|\n" + _rows
        + "\n\nCompare only after everyone has finished the shared set; do not discuss the shared questions before then.")})
    return


if __name__ == "__main__":
    app.run()
