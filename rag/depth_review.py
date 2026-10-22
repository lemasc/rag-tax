import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium", app_title="ตรวจ top-50")


@app.cell
def _():
    """Human check of the top-50 diagnostic (rag/depth.py): for each question retrieval missed, does the chunk the panel
    thought answers it really answer it? One chunk per question; the next candidate only when the last was not a 2.
    Round 1 (closed) graded at most three panel 2s per question -> rag/eval/labels/<name>/depth.csv. Round 2 grades the
    chunks of depth.ROUND2 for the questions round 1 left at D -> depth_r2.csv.

    Run: uv run marimo run rag/depth_review.py --token-password <password>
    """
    import html
    import sys
    from pathlib import Path

    import marimo as mo

    ROOT = Path(__file__).parent.parent
    sys.path.insert(0, str(ROOT))  # `marimo run` does not put the repo root on the path
    from rag import depth, labels
    from rag.answer import KIND_TH, year_label
    from rag.chunk import OUT, read_jsonl
    from rag.questions import load

    return KIND_TH, OUT, depth, html, labels, load, mo, read_jsonl, year_label


@app.cell
def _(OUT, depth, labels, load, read_jsonl):
    _items = [i for i in read_jsonl(depth.OUT / "pool.jsonl") if i["group"] == "miss"]
    _per_judge = {j: read_jsonl(depth.OUT / "judgments" / f"{j}.jsonl") for j in depth.DEFAULT_PANEL}
    _panel = depth.panel_grades(_per_judge, strict=False)
    items = {i["id"]: i for i in _items}
    cands1 = {i["id"]: depth.candidates(i["pool"], _panel[i["id"]]) for i in _items}
    cands2 = depth.round2_candidates(items)
    chunks = {c["chunk_id"]: c for c in read_jsonl(OUT / "chunks.jsonl")}
    records = {r["id"]: r for r in read_jsonl(labels.RUNS / depth.BASE_RUN / "answers.jsonl")}
    questions = {q.id: q for q in load()}
    return cands1, cands2, chunks, items, questions, records


@app.cell
def _(depth, html, mo):
    # one strip drawn the same way on every screen: where the question's chunks sit in the hybrid ranking
    def strip(item, marks, big=False):
        """`marks`: {chunk_id: (colour, label)} drawn as tall markers, at the far right when the chunk is outside the
        pool; every other chunk of the pool is a thin tick."""
        _zones = [(0, 25, "ส่งให้ตอบ", "อันดับ 1–5", 0.22), (25, 75, "เจอแต่ไม่ถึง 5", "อันดับ 6–50", 0.12), (75, 100, "ตกรอบ", "อันดับ 51+ · ขวาสุด = นอกผลค้น", 0.05)]
        _h = 46 if big else 30
        _parts = [f"<div style='position:absolute;left:{a}%;width:{b - a}%;top:0;bottom:0;background:rgba(14,138,138,{o});"
                  f"border-right:1px solid rgba(127,127,127,.35)'></div>" for a, b, _n, _r, o in _zones]
        _parts += [f"<div style='position:absolute;left:{depth.strip_position(e['hybrid_rank'])}%;width:2px;top:{_h * .55:.0f}px;bottom:0;"
                   f"background:{'#0e8a8a' if e['returned'] else 'rgba(127,127,127,.55)'}'></div>" for e in item["pool"]]
        _rank = {e["chunk_id"]: e["hybrid_rank"] for e in item["pool"]}
        for _cid, (_c, _t) in marks.items():
            _x = depth.strip_position(_rank.get(_cid))
            _parts.append(f"<div style='position:absolute;left:calc({_x}% - 3px);width:6px;top:2px;bottom:0;background:{_c};border-radius:2px'></div>")
            if big and _t:
                _align = "right:" + f"calc({100 - _x}% + 8px)" if _x > 60 else f"left:calc({_x}% + 8px)"
                _parts.append(f"<div style='position:absolute;{_align};top:0;font-size:.78em;color:{_c};white-space:nowrap;font-weight:600'>{html.escape(_t)}</div>")
        _labels = "".join(f"<div style='position:absolute;left:{a}%;width:{b - a}%;text-align:center'>{n}<br>{r}</div>" for a, b, n, r, _ in _zones) if big else ""
        _under = f"<div style='position:relative;height:2.6em;font-size:.72em;opacity:.75;margin-top:2px'>{_labels}</div>" if big else ""
        return mo.Html(f"<div style='position:relative;height:{_h}px;border:1px solid rgba(127,127,127,.4);border-radius:4px;overflow:hidden'>{''.join(_parts)}</div>{_under}")

    def chip(text, colour):
        return (f"<span style='display:inline-block;padding:0 .6em;border-radius:999px;font-size:.82em;font-weight:600;"
                f"background:{colour}22;color:{colour};border:1px solid {colour}66;white-space:nowrap'>{html.escape(text)}</span>")

    def rank_th(rank):
        return "นอกผลค้น" if rank is None else f"อันดับ {rank}"

    return chip, rank_th, strip


