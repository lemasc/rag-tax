import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full", app_title="E1: ตรวจ chunk และคะแนน LLM")


@app.cell
def _():
    """Read-only view of the E1 ranking ablation (rag/pooled.py): per question, the chunks dense, sparse and hybrid ranked,
    what each of the three judges and the panel graded them, and the failure cases (a mode that finds a 2 in its top 5
    where another does not, questions with no 2 anywhere, chunks the judges disagree on). Nothing is saved from here.

    Needs rag/out/pooled/pool.jsonl and judgments/ (uv run python -m rag.pooled).
    Run: uv run marimo edit rag/pooled_browse.py
    """
    import html
    import sys
    from pathlib import Path

    import marimo as mo

    ROOT = Path(__file__).parent.parent
    sys.path.insert(0, str(ROOT))
    from rag import chunk_version, pooled
    from rag.answer import KIND_TH, year_label
    from rag.chunk import OUT as CHUNKS, read_jsonl

    return CHUNKS, KIND_TH, chunk_version, html, mo, pooled, read_jsonl, year_label


@app.cell
def _(CHUNKS, chunk_version, mo, pooled, read_jsonl):
    import json as _json

    JUDGES = {"sol": "judge-sol-or", "haiku": "judge-haiku", "deepseek": "judge-deepseek"}  # the panel of the E1 report
    mo.stop(not (pooled.OUT / "pool.jsonl").exists(), mo.callout("ยังไม่มี pool: uv run python -m rag.pooled", kind="warn"))
    items = read_jsonl(pooled.OUT / "pool.jsonl")
    by_id = {it["id"]: it for it in items}
    chunks = {c["chunk_id"]: c for c in read_jsonl(CHUNKS / "chunks.jsonl")}
    per_judge = {n: read_jsonl(pooled.OUT / "judgments" / f"{f}.jsonl") for n, f in JUDGES.items()
                 if (pooled.OUT / "judgments" / f"{f}.jsonl").exists()}
    mo.stop(len(per_judge) < 3, mo.callout(f"ต้องมี judge ครบ 3 คน (มี {', '.join(per_judge) or 'ไม่มี'})", kind="warn"))
    by_judge = pooled.judge_grades(per_judge, items)
    _sha = _json.loads((pooled.OUT / "pool_config.json").read_text(encoding="utf-8"))["chunks_sha"]
    _problem = chunk_version.problem(_sha, "the pool")
    n_missing = sum(len(it["pool"]) for it in items) - min(len(g) for g in by_judge.values())
    mo.vstack([
        mo.md("## E1: dense / sparse / hybrid — ตรวจ chunk, คะแนนของ judge และ failure case"),
        mo.callout(mo.md(f"**chunk ไม่ตรงกับตอนสร้าง pool**: ข้อความ chunk ที่แสดงอาจเป็นคนละเวอร์ชัน\n\n{_problem}"), kind="warn") if _problem else mo.md(""),
        mo.callout(f"มี {n_missing} คู่ที่ judge บางคนยังไม่ได้ให้คะแนน: รัน `uv run python -m rag.pooled` ให้ครบก่อน", kind="warn") if n_missing else mo.md(""),
        mo.md(f"{len(items)} คำถาม · {sum(len(it['pool']) for it in items)} คู่ (คำถาม, chunk) · judge: {', '.join(per_judge)} · "
              f"top {pooled.TOP} ของแต่ละโหมดรวมเป็น pool"),
    ])
    return by_id, by_judge, chunks, items, per_judge


@app.cell
def _(mo):
    strict = mo.ui.switch(label="เข้มงวด: เป็น 2 เมื่อทั้ง 3 judge ให้ 2 (ปิด = มัธยฐานของ panel)")
    strict
    return (strict,)


@app.cell
def _(items, per_judge, pooled, strict):
    grades = pooled.panel_grades(per_judge, items, strict.value)
    by_q = pooled.metrics_by_question(items, grades)
    return by_q, grades


@app.cell
def _(by_q, items, mo, pooled):
    _fields = list(next(iter(by_q["dense"].values())))
    _rows = [{"โหมด": m, **{f: round(pooled.mean_of([by_q[m][it["id"]][f] for it in items]), 3) for f in _fields}} for m in pooled.MODES]
    _diff = []
    for _a, _b in (("hybrid", "dense"), ("hybrid", "sparse"), ("dense", "sparse")):
        _row = {"ต่าง": f"{_a} − {_b}"}
        for _f in _fields:
            _d = pooled.paired_difference({it["id"]: by_q[_a][it["id"]][_f] for it in items}, {it["id"]: by_q[_b][it["id"]][_f] for it in items})
            _row[_f] = f"{_d['mean']:+.3f} [{_d['lo']:+.3f}, {_d['hi']:+.3f}]" + ("" if _d["lo"] <= 0 <= _d["hi"] else " *")
        _diff.append(_row)
    _cat = []
    for _c in sorted({it["category"] for it in items}):
        _ids = [it["id"] for it in items if it["category"] == _c]
        _cat.append({"หมวด": _c, "n": len(_ids), **{f"{m} {f}": round(pooled.mean_of([by_q[m][q][f] for q in _ids]), 2)
                                                   for f in ("hit5", "ndcg10") for m in pooled.MODES}})
    mo.vstack([
        mo.md("#### ทุกคำถาม"), mo.ui.table(_rows, selection=None),
        mo.md("ผลต่างของค่าเฉลี่ย (จับคู่ตามคำถาม) พร้อมช่วง 95% จาก bootstrap; `*` = ช่วงไม่คร่อม 0"), mo.ui.table(_diff, selection=None),
        mo.accordion({"ตามหมวด (n เล็ก: ใช้เป็นเบาะแส ไม่ใช่ผล)": mo.ui.table(_cat, selection=None, page_size=20)}),
    ])
    return


