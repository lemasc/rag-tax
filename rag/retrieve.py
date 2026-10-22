"""Retrieval over the chunk indexes: dense, sparse (BM25) and hybrid (reciprocal rank fusion).

RRF: score(d) = sum over rankings r of 1 / (RRF_K + rank_r(d)), ranks from 1. It uses ranks only, so the cosine
and BM25 scales never need calibrating against each other. RRF_K = 60 is the value from Cormack et al. (2009);
it damps the difference between the very top ranks so one ranking cannot dominate.

Run: uv run python -m rag.retrieve "ลดหย่อนบิดามารดาได้เท่าไร" [--mode dense|sparse|hybrid] [-k 5] [--max-per-doc 2]
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


def cap_per_doc(ranking: list[int], doc_ids: list[str], cap: int) -> list[int]:
    """The ranking with at most `cap` chunks per document, the best-ranked ones kept and the order unchanged."""
    seen: dict[str, int] = {}
    kept = []
    for i in ranking:
        seen[doc_ids[i]] = seen.get(doc_ids[i], 0) + 1
        if seen[doc_ids[i]] <= cap:
            kept.append(i)
    return kept


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

    def search(self, query: str, mode: str = "hybrid", k: int = 5, max_per_doc: int | None = None) -> list[dict]:
        """The k best chunks. With `max_per_doc`, a document gives at most that many, so one document cannot fill every
        slot; the cap is applied to the ranking (the best DEPTH candidates) before the cut to k."""
        depth = DEPTH if max_per_doc else k
        doc_ids = [c["doc_id"] for c in self.chunks]
        if mode == "dense":
            s = self.dense_scores(query)
            ranking = top(s, max(depth, k))
            scored = {i: float(s[i]) for i in ranking}
        elif mode == "sparse":
            s = self.sparse_scores(query)
            ranking = [i for i in top(s, max(depth, k)) if s[i] > 0]
            scored = {i: float(s[i]) for i in ranking}
        elif mode == "hybrid":
            s = self.sparse_scores(query)
            sparse_rank = [i for i in top(s, DEPTH) if s[i] > 0]
            fused = rrf([top(self.dense_scores(query), DEPTH), sparse_rank])
            ranking, scored = [i for i, _ in fused], dict(fused)
        else:
            raise ValueError(f"mode must be one of {MODES}")
        if max_per_doc:
            ranking = cap_per_doc(ranking, doc_ids, max_per_doc)
        return [self.chunks[i] | dict(rank=r, score=scored[i]) for r, i in enumerate(ranking[:k], 1)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--mode", choices=MODES, default="hybrid")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--max-per-doc", type=int, help="at most this many chunks from one document")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--json", action="store_true", help="print hits as JSON lines")
    a = ap.parse_args()
    for h in Retriever(a.model).search(a.query, a.mode, a.k, a.max_per_doc):
        if a.json:
            print(json.dumps(h, ensure_ascii=False))
            continue
        print(f"#{h['rank']} {h['score']:.4f}  {h['chunk_id']}  [{h['kind']}, tax_year={h['tax_year'] or h['year']}]")
        print(f"   {h['header']}")
        print("   " + h["text"][:300].replace("\n", " ") + ("…" if len(h["text"]) > 300 else ""))


if __name__ == "__main__":
    main()