@app.cell
def _(labels, mo):
    known = labels.reviewers()
    pick_name = mo.ui.dropdown(known, label="ผู้ตรวจ (Reviewer)", value=known[0] if len(known) == 1 else None)
    new_name = mo.ui.text(label="หรือชื่อใหม่", placeholder="a-z 0-9 - _")
    pick_round = mo.ui.radio({"รอบ 2 (ตอนนี้)": 2, "รอบ 1 (ปิดแล้ว ดูย้อนหลังได้)": 1}, value="รอบ 2 (ตอนนี้)", inline=True, label="รอบ")
    mo.vstack([
        mo.md("## ตรวจว่าเอกสารที่ค้นเจอตอบคำถามได้จริงหรือไม่"),
        mo.hstack([pick_name, new_name], justify="start"),
        pick_round,
    ])
    return new_name, pick_name, pick_round


@app.cell
def _(cands1, cands2, mo, pick_round):
    rnd = pick_round.value
    cands = cands2 if rnd == 2 else cands1
    order = [(q, e["chunk_id"]) for q, cs in cands.items() for e in cs]  # every candidate, question by question
    if rnd == 2:
        _why = mo.callout(mo.md(f"""**รอบ 2 (เพิ่ม 22 ต.ค. 2569) · ทำไมต้องมีรอบนี้**

    รอบ 1 ให้ดูไม่เกิน 3 ชิ้นต่อข้อ คือชิ้นที่ผู้ตัดสิน LLM ให้ 2 และอยู่อันดับสูงสุด ผลรวมของทีมคือ 9 จาก 13 ข้อไม่มีชิ้นที่ตอบได้ (D) ซึ่งเท่ากับเกณฑ์ 9 ข้อ **พอดี**

    แต่ในข้อเหล่านี้ LLM ให้ 2 มากกว่า 3 ชิ้น (บางข้อถึง 17 ชิ้น) ชิ้นที่เหลือไม่มีใครเคยอ่าน และเมื่อค้นคำสำคัญในคลังเอกสารทั้งหมด ก็เจอชิ้นที่ระบบค้นไม่เคยดึงขึ้นมาเลย
    ผล D ของรอบ 1 จึงแปลว่า "3 ชิ้นแรกไม่ตอบ" ยังไม่ใช่ "ไม่มีชิ้นที่ตอบได้" ถ้าเปลี่ยนแค่ 1 ข้อ ผลสรุปจะกลายเป็น "ผลผสม"

    **ชิ้นในรอบนี้มาจากไหน** (Claude เป็นผู้เลือก หลังอ่านผลค้นคำสำคัญ)
    - <b style='color:#d9822b'>ส้ม</b> ผู้ตัดสิน LLM ให้ 2 แต่เกินโควตา 3 ชิ้นของรอบ 1 จึงยังไม่มีใครตรวจ
    - <b style='color:#7d3cbd'>ม่วง</b> ค้นเจอด้วยคำสำคัญ แต่ไม่ติด 50 อันดับแรกของทั้งสองวิธีค้น (นอกผลค้น)

    **งานของคุณ:** {len(cands)} ข้อ ไม่เกิน {len(order)} ชิ้น (ประมาณ 10 นาที) ให้คะแนนแบบเดิม ถ้าชิ้นแรกของข้อได้ 2 ข้อนั้นจบเลย
    คะแนนเก็บแยกใน `depth_r2.csv` รอบ 1 ไม่ถูกแก้ ข้อที่ผู้ตรวจรอบ 1 เห็นไม่ตรงกัน (Q0207, Q0213) ใช้ผลรอบ 1 ตามเดิม"""), kind="warn")
    else:
        _why = mo.callout(mo.md("""**รอบ 1 (ปิดแล้ว)** · ระบบค้นไม่ถึงคำตอบใน 13 คำถาม แต่ผู้ตัดสินที่เป็น LLM บอกว่ามีชิ้นที่ "ตอบได้" อยู่ในผลค้น 50 อันดับแรก
    เมื่อลองอ่านดู หลายชิ้นดูไม่ตอบจริง จึงให้คนตัดสินแทน จะได้รู้ว่าปัญหาอยู่ที่ **การจัดอันดับ** หรือที่ **คลังเอกสาร**

    ข้อละ 1 ชิ้น ถ้าไม่ตอบ จะมีชิ้นถัดไปให้ดู (ไม่เกิน 3 ชิ้นต่อข้อ) ดูหรือแก้คะแนนได้ แต่งานตอนนี้อยู่ที่รอบ 2"""), kind="info")
    _why
    return cands, order, rnd


