import marimo

__generated_with = "0.25.1"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import pandas as pd

    OUT = Path("analysis/out")
    chunks = pd.read_json(OUT / "chunks.jsonl", lines=True).set_index("chunk_id")
    topics = pd.read_json(OUT / "topics.jsonl", lines=True)
    topics["text"] = topics.chunk_id.map(chunks.text)
    terms = json.loads((OUT / "topic_terms.json").read_text(encoding="utf-8"))

    # No Thai font is guaranteed on the machine, so plots use these English labels; tables keep the Thai originals.
    KIND_EN = {
        "กฎกระทรวง": "ministerial regulation",
        "คำสั่งกรมสรรพากร": "RD order",
        "ประกาศอธิบดี": "DG notification",
        "ประกาศกรมสรรพากร": "RD announcement",
        "ประกาศกระทรวงการคลัง": "MoF announcement",
        "พระราชกฤษฎีกา": "royal decree",
        "คำวินิจฉัย": "tribunal ruling",
    }
    topics["kind_en"] = topics.kind.replace(KIND_EN)

    return chunks, json, mo, pd, plt, terms, topics


@app.cell
def _(mo):
    mo.md(r"""
    # Topic viewer

    Provisional chunks (`analysis/chunks.py`), not final. Duplicates are removed (1,275 of 1,375 chunks).
    Findings so far: `docs/plans/topic-exploration.md`. Topic labels are top terms only, unreviewed.
    """)
    return


@app.cell
def _(mo):
    model = mo.ui.dropdown(
        {"Sparse: TF-IDF + NMF (k=16)": "sparse", "Dense: bge-m3 + KMeans (k=16)": "dense_km", "Dense: bge-m3 + UMAP + HDBSCAN": "dense_hdb"},
        value="Dense: bge-m3 + UMAP + HDBSCAN",
        label="Model",
    )
    model
    return (model,)


@app.cell
def _(model, pd, terms, topics):
    col = model.value
    tt = terms[col]

    def _summ(g):
        return pd.Series(
            {
                "chunks": len(g),
                "docs": g.doc_id.nunique(),
                "top doc share": round(g.doc_id.value_counts(normalize=True).iloc[0], 2),
                "mix": ", ".join(f"{k} {v}" for k, v in g.kind.value_counts().head(3).items()),
                "terms": " ".join(tt[str(g.name)][:8]),
            }
        )

    summary = topics.groupby(col)[["doc_id", "kind"]].apply(_summ).reset_index().rename(columns={col: "topic"})
    return col, summary, tt


@app.cell
def _(col, mo, plt, topics):
    fig, ax = plt.subplots(figsize=(8, 6))
    _noise = topics[col] == -1
    ax.scatter(topics.x[_noise], topics.y[_noise], s=6, c="#cccccc", label="noise")
    sc = ax.scatter(topics.x[~_noise], topics.y[~_noise], s=7, c=topics[col][~_noise], cmap="tab20")
    ax.set_title(f"UMAP 2-d of bge-m3 embeddings, coloured by {col}")
    ax.set_xticks([]), ax.set_yticks([])
    mo.hstack([ax, mo.md("Position always comes from the dense embeddings. Colours change with the model chosen, so colour = which topic *that* model gave the chunk. Compare sparse and dense colourings to see where they disagree.")], widths=[2, 1])
    return


@app.cell
def _(mo, summary):
    mo.vstack([mo.md("## Topics"), mo.ui.table(summary, selection=None, page_size=50)])
    return


@app.cell
def _(col, mo, pd, plt, topics):
    _ct = pd.crosstab(topics[col], topics.kind_en)
    _fig, _ax = plt.subplots(figsize=(9, max(4, 0.22 * len(_ct))))
    _im = _ax.imshow(_ct.div(_ct.sum(axis=1), axis=0).values, aspect="auto", cmap="Blues")
    _ax.set_xticks(range(len(_ct.columns)), _ct.columns, rotation=60, ha="right", fontsize=7)
    _ax.set_yticks(range(len(_ct.index)), _ct.index, fontsize=7)
    _ax.set_title("Share of each topic by document kind (rows sum to 1)")
    mo.vstack([mo.md("## Source mix per topic"), _ax])
    return


@app.cell
def _(col, mo, topics):
    topic = mo.ui.dropdown(sorted(topics[col].unique().tolist()), value=sorted(topics[col].unique().tolist())[0], label="Topic")
    n = mo.ui.slider(3, 30, value=8, label="chunks to show")
    mo.hstack([topic, n])
    return n, topic


@app.cell
def _(col, mo, n, terms, topic, topics):
    _g = topics[topics[col] == topic.value]
    _sample = _g.sample(min(n.value, len(_g)), random_state=0)
    mo.vstack(
        [
            mo.md(f"**{len(_g)} chunks, {_g.doc_id.nunique()} documents.** Terms: {' '.join(terms[col][str(topic.value)])}"),
            mo.ui.table(_sample[["chunk_id", "kind", "n_tokens", "title", "text"]], selection=None, page_size=n.value),
        ]
    )
    return


@app.cell
def _(mo, plt, topics):
    _fig, (_a, _b) = plt.subplots(1, 2, figsize=(11, 3.5))
    for _k, _g in topics.groupby("origin"):
        _a.hist(_g.n_tokens.clip(upper=700), bins=40, alpha=0.6, label=f"{_k} ({len(_g)})")
    _a.set_xlabel("bge-m3 tokens (clipped at 700)")
    _a.legend(fontsize=7)
    _a.set_title("Chunk length by origin")
    _c = topics.groupby("doc_id").size().sort_values(ascending=False)
    _b.plot(range(1, len(_c) + 1), _c.cumsum() / _c.sum())
    _b.set_xlabel("documents, largest first")
    _b.set_ylabel("share of chunks")
    _b.set_title("Concentration: few documents hold many chunks")
    mo.vstack([mo.md("## Length and balance"), _a.figure])
    return


@app.cell
def _(col, mo, pd, topics):
    _other = "sparse" if col != "sparse" else "dense_km"
    _x = pd.crosstab(topics[col], topics[_other])
    mo.vstack([mo.md(f"## Agreement: `{col}` (rows) vs `{_other}` (columns)\nCounts of chunks. A topic that concentrates in one column is found by both models; a spread-out row is a topic only one model separates."), mo.ui.table(_x.rename(columns=str).reset_index(), selection=None, page_size=50)])
    return


if __name__ == "__main__":
    app.run()
