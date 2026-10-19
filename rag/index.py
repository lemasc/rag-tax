"""Build the retrieval indexes over rag/out/chunks.jsonl.

Dense : SentenceTransformers embeddings of header + body, L2-normalised (cosine = dot product).
        Default model BAAI/bge-m3: multilingual with strong Thai, 8K context, runs on CPU (GPU only makes indexing
        faster). Other models can be indexed side by side for an ablation; each gets its own file.
Sparse: newmm tokens of header + body, cached so BM25 can be built at load time in under a second.

Output: rag/out/dense/<model>.npz (ids, emb), rag/out/sparse_tokens.jsonl
Run   : uv run python -m rag.index [--model BAAI/bge-m3] [--device cpu]
"""

import argparse
import json
from pathlib import Path

import numpy as np

from rag.chunk import MAX_TOKENS, OUT, passage, read_jsonl
from rag.sparse import tokenize

DEFAULT_MODEL = "BAAI/bge-m3"
# Models trained with instruction prefixes need them on both sides; bge-m3 uses none.
PREFIXES = {
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}


def dense_path(model: str) -> Path:
    return OUT / "dense" / (model.replace("/", "__") + ".npz")


def load_model(model: str, device: str | None = None):
    import torch
    from sentence_transformers import SentenceTransformer

    m = SentenceTransformer(model, device=device or ("cuda" if torch.cuda.is_available() else "cpu"))
    m.max_seq_length = MAX_TOKENS + 8  # chunks are capped at MAX_TOKENS without special tokens
    return m


def embed(m, model: str, texts: list[str], query: bool) -> np.ndarray:
    prefix = PREFIXES.get(model, ("", ""))[0 if query else 1]
    return m.encode([prefix + t for t in texts], batch_size=16, normalize_embeddings=True, convert_to_numpy=True,
                    show_progress_bar=not query)


def main(model: str, device: str | None) -> None:
    chunks = read_jsonl(OUT / "chunks.jsonl")
    ids = np.array([c["chunk_id"] for c in chunks])
    assert len(set(ids)) == len(ids), "chunk_id must be unique"
    texts = [passage(c) for c in chunks]

    with (OUT / "sparse_tokens.jsonl").open("w", encoding="utf-8") as f:
        for c, t in zip(chunks, texts):
            f.write(json.dumps(dict(chunk_id=c["chunk_id"], tokens=tokenize(t)), ensure_ascii=False) + "\n")
    print(f"sparse: {len(chunks)} chunks tokenized")

    emb = embed(load_model(model, device), model, texts, query=False)
    dense_path(model).parent.mkdir(parents=True, exist_ok=True)
    np.savez(dense_path(model), ids=ids, emb=emb.astype(np.float32))
    print(f"dense : {emb.shape} -> {dense_path(model)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--device", default=None)
    a = ap.parse_args()
    main(a.model, a.device)