@app.cell
def _(labels, mo, new_name, pick_name):
    _raw = new_name.value.strip() or pick_name.value or ""
    reviewer, name_error = None, None
    if _raw:
        try:
            reviewer = labels.check_name(_raw)
        except ValueError as e:
            name_error = str(e)
    mo.stop(not reviewer, mo.callout(name_error or "เลือกหรือพิมพ์ชื่อผู้ตรวจ", kind="warn" if name_error else "info"))
    return (reviewer,)


@app.cell
def _(mo):
    get_saved, set_saved = mo.state(0)  # bumped after each save, so the queue and the overview recompute
    return get_saved, set_saved


@app.cell
def _(
    cands,
    cands1,
    cands2,
    chip,
    depth,
    get_saved,
    items,
    labels,
    mo,
    questions,
    rank_th,
    reviewer,
    rnd,
    strip,
):
    get_saved()
    mine = depth.human_grades([reviewer], rnd)
    _team1 = depth.human_grades(labels.reviewers())
    _team2 = depth.human_grades(labels.reviewers(), 2)

    def _of(grades, q):
        return {k[1]: g for k, g in grades.items() if k[0] == q}

    _queue = [q for q, c in cands.items() if depth.status(c, _of(mine, q))[0] == "pending"]

    def _row(q):
        _r1 = depth.status(cands1[q], _of(_team1, q))
        _r2 = depth.status(cands2[q], _of(_team2, q)) if q in cands2 else None
        _cls, _cls1 = depth.final_class(_r1, _r2), depth.final_class(_r1, None)
        _marks = {c["chunk_id"]: ("#c0392b" if g != 2 else "#2e9d5b", "")
                  for cs, tg in ((cands1[q], _of(_team1, q)), (cands2.get(q, []), _of(_team2, q)))
                  for c in cs if (g := tg.get(c["chunk_id"])) is not None}
        if _cls is None:
            _label = chip("ยังไม่ครบ" if _marks else "ยังไม่ตรวจ", "#888888")
        elif _cls == "D":
            _label = chip("D · ไม่พบชิ้นที่ตอบได้", "#c0392b")
        else:
            _e = (_r1 if _r1[0] == "found" else _r2)[1]
            _label = chip("A · อยู่ใน 5 อันดับแรก" if _cls == "A" else f"{_cls} · {rank_th(_e['hybrid_rank'])}", "#2e9d5b" if _cls == "A" else "#d9822b")
        if q not in cands2:
            _src = "รอบ 1"
        elif _cls is None or _cls == _cls1:
            _src = "รอบ 1 + รอบ 2"
        else:
            _src = f"รอบ 2 เปลี่ยนจาก {_cls1}"
        return (f"<tr><td style='white-space:nowrap'><b>{q}</b></td><td>{questions[q].text[:46]}</td><td style='min-width:14em'>"
                f"{strip(items[q], _marks).text}</td><td style='white-space:nowrap'>{_label}<br><small>{_src}</small></td></tr>"), _cls, _cls1

    _rows = [_row(q) for q in cands1]

    def _count(i):
        _n = {"A": 0, "B": 0, "C": 0, "D": 0, None: 0}
        for _r in _rows:
            _n[_r[i]] += 1
        return _n

    def _verdict(n):
        _rank_n, _need = n["B"] + n["C"], 9
        return ("ปัญหาการจัดอันดับเป็นหลัก → ทำ tax-year boost / reranker ต่อ" if _rank_n >= _need else
                "ปัญหาคลังเอกสารหรือถ้อยคำเป็นหลัก → เพิ่มแหล่ง / เขียนคำถามใหม่" if n["D"] >= _need else "ผลผสม ไม่ฟันธง")

    _n, _n1 = _count(1), _count(2)
    _line = lambda n: f"A {n['A']} · B {n['B']} · C {n['C']} · D {n['D']}"  # noqa: E731
    _old = f"รอบ 1 อย่างเดียว: {_line(_n1)} → {_verdict(_n1)}"
    if _n[None]:
        _say = mo.md(f"{_old}<br>สรุปสองรอบจะขึ้นเมื่อตรวจครบ (ยังไม่ครบ {_n[None]} ข้อ)")
    else:
        _say = mo.callout(mo.md(f"**ตามกติกาที่ตั้งไว้ก่อนตรวจ** (ต้องมี ≥ 9 จาก 13 ข้อ)<br>{_old}<br>"
                                f"**รวมรอบ 2: {_line(_n)} → {_verdict(_n)}**"), kind="success")
    mo.vstack([
        mo.md(f"**{reviewer}** · รอบ {rnd}: ตรวจแล้ว {len(cands) - len(_queue)}/{len(cands)} ข้อ · เหลือ {len(_queue)} ข้อ"),
        mo.accordion({"ภาพรวมทั้ง 13 ข้อ (ผลรวมของผู้ตรวจทุกคน ทั้งสองรอบ)": mo.vstack([
            mo.md("แถบแสดงอันดับของเอกสารทุกชิ้นที่ค้นเจอ (ขีดเทา) และ **ชิ้นที่ส่งให้ระบบตอบจริง** (ขีดเขียวน้ำเงิน) "
                  "เครื่องหมาย <span style='color:#2e9d5b'>เขียว</span> = คนว่าตอบได้ <span style='color:#c0392b'>แดง</span> = คนว่าไม่ตอบ "
                  "เครื่องหมายที่ขอบขวาสุด = ชิ้นนอกผลค้น"),
            mo.Html("<table style='width:100%;font-size:.92em'>" + "".join(h for h, _, _ in _rows) + "</table>"),
            _say])}),
    ])
    return (mine,)


