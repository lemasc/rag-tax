import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="RAG answer browser")


@app.cell
def _():
    """Read-only view of a scored run: answers, retrieved sources, the judge's verdict and, where reviewers have
    labelled, the human labels next to it. Written for the team, not for reviewers: it shows the judge's scores,
    which rag/review.py deliberately does not (they would anchor the labels).

    Needs rag/out/runs/<run>/scores.jsonl (uv run python -m rag.evaluate).
    Run: uv run marimo edit rag/browse.py     (restart after changing rag/evaluate.py or rag/labels.py)
    """
    import html
    import json
    import sys
    from pathlib import Path

    import marimo as mo

    ROOT = Path(__file__).parent.parent
    sys.path.insert(0, str(ROOT))
    from rag import chunk_version, evaluate, labels
    from rag.answer import KIND_TH, year_label
    from rag.questions import load

    return KIND_TH, ROOT, chunk_version, evaluate, html, json, labels, load, mo, year_label


@app.cell
def _(labels, mo):
    _scored = [r for r in labels.runs() if (labels.RUNS / r / "scores.jsonl").exists()]
    pick_run = mo.ui.dropdown(_scored, value=(_scored or [None])[0], label="Run (with scores)")
    refresh = mo.ui.refresh(label="โหลดป้ายกำกับของผู้ตรวจใหม่", default_interval=None)
    mo.vstack([mo.md("## ดูคำตอบและผลของ judge (Answer browser)"), mo.hstack([pick_run, refresh], justify="start")])
    return pick_run, refresh


@app.cell
def _(ROOT, chunk_version, evaluate, json, labels, load, mo, pick_run, refresh):
    mo.stop(not pick_run.value, mo.callout("ยังไม่มี run ที่ให้คะแนนแล้ว: uv run python -m rag.evaluate", kind="warn"))
    refresh.value  # reloading the human labels is the only reason this cell reruns
    run_id = pick_run.value
    _dir = labels.RUNS / run_id
    records = {r["id"]: r for r in map(json.loads, (_dir / "answers.jsonl").open(encoding="utf-8"))}
    scores = {s["id"]: s for s in map(json.loads, (_dir / "scores.jsonl").open(encoding="utf-8"))}
    score_config = json.loads((_dir / "scores_config.json").read_text(encoding="utf-8"))
    chunks = {c["chunk_id"]: c for c in map(json.loads, (ROOT / "rag" / "out" / "chunks.jsonl").open(encoding="utf-8"))}
    questions = {q.id: q for q in load()}
    reviewers = labels.reviewers()
    human_a = {r: labels.answer_labels(r) for r in reviewers}
    human_c = {r: labels.chunk_labels(r) for r in reviewers}
    # the judge scored in_subset answers only; earlier turns of a set are answered but not scored
    gap = {q: evaluate.human_gap(s["rubric"], [human_a[r][(run_id, q)] for r in reviewers if (run_id, q) in human_a[r]])
           for q, s in scores.items()}
    _other = chunk_version.problem(chunk_version.run_sha(_dir), f"run {run_id}")  # chunk text below would be another version's
    mo.vstack([
        mo.callout(mo.md(f"**Chunks differ from this run's**: chunk text shown here may not be what the run retrieved.\n\n{_other}"),
                   kind="warn") if _other else mo.md(""),
        mo.md(
            f"Judge **{score_config['judge']['model']}** prompt {score_config['judge_version']} · scored {score_config['scored'][:10]} · "
            f"{len(scores)} answers · reviewers with labels: {', '.join(reviewers) or 'none yet'}"
        ),
    ])
    return (
        chunks,
        gap,
        human_a,
        human_c,
        questions,
        records,
        reviewers,
        run_id,
        scores,
    )


