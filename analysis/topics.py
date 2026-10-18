"""Sparse and dense topic models over the provisional chunks (non-duplicate rows only).

Sparse: PyThaiNLP newmm tokens -> TF-IDF -> NMF.
Dense : bge-m3 embeddings -> UMAP -> HDBSCAN (density, finds its own count) and KMeans (same k as NMF, for a like-for-like comparison).
Both are labelled with top terms: NMF by component weight, dense clusters by class-based TF-IDF (c-TF-IDF).

Input : analysis/out/chunks.jsonl
Output: analysis/out/topics.jsonl (one row per chunk with sparse/dense assignments), analysis/out/topic_terms.json, analysis/out/emb.npy
Run   : uv run python analysis/topics.py [--k 16]
"""

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
from pythainlp.corpus import thai_stopwords
from pythainlp.tokenize import word_tokenize
from sklearn.cluster import KMeans
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer

OUT = Path("analysis/out")
EMBEDDER = "BAAI/bge-m3"
THAI_WORD = re.compile(r"^[ก-๙]{2,}$|^[A-Za-z]{3,}$")  # drop digits, punctuation, single characters
# Boilerplate that every legal text carries and says nothing about the topic. Found by inspecting top terms of a first run.
EXTRA_STOP = {"ตาม", "แห่ง", "ซึ่ง", "ดังนี้", "ดังกล่าว", "ทั้งนี้", "ให้", "โดย", "ใน", "หรือ", "และ", "ของ", "ที่", "การ", "ความ"}


def tokenize(text: str) -> list[str]:
    stop = thai_stopwords() | EXTRA_STOP
    return [w for w in word_tokenize(text, engine="newmm", keep_whitespace=False) if THAI_WORD.match(w) and w not in stop]


def top_terms(weights: np.ndarray, vocab: np.ndarray, n: int = 10) -> list[str]:
    return vocab[np.argsort(weights)[::-1][:n]].tolist()


def c_tfidf(docs_by_class: dict[int, str], analyzer, n: int = 10) -> dict[int, list[str]]:
    """Class-based TF-IDF (BERTopic): all chunks of a cluster are one document."""
    labels = list(docs_by_class)
    cv = CountVectorizer(analyzer=analyzer)
    counts = cv.fit_transform([docs_by_class[c] for c in labels]).toarray().astype(float)
    tf = counts / counts.sum(axis=1, keepdims=True)
    idf = np.log(1 + counts.sum(axis=1).mean() / counts.sum(axis=0))  # BERTopic: average class size over the word's total count
    vocab = cv.get_feature_names_out()
    return {c: top_terms(tf[i] * idf, vocab, n) for i, c in enumerate(labels)}


def main(k: int) -> None:
    df = pd.read_json(OUT / "chunks.jsonl", lines=True)
    df = df[df.dup_of.isna()].reset_index(drop=True)
    print(f"{len(df)} chunks")

    toks = [tokenize(t) for t in df.text]
    analyzer = lambda s: s.split("\x00")  # noqa: E731 - tokens are pre-split
    joined = ["\x00".join(t) for t in toks]

    # ---- sparse
    tfidf = TfidfVectorizer(analyzer=analyzer, min_df=3, max_df=0.4, sublinear_tf=True)
    X = tfidf.fit_transform(joined)
    vocab = tfidf.get_feature_names_out()
    nmf = NMF(n_components=k, init="nndsvd", random_state=0, max_iter=600)
    W = nmf.fit_transform(X)
    df["sparse"] = W.argmax(axis=1)
    df["sparse_w"] = W.max(axis=1)
    terms = {"sparse": {int(i): top_terms(c, vocab) for i, c in enumerate(nmf.components_)}}

    # ---- dense
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDER, device="cuda")
    model.max_seq_length = 1024
    E = model.encode(df.text.tolist(), batch_size=16, normalize_embeddings=True, show_progress_bar=True)
    np.save(OUT / "emb.npy", E)
    df[["chunk_id"]].to_json(OUT / "emb_ids.jsonl", orient="records", lines=True)

    import hdbscan
    import umap

    U5 = umap.UMAP(n_components=5, n_neighbors=15, min_dist=0.0, metric="cosine", random_state=0).fit_transform(E)
    U2 = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1, metric="cosine", random_state=0).fit_transform(E)
    df["x"], df["y"] = U2[:, 0], U2[:, 1]
    df["dense_hdb"] = hdbscan.HDBSCAN(min_cluster_size=12, min_samples=5, cluster_selection_method="eom").fit_predict(U5)
    df["dense_km"] = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(E)

    for col in ("dense_hdb", "dense_km"):
        by_class = {int(c): "\x00".join(w for i in np.flatnonzero(df[col] == c) for w in toks[i]) for c in sorted(df[col].unique())}
        terms[col] = c_tfidf(by_class, analyzer)

    df.drop(columns=["text"]).to_json(OUT / "topics.jsonl", orient="records", lines=True, force_ascii=False)
    (OUT / "topic_terms.json").write_text(json.dumps(terms, ensure_ascii=False, indent=1), encoding="utf-8")
    print("hdbscan clusters:", df.dense_hdb.nunique() - (-1 in set(df.dense_hdb)), "noise:", int((df.dense_hdb == -1).sum()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=16)
    main(ap.parse_args().k)