@app.cell
def _(cands, depth, mo, reviewer, rnd):
    # where the reviewer is looking: starts at the first candidate still to grade; moved by the navigation and by saving
    get_pos, set_pos = mo.state(depth.next_pending(cands, depth.human_grades([reviewer], rnd)) or next((q, cs[0]["chunk_id"]) for q, cs in cands.items()))
    return get_pos, set_pos


@app.cell
def _(cands, depth, get_pos, mine, mo, order, questions, rank_th, set_pos):
    _q, _c = get_pos()
    _i = order.index((_q, _c))

    def _own(q):
        return {k[1]: g for k, g in mine.items() if k[0] == q}

    def _mark(q):
        _st = depth.status(cands[q], _own(q))[0]
        return "○" if _st == "pending" and not _own(q) else "◐" if _st == "pending" else "●"

    def _open(q):  # a question's first candidate still to grade, else its first
        _st, _e = depth.status(cands[q], _own(q))
        return q, (_e if _st == "pending" else cands[q][0])["chunk_id"]

    _qopts = {f"{_mark(q)} {q} {questions[q].text[:46]}": q for q in cands}
    pick_q = mo.ui.dropdown(_qopts, value=next(k for k, v in _qopts.items() if v == _q), on_change=lambda q: set_pos(_open(q)),
                            label="คำถาม (○ ยังไม่ตรวจ ◐ ตรวจบางส่วน ● จบแล้ว)", full_width=True)
    _sym = lambda c: {2: "✓ 2", 1: "1", 0: "0"}.get(mine.get((_q, c["chunk_id"])), "ยังไม่ตรวจ")  # noqa: E731
    _copts = {f"ชิ้นที่ {k} · {rank_th(c['hybrid_rank'])} · {_sym(c)}": c["chunk_id"] for k, c in enumerate(cands[_q], 1)}
    pick_c = mo.ui.radio(_copts, value=next(k for k, v in _copts.items() if v == _c), inline=True, on_change=lambda c: set_pos((_q, c)))
    _later = depth.next_pending(cands, mine, (_q, _c))
    prev_b = mo.ui.button(label="← ก่อนหน้า", on_click=lambda _: set_pos(order[_i - 1]), disabled=_i == 0)
    next_b = mo.ui.button(label="ถัดไป →", on_click=lambda _: set_pos(order[_i + 1]), disabled=_i == len(order) - 1)
    todo_b = mo.ui.button(label="ไปชิ้นที่ยังไม่ตรวจ ⇥", on_click=lambda _: set_pos(_later), disabled=_later is None or _later == (_q, _c))
    mo.vstack([pick_q, mo.hstack([pick_c, prev_b, next_b, todo_b], justify="start", align="center", wrap=True),
               mo.md("<small>ดูข้ามไปมาได้อิสระ ชิ้นไหนจะตรวจก่อนก็ได้ และกลับมาแก้คะแนนได้เสมอ</small>")])
    return