@app.cell
def _(mo, questions, scores):
    f_cat = mo.ui.dropdown(["(ทั้งหมด)"] + sorted({q.category for i, q in questions.items() if i in scores}), value="(ทั้งหมด)", label="หมวด")
    f_kind = mo.ui.dropdown(["(ทั้งหมด)", "normal", "multi_turn", "ask_back", "misconception", "out_of_scope"], value="(ทั้งหมด)", label="ประเภท")
    f_tag = mo.ui.dropdown(["(ทั้งหมด)"] + sorted({t for s in scores.values() for t in s["rubric"]["tags"]}), value="(ทั้งหมด)", label="tag ของ judge")
    f_gap = mo.ui.switch(label="เฉพาะข้อที่ judge ต่างจากผู้ตรวจ")
    mo.hstack([f_cat, f_kind, f_tag, f_gap], justify="start")
    return f_cat, f_gap, f_kind, f_tag


@app.cell
def _(
    f_cat,
    f_gap,
    f_kind,
    f_tag,
    gap,
    human_a,
    mo,
    questions,
    run_id,
    scores,
):
    def _fmt(x):
        return None if x is None else round(x, 2)

    _rows = []
    for _qid, _s in scores.items():
        _q, _r = questions[_qid], _s["rubric"]
        if f_cat.value != "(ทั้งหมด)" and _q.category != f_cat.value:
            continue
        if f_kind.value != "(ทั้งหมด)" and _q.kind != f_kind.value:
            continue
        if f_tag.value != "(ทั้งหมด)" and f_tag.value not in _r["tags"]:
            continue
        if f_gap.value and not gap[_qid]:
            continue
        _rows.append({
            "id": _qid, "หมวด": _q.category, "ประเภท": _q.kind, "คำถาม": _q.text[:50],
            "faith": _fmt(_s["faithfulness"]["score"]), "relev": _fmt(_s["relevance"]["score"]),
            "grounded": _r["grounded"], "correct": _r["correct"], "useful": _r["useful"], "behav": _r["behaviour"],
            "tags": ", ".join(_r["tags"]), "ผู้ตรวจ": sum(1 for _h in human_a.values() if (run_id, _qid) in _h),
            "gap": _fmt(gap[_qid]),
        })
    table = mo.ui.table(_rows, selection="single", page_size=15, label=f"{len(_rows)} ข้อ (คลิกหัวคอลัมน์เพื่อเรียง, เลือกแถวเพื่อดูรายละเอียด)")
    table
    return (table,)


@app.cell
def _(mo, table):
    mo.stop(not table.value, mo.callout("เลือกแถวในตารางเพื่อดูรายละเอียด", kind="info"))
    qid = table.value[0]["id"]
    return (qid,)


