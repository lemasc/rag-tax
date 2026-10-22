"""rag.sparse and rag.retrieve: BM25 scoring, Thai tokenization, rank fusion."""

import numpy as np

from rag.retrieve import Retriever, cap_per_doc, rrf, top
from rag.sparse import BM25, tokenize


def test_tokenize_keeps_amounts_and_form_names_and_drops_punctuation():
    assert tokenize("ลดหย่อนได้ไม่เกิน 100,000 บาท (ภ.ง.ด.90)") == ["ลดหย่อน", "ได้", "ไม่", "เกิน", "100,000", "บาท", "ภ.ง.ด.", "90"]


def test_bm25_prefers_the_rare_matching_term():
    docs = [["ภาษี", "บุตร"], ["ภาษี", "บิดา"], ["ภาษี", "สามี"]]
    bm = BM25(docs)
    s = bm.scores(["ภาษี", "บิดา"])
    assert s.argmax() == 1 and s[0] == s[2] > 0
    assert bm.idf[bm.vocab["บิดา"]] > bm.idf[bm.vocab["ภาษี"]]
    assert not bm.scores(["ไม่มีในคลัง"]).any()


def test_bm25_matches_the_formula_on_one_term():
    bm = BM25([["a", "a", "b"], ["b"]], k1=1.5, b=0.75)
    idf = np.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
    tf, dl, avgdl = 2, 3, 2
    assert np.isclose(bm.scores(["a"])[0], idf * tf * 2.5 / (tf + 1.5 * (1 - 0.75 + 0.75 * dl / avgdl)))


def test_rrf_rewards_agreement_between_rankings():
    fused = rrf([[1, 2], [2, 3]], k=60)
    assert [i for i, _ in fused] == [2, 1, 3]  # 2 is found by both rankings, 1 and 3 by one each
    assert np.isclose(dict(fused)[2], 1 / 62 + 1 / 61)


def test_top_returns_highest_first():
    assert top(np.array([0.1, 0.9, 0.5, 0.7]), 3) == [1, 3, 2]


def test_cap_per_doc_keeps_the_best_chunks_of_each_document_in_order():
    docs = ["a", "a", "a", "b", "a", "c"]
    assert cap_per_doc([0, 1, 2, 3, 4, 5], docs, 2) == [0, 1, 3, 5]
    assert cap_per_doc([4, 3, 2, 1, 0], docs, 1) == [4, 3]  # the ranking decides which chunk of a document survives


def fake_retriever(doc_ids: list[str], dense: list[float]) -> Retriever:
    r = object.__new__(Retriever)
    r.chunks = [dict(chunk_id=f"{d}~{n}", doc_id=d) for n, d in enumerate(doc_ids)]
    r.dense_scores = lambda q: np.array(dense)
    return r


def test_search_cap_lets_other_documents_in_and_renumbers_ranks():
    r = fake_retriever(["a", "a", "a", "b", "c"], [0.9, 0.8, 0.7, 0.6, 0.5])
    assert [h["chunk_id"] for h in r.search("q", "dense", 3)] == ["a~0", "a~1", "a~2"]
    capped = r.search("q", "dense", 3, max_per_doc=1)
    assert [(h["rank"], h["chunk_id"], h["score"]) for h in capped] == [(1, "a~0", 0.9), (2, "b~3", 0.6), (3, "c~4", 0.5)]


def test_search_cap_returns_fewer_hits_when_the_documents_run_out():
    r = fake_retriever(["a", "a", "b"], [0.9, 0.8, 0.7])
    assert [h["doc_id"] for h in r.search("q", "dense", 5, max_per_doc=1)] == ["a", "b"]
