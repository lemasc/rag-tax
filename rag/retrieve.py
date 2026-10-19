"""Retrieval over the chunk indexes: dense, sparse (BM25) and hybrid (reciprocal rank fusion).

RRF: score(d) = sum over rankings r of 1 / (RRF_K + rank_r(d)), ranks from 1. It uses ranks only, so the cosine
and BM25 scales never need calibrating against each other. RRF_K = 60 is the value from Cormack et al. (2009);
it damps the difference between the very top ranks so one ranking cannot dominate.

Run: uv run python -m rag.retrieve "ลดหย่อนบิดามารดาได้เท่าไร" [--mode dense|sparse|hybrid] [-k 5]
"""

import argparse
import json

import numpy as np

from rag.chunk import OUT, read_jsonl
from rag.index import DEFAULT_MODEL, dense_path, embed, load_model
from rag.sparse import BM25, tokenize

MODES = ("dense", "sparse", "hybrid")
RRF_K = 60
DEPTH = 50  # candidates taken from each ranking before fusion


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, i in enumerate(ranking, 1):
            scores[i] = scores.get(i, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


def top(scores: np.ndarray, k: int) -> list[int]:
    k = min(k, len(scores))
    idx = np.argpartition(-scores, k - 1)[:k]
    return idx[np.argsort(-scores[idx])].tolist()


class Retriever:
    def __init__(self, model: str = DEFAULT_MODEL, device: str | None = None):
        self.chunks = read_jsonl(OUT / "chunks.jsonl")
        ids = [c["chunk_id"] for c in self.chunks]
        toks = read_jsonl(OUT / "sparse_tokens.jsonl")
        dense = np.load(dense_path(model))
        if [t["chunk_id"] for t in toks] != ids or dense["ids"].tolist() != ids:
            raise SystemExit("indexes do not match rag/out/chunks.jsonl: run `python -m rag.index`")
        self.bm25 = BM25([t["tokens"] for t in toks])
        self.emb = dense["emb"]
        self.model_name, self.model = model, load_model(model, device)

    def dense_scores(self, query: str) -> np.ndarray:
        return self.emb @ embed(self.model, self.model_name, [query], query=True)[0]

    def sparse_scores(self, query: str) -> np.ndarray:
        return self.bm25.scores(tokenize(query))

    def search(self, query: str, mode: str = "hybrid", k: int = 5) -> list[dict]:
        if mode == "dense":
            s = self.dense_scores(query)
            hits = [(i, float(s[i])) for i in top(s, k)]
        elif mode == "sparse":
            s = self.sparse_scores(query)
            hits = [(i, float(s[i])) for i in top(s, k) if s[i] > 0]
        elif mode == "hybrid":
            s = self.sparse_scores(query)
            sparse_rank = [i for i in top(s, DEPTH) if s[i] > 0]
            hits = rrf([top(self.dense_scores(query), DEPTH), sparse_rank])[:k]
        else:
            raise ValueError(f"mode must be one of {MODES}")
        return [self.chunks[i] | dict(rank=r, score=score) for r, (i, score) in enumerate(hits, 1)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--mode", choices=MODES, default="hybrid")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--json", action="store_true", help="print hits as JSON lines")
    a = ap.parse_args()
    for h in Retriever(a.model).search(a.query, a.mode, a.k):
        if a.json:
            print(json.dumps(h, ensure_ascii=False))
            continue
        print(f"#{h['rank']} {h['score']:.4f}  {h['chunk_id']}  [{h['kind']}, tax_year={h['tax_year'] or h['year']}]")
        print(f"   {h['header']}")
        print("   " + h["text"][:300].replace("\n", " ") + ("…" if len(h["text"]) > 300 else ""))


if __name__ == "__main__":
    main()