@app.cell
def _(
    KIND_TH,
    chunks,
    html,
    human_a,
    human_c,
    mo,
    qid,
    questions,
    records,
    reviewers,
    run_id,
    scores,
    year_label,
):
    rec, q, s = records[qid], questions[qid], scores[qid]
    rub, fa, rel = s["rubric"], s["faithfulness"], s["relevance"]

    def _esc(t):
        return html.escape(t).replace("\n", "<br>")

    _earlier = [records[p.id] for p in sorted(questions.values(), key=lambda p: p.turn or 0)
                if q.set and p.set == q.set and p.turn < q.turn and p.id in records]
    _history = [mo.md(f"**รอบ {questions[r['id']].turn}:** {r['question']}\n\n> {r['answer'][:500]}") for r in _earlier]

    _head = mo.vstack([
        mo.md(f"### {q.id} · {q.category} · {q.difficulty or '-'} · {q.kind}"),
        *([mo.accordion({"รอบก่อนหน้า": mo.vstack(_history)})] if _history else []),
        mo.md(f"**คำถาม:** {q.text}"),
        mo.callout(mo.md(rec["answer"]), kind="neutral"),
    ])

    # judge verdict
    _bad = [c for c in fa["claims"] if not c["supported"]]
    _faith = "-" if fa["score"] is None else f"{fa['score']:.2f}"
    _claims = mo.md("\n".join(f"- ✗ {c['claim']}  \n  _{c['reason']}_" for c in _bad)) if _bad else mo.md("ทุกข้อความมีในเอกสาร" if fa["claims"] else "ไม่มีข้อความที่ตรวจได้")
    _verdict = mo.vstack([
        mo.md(f"**Judge** · grounded {rub['grounded']} · correct {rub['correct']} · useful {rub['useful']} · behaviour {rub['behaviour']}"
              f" · tags: {', '.join(rub['tags']) or '-'}\n\n> {rub['note']}"),
        mo.md(f"**Faithfulness** {_faith} ({sum(c['supported'] for c in fa['claims'])}/{len(fa['claims'])} claims). "
              "ข้อความที่ไม่มีในเอกสาร:"),
        _claims,
        mo.md(f"**Relevance** {rel['score']:.2f}{' (judge: คำตอบไม่ชัดเจน → 0)' if rel['noncommittal'] else ''}. "
              "คำถามที่คำตอบนี้ตอบได้ตามที่ judge เขียน:\n" + "\n".join(f"- {x}" for x in rel["questions"])),
    ])

    # human labels next to the judge
    _human_rows = []
    for _r in reviewers:
        _lab = human_a[_r].get((run_id, qid))
        if _lab:
            _human_rows.append({"ผู้ตรวจ": _r, **{f: _lab[f] for f in ("grounded", "correct", "useful", "behaviour")},
                                "tags": _lab["tags"].replace(";", ", "), "note": _lab["note"]})
    _human = mo.ui.table(_human_rows, selection=None, label="ป้ายกำกับของผู้ตรวจ (ตรงกับ judge เมื่อค่าเท่ากัน)") if _human_rows else mo.md("_ยังไม่มีผู้ตรวจข้อนี้_")

    # sources: judge and human relevance per chunk
    _src = {}
    for _n, _h in enumerate(rec["hits"], 1):
        _c = chunks.get(_h["chunk_id"], {})
        _humans = " ".join(f"{_r}:{human_c[_r][(qid, _h['chunk_id'])]['relevance']}" for _r in reviewers if (qid, _h["chunk_id"]) in human_c[_r])
        _cited = " · อ้างอิงในคำตอบ" if _h["chunk_id"] in rec["cited"] else ""
        _title = (f"[{_n}] {_c.get('header', '(chunk missing)')[:70]} — judge {rub['relevance'][str(_n)]}"
                  f"{' · ' + _humans if _humans else ''}{_cited}")
        _meta = f"{KIND_TH.get(_c.get('kind'), _c.get('kind', '?'))} · {year_label(_c) if _c else '?'} · {_h['chunk_id']}"
        _src[_title] = mo.Html(f"<small>{html.escape(_meta)}</small><div style='font-size:0.9em;margin-top:0.4em'>{_esc(_c.get('text', ''))}</div>")

    mo.vstack([_head, mo.hstack([_verdict, _human], widths=[3, 2], align="start"), mo.md("#### แหล่งอ้างอิงที่ดึงมา"), mo.accordion(_src)])
    return


@app.cell
def _(evaluate, json, labels, mo, pick_run, refresh, scores):
    refresh.value
    _path = labels.RUNS / pick_run.value
    _agree = evaluate.compare(_path, list(scores.values()))
    _rows = [{"ผู้ตรวจ": rev, "item": f, "n": a["n"], "exact": None if not a["n"] else round(a["exact"], 2),
              "within one": None if "within_one" not in a else round(a["within_one"], 2),
              "bias (judge − human)": None if "bias" not in a else round(a["bias"], 2)}
             for rev, fields in _agree.items() for f, a in fields.items()]
    _summary = json.loads((_path / "scores_summary.json").read_text(encoding="utf-8"))
    _cat = [{"หมวด": c, **{k: (None if v is None else round(v, 2)) for k, v in r.items() if k not in ("behaviour",)}}
            for c, r in _summary["by_category"].items()]
    mo.accordion({
        "สรุปตามหมวด (คำถามทั่วไป + หลายรอบ)": mo.ui.table(_cat, selection=None),
        "judge เทียบกับผู้ตรวจ (ใช้ได้เมื่อมีป้ายกำกับครบ)": mo.ui.table(_rows, selection=None) if _rows else mo.md("_ยังไม่มีป้ายกำกับที่ครบ_"),
    })
    return


if __name__ == "__main__":
    app.run()