@app.cell
def _(grades, items, mo, pooled):
    _cls = [pooled.compare_modes(it, grades) for it in items]
    _n = {k: _cls.count(k) for k in ("both", "dense only", "hybrid only", "neither", "no 2 in pool")}
    _src = pooled.hybrid_top5_sources(items, grades)
    _src_rows = [{"chunk ใน top 5 ของ hybrid ที่พบโดย": k, "จำนวนช่อง": len(v),
                  "ได้ 2": round(sum(g == 2 for g in v) / len(v), 2) if v else None,
                  "ได้ 1": round(sum(g == 1 for g in v) / len(v), 2) if v else None,
                  "ได้ 0": round(sum(g == 0 for g in v) / len(v), 2) if v else None} for k, v in _src.items()]
    mo.vstack([
        mo.md("#### Failure case: dense เทียบกับ hybrid (มี 2 ใน top 5 หรือไม่)"),
        mo.md(f"ทั้งคู่ **{_n['both']}** · dense อย่างเดียว **{_n['dense only']}** · hybrid อย่างเดียว **{_n['hybrid only']}** · "
              f"ไม่มีโหมดไหนพบ **{_n['neither']}** · ไม่มี 2 ใน pool เลย **{_n['no 2 in pool']}** (corpus หรือถ้อยคำไม่ตรง ไม่ใช่เรื่อง ranking)"),
        mo.md("hybrid ใช้ช่อง top 5 กับ chunk ที่แต่ละ ranking พบ ได้คะแนนอย่างไร (RRF ให้คะแนนสูงกับ chunk ที่ทั้งสอง ranking พบ):"),
        mo.ui.table(_src_rows, selection=None),
    ])
    return


@app.cell
def _(items, mo):
    f_cat = mo.ui.dropdown(["(ทั้งหมด)"] + sorted({it["category"] for it in items}), value="(ทั้งหมด)", label="หมวด")
    f_case = mo.ui.dropdown(
        ["(ทั้งหมด)", "dense only", "hybrid only", "neither", "no 2 in pool", "มี chunk ที่ judge ให้ห่างกัน 2 คะแนน"],
        value="(ทั้งหมด)", label="กรณี (dense เทียบ hybrid)")
    f_dev = mo.ui.dropdown(["(ทั้งหมด)", "เฉพาะ dev", "ไม่รวม dev"], value="(ทั้งหมด)", label="dev")
    mo.hstack([f_cat, f_case, f_dev], justify="start")
    return f_case, f_cat, f_dev


@app.cell
def _(by_judge, f_case, f_cat, f_dev, grades, items, mo, pooled):
    _rows = []
    for _it in items:
        _case = pooled.compare_modes(_it, grades)
        _bad = pooled.contested(_it, by_judge)
        if f_cat.value != "(ทั้งหมด)" and _it["category"] != f_cat.value:
            continue
        if f_dev.value == "เฉพาะ dev" and not _it["dev"] or f_dev.value == "ไม่รวม dev" and _it["dev"]:
            continue
        if f_case.value == "มี chunk ที่ judge ให้ห่างกัน 2 คะแนน":
            if not _bad:
                continue
        elif f_case.value != "(ทั้งหมด)" and _case != f_case.value:
            continue
        _g = grades[_it["id"]]
        _rows.append({
            "id": _it["id"], "หมวด": _it["category"], "คำถาม": _it["question"][:50], "กรณี": _case, "dev": "✓" if _it["dev"] else "",
            "2 ใน pool": sum(v == 2 for v in _g.values()), "pool": len(_g), "judge ขัดกัน": len(_bad),
            **{f"{m} 2@5": sum(_g[c] == 2 for c in _it["rankings"][m][:5]) for m in pooled.MODES},
        })
    table = mo.ui.table(_rows, selection="single", page_size=15, label=f"{len(_rows)} ข้อ (เลือกแถวเพื่อดู chunk และคะแนนของแต่ละ judge)")
    table
    return (table,)


