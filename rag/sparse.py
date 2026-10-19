"""Sparse retrieval: BM25 (Okapi) over PyThaiNLP newmm tokens.

Thai is written without spaces between words, so a word tokenizer is needed before any bag-of-words model. newmm
(dictionary maximal matching) keeps amounts ("100,000"), form names ("ภ.ง.ด.") and section numbers together. No
stopword list: BM25's IDF already gives near-zero weight to words found in most chunks.
"""

import re

import numpy as np
from pythainlp.tokenize import word_tokenize
from scipy import sparse

WORD = re.compile(r"[ก-๙A-Za-z0-9]")  # keep tokens with a letter or digit; drop whitespace and bare punctuation


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in word_tokenize(text, engine="newmm", keep_whitespace=False) if WORD.search(t)]


class BM25:
    """score(q, d) = sum over query terms t of idf(t) * tf(t,d) * (k1 + 1) / (tf(t,d) + k1 * (1 - b + b * |d| / avgdl)).

    The per-(term, chunk) weight does not depend on the query, so it is computed once into a sparse matrix and a
    query is scored by summing the columns of its terms."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.vocab: dict[str, int] = {}
        rows, cols = [], []
        for i, toks in enumerate(docs):
            for t in toks:
                rows.append(i)
                cols.append(self.vocab.setdefault(t, len(self.vocab)))
        tf = sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(docs), len(self.vocab)))
        tf.sum_duplicates()
        n = len(docs)
        df = np.bincount(tf.indices, minlength=len(self.vocab))
        self.idf = np.log(1 + (n - df + 0.5) / (df + 0.5))  # the "+1" keeps idf positive for very common terms
        dl = np.asarray(tf.sum(axis=1)).ravel()
        norm = k1 * (1 - b + b * dl / dl.mean())
        tf = tf.tocoo()
        w = self.idf[tf.col] * tf.data * (k1 + 1) / (tf.data + norm[tf.row])
        self.weights = sparse.csc_matrix((w, (tf.row, tf.col)), shape=tf.shape)

    def scores(self, query: list[str]) -> np.ndarray:
        ids = [self.vocab[t] for t in query if t in self.vocab]  # a repeated query term counts each time
        if not ids:
            return np.zeros(self.weights.shape[0])
        return np.asarray(self.weights[:, ids].sum(axis=1)).ravel()