@app.cell
def _(
    KIND_TH,
    cands,
    cands1,
    chunks,
    depth,
    get_pos,
    html,
    items,
    labels,
    mine,
    mo,
    questions,
    rank_th,
    records,
    reviewer,
    rnd,
    strip,
    year_label,
):
    qid, cid = get_pos()
    q, it, c = questions[qid], items[qid], chunks[cid]
    _cs = cands[qid]
    _e = next(e for e in _cs if e["chunk_id"] == cid)
    _k = _cs.index(_e) + 1
    _r = _e["hybrid_rank"]
    _earlier = [records[p.id] for p in sorted(questions.values(), key=lambda p: p.turn or 0)
                if q.set and p.set == q.set and p.turn < q.turn and p.id in records]
    _asked = [e["chunk_id"] for e in _cs if e["chunk_id"] != cid and (qid, e["chunk_id"]) in mine]
    _colour = "#7d3cbd" if _r is None else "#d9822b"
    _marks = {x: ("#c0392b", "") for x in _asked if mine[(qid, x)] != 2}
    if rnd == 2:  # what round 1 already turned down for this question
        _team1 = depth.human_grades(labels.reviewers())
        _marks |= {e["chunk_id"]: ("#c0392b", "") for e in cands1[qid] if _team1.get((qid, e["chunk_id"]), 2) != 2}
    _marks[cid] = (_colour, f"ชิ้นนี้ · {rank_th(_r)}")
    _returned = "".join(f"<li>อันดับ {e['hybrid_rank']}: {html.escape(chunks[e['chunk_id']]['header'][:90])}</li>"
                        for e in sorted((e for e in it["pool"] if e["returned"]), key=lambda e: e["hybrid_rank"]))
    if _r is None:
        _where = "ชิ้นนี้ <b>ไม่ติด 50 อันดับแรกของทั้งสองวิธีค้น</b> (dense และ BM25) ระบบจึงไม่เคยดึงขึ้นมาเลย"
    elif _r <= 5:
        _where = "ชิ้นนี้ <b>อยู่ใน 5 อันดับแรกที่ระบบเห็นแล้ว</b>"
    else:
        _where = f"ชิ้นนี้อยู่ <b>อันดับ {_r}</b> ระบบเห็นแค่ 5 อันดับแรก จึงไม่เคยเห็นชิ้นนี้"
    _t = html.escape(c["text"]).replace("\n", "<br>")
    _url = html.escape(c.get("url", ""))
    _head = [mo.md(f"### {qid} · {q.category}"), mo.md(f"**คำถาม:** {q.text}")]
    if _earlier:
        _head.insert(1, mo.accordion({"รอบก่อนหน้า (คำถามนี้ต่อจากบทสนทนา)": mo.md("\n\n".join(f"**{r['question']}**\n\n> {r['answer'][:400]}" for r in _earlier))}))
    if rnd == 2:
        _src = ("ค้นเจอด้วยคำสำคัญในคลังเอกสารทั้งหมด แต่ระบบค้นไม่เคยดึงขึ้นมา" if _r is None else
                "ผู้ตัดสิน LLM ให้ 2 แต่รอบ 1 ให้ดูแค่ 3 ชิ้นแรกของข้อนี้ ชิ้นนี้จึงยังไม่มีใครตรวจ")
        _head.append(mo.md(f"<span style='color:{_colour}'>■</span> **ที่มาของชิ้นนี้ (รอบ 2):** {_src} · "
                           f"รอบ 1 ทีมตรวจข้อนี้ไป {len(cands1[qid])} ชิ้น ไม่มีชิ้นที่ตอบได้ (แดงบนแถบ)"))

    _opts = {"2 ตอบได้: มีสิ่งที่ต้องใช้ตอบคำถามนี้ (หรือส่วนที่จำเป็น)": 2,
             "1 ใกล้เคียง: หัวข้อเดียวกัน แต่ไม่ได้ตอบ (กฎข้างเคียง ตัวเลขปีอื่น ความรู้พื้นหลัง)": 1,
             "0 ไม่เกี่ยว": 0}
    _prev = mine.get((qid, cid))
    _was = mo.callout(f"คุณตรวจชิ้นนี้แล้ว (ให้ {_prev}) แก้และบันทึกใหม่ได้", kind="neutral") if _prev is not None else mo.md("")
    _saved = next((k for k, v in _opts.items() if v == _prev), None)
    rel = mo.ui.radio(_opts, value=_saved)
    note = mo.ui.text(value=depth.read_depth_labels(reviewer, rnd).get((qid, cid), {}).get("note", ""), placeholder="หมายเหตุ เช่น ตอบแค่บางส่วน / ตัวเลขเก่า (ไม่บังคับ)", full_width=True)
    form = mo.ui.batch(mo.Html("<p><b>ชิ้นนี้ตอบคำถามได้หรือไม่?</b></p>{rel}<p>{note}</p>"), dict(rel=rel, note=note)).form(
        submit_button_label="บันทึก (Save)", bordered=True)
    mo.vstack([
        *_head,
        mo.md(f"**ระบบค้นเจอเอกสารที่คิดว่าตอบได้ที่ไหน** · {_where}"),
        strip(it, _marks, big=True),
        mo.accordion({"5 ชิ้นที่ระบบส่งให้ตอบจริง": mo.Html(f"<ol style='margin:0;font-size:.9em'>{_returned}</ol>")}),
        mo.md(f"#### ชิ้นที่ต้องตัดสิน ({_k}/{len(_cs)})"),
        mo.Html(f"<div style='border:1px solid rgba(127,127,127,.4);border-radius:6px;padding:.8em 1em'>"
                f"<b>{html.escape(c['header'])}</b><br><small>{html.escape(KIND_TH.get(c['kind'], c['kind']))} · {html.escape(year_label(c))} · {html.escape(cid)}</small>"
                f"<div style='max-height:22em;overflow:auto;margin:.6em 0;font-size:.92em'>{_t}</div>"
                f"<small><a href='{_url}' target='_blank'>{_url}</a></small></div>"),
        mo.md("<small>ตัดสินจากตัวชิ้นเอกสารเทียบกับคำถามเท่านั้น (ไม่ต้องดูคำตอบของระบบ) คะแนน 2 ต้องมีเนื้อหาที่ตอบได้จริง ไม่ใช่แค่หัวข้อตรง</small>"),
        _was,
        form,
    ])
    return cid, form, qid


@app.cell
def _(cands, cid, depth, form, mo, qid, reviewer, rnd, set_pos, set_saved):
    mo.stop(form.value is None)
    _v = form.value
    mo.stop(_v["rel"] is None, mo.callout("เลือกคะแนนก่อนบันทึก", kind="warn"))
    _first_time = (qid, cid) not in depth.human_grades([reviewer], rnd)
    depth.save_depth_label(reviewer, qid, cid, _v["rel"], _v["note"], rnd)
    set_saved(lambda n: n + 1)
    _next = depth.next_pending(cands, depth.human_grades([reviewer], rnd), (qid, cid)) if _first_time else None
    if _next:  # a first grade moves on to the next chunk to grade; changing an earlier grade stays where it is
        set_pos(_next)
    mo.callout(f"บันทึก {qid} (รอบ {rnd}) แล้ว" + (" · ไปชิ้นถัดไปที่ยังไม่ตรวจให้แล้ว (ย้อนกลับได้)" if _next else ""), kind="success")
    return


if __name__ == "__main__":
    app.run()