@app.cell
def _(mo, table):
    mo.stop(not table.value, mo.callout("เลือกแถวในตารางเพื่อดูรายละเอียด", kind="info"))
    qid = table.value[0]["id"]
    return (qid,)


@app.cell
def _(KIND_TH, by_id, by_judge, chunks, grades, html, mo, pooled, qid, strict, year_label):
    _it = by_id[qid]
    _g = grades[qid]
    _case = pooled.compare_modes(_it, grades)
    _contested = set(pooled.contested(_it, by_judge))

    def _esc(t):
        return html.escape(t).replace("\n", "<br>")

    def _rank(m, c):
        r = _it["rankings"][m]
        return r.index(c) + 1 if c in r else None

    _order = sorted((e["chunk_id"] for e in _it["pool"]),
                    key=lambda c: min(_rank(m, c) or 99 for m in pooled.MODES) * 100 + sum(_rank(m, c) or 99 for m in pooled.MODES) / 3)
    _table = []
    for _c in _order:
        _ch = chunks.get(_c, {})
        _table.append({
            "dense": _rank("dense", _c), "sparse": _rank("sparse", _c), "hybrid": _rank("hybrid", _c),
            "panel": _g[_c], **{j: by_judge[j][qid, _c] for j in by_judge}, "ขัดกัน": "⚠" if _c in _contested else "",
            "chunk": _c, "header": _ch.get("header", "(ไม่มีใน chunks.jsonl)")[:70],
        })

    # why a mode lost: where the best 2 of the winning mode sits in the other rankings, and what took the top 5
    _why = mo.md("")
    if _case in ("dense only", "hybrid only"):
        _win, _lose = ("dense", "hybrid") if _case == "dense only" else ("hybrid", "dense")
        _best = next(c for c in _it["rankings"][_win][:5] if _g[c] == 2)
        _others = [m for m in pooled.MODES if m != _win]
        _pos = ", ".join(f"{m}: {'อันดับ ' + str(_rank(m, _best)) if _rank(m, _best) else 'ไม่อยู่ใน top ' + str(pooled.TOP)}" for m in _others)
        _top5 = [_g[c] for c in _it["rankings"][_lose][:5]]
        _why = mo.callout(mo.md(
            f"**{_win} พบ 2 ใน top 5 แต่ {_lose} ไม่พบ.** chunk `{_best}` อยู่ที่ {_win} อันดับ {_rank(_win, _best)}; ที่โหมดอื่น: {_pos}. "
            f"คะแนนของ top 5 ใน {_lose}: {_top5}"), kind="warn")
    elif _case == "no 2 in pool":
        _why = mo.callout("ไม่มี chunk ใดใน pool ที่ panel ให้ 2: อ่าน chunk ด้านล่างว่า corpus ขาดคำตอบ หรือถ้อยคำคำถามไม่ตรง", kind="danger")

    _it_q = [mo.md(f"**รอบก่อนหน้า:** {t}") for t in _it["earlier"]]
    _src = {}
    for _row in _table:
        _ch = chunks.get(_row["chunk"], {})
        _ranks = " ".join(f"{m[0]}{_row[m]}" for m in pooled.MODES if _row[m])
        _title = f"{_ranks:14s} panel {_row['panel']} ({'/'.join(str(_row[j]) for j in by_judge)}){' ⚠' if _row['ขัดกัน'] else ''} — {_row['header'][:60]}"
        _meta = f"{KIND_TH.get(_ch.get('kind'), _ch.get('kind', '?'))} · {year_label(_ch) if _ch else '?'} · {_row['chunk']}"
        _src[_title] = mo.Html(f"<small>{html.escape(_meta)}</small><div style='font-size:0.9em;margin-top:0.4em'>{_esc(_ch.get('text', ''))}</div>")

    mo.vstack([
        mo.md(f"### {qid} · {_it['category']} · {_it['kind']}{' · dev' if _it['dev'] else ''}"),
        *_it_q,
        mo.md(f"**คำถาม:** {_it['question']}"),
        mo.md(f"query ที่ใช้ค้น: `{_it['query'][:200]}`") if _it["earlier"] else mo.md(""),
        mo.md(f"กรณี: **{_case}** · panel ({'เข้มงวด' if strict.value else 'มัธยฐาน'}) · "
              f"คอลัมน์ dense/sparse/hybrid = อันดับใน top {pooled.TOP} ของโหมดนั้น ('None' = ไม่อยู่ใน top {pooled.TOP}); "
              f"คะแนน {'/'.join(by_judge)} = ของแต่ละ judge; ⚠ = มีคนให้ 2 และอีกคนให้ 0"),
        _why,
        mo.ui.table(_table, selection=None, page_size=25),
        mo.md("#### ข้อความ chunk (เรียงตามอันดับที่ดีที่สุดของโหมดใดๆ; d=dense, s=sparse, h=hybrid)"),
        mo.accordion(_src),
    ])
    return


if __name__ == "__main__":
    app.run()
