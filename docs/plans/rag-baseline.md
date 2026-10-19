# Retrieval baseline

Status: first build 2026-10-19; rebuilt the same day with the PIT scope filter. Code in `rag/`; run from the repo root.

```
uv run python -m rag.chunk     # crawler/data/clean -> rag/out/chunks.jsonl
uv run python -m rag.index     # -> rag/out/dense/BAAI__bge-m3.npz, rag/out/sparse_tokens.jsonl (both gitignored)
uv run python -m rag.retrieve "ลดหย่อนบิดามารดาได้เท่าไร" --mode hybrid -k 5
```

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Chunk unit | FAQ item / statute section whole when it fits; otherwise paragraphs packed to the limit | Keeps a question with its answer and a section with its clauses. Legal instruments have no `ข้อ` splitter yet (cleaning item 2), so they are windowed. |
| Size | cap 512 bge-m3 tokens (header included); windows target 384 | 597 of 605 FAQ units and 36 of 43 statute sections fit whole. Windows smaller than the cap hold one or two clauses, not a whole instrument. Provisional: chunk size is an ablation candidate. |
| Header | `title \| section \| unit title or label` embedded with each chunk; later parts of a split FAQ item also repeat its question | A window cut from the middle of a document otherwise has no subject. |
| Overlap | none | Baseline. |
| Exclusions | `include = false` documents and units (hubs, TOC, duplicate decisions) | `unit_decisions.csv` applied by the clean build. PIT scope filter on: legal documents labelled `non_pit` in `legal_scope.csv` are `include = false` (8 documents; see `pit-scope.md`). `mixed` and unlabelled documents stay in. |
| Dense model | `BAAI/bge-m3`, normalised, cosine | Multilingual with strong Thai, 8K context, runs on CPU (assignment requirement); indexing 1,241 chunks takes ~30 s. Other models index side by side (`--model`); e5 prefixes are handled. |
| Sparse | BM25 (k1 1.5, b 0.75), own implementation, PyThaiNLP newmm, no stopwords | Thai needs word segmentation; newmm keeps `100,000`, `ภ.ง.ด.`, `(1)` whole. IDF handles common words. |
| Hybrid | RRF, k = 60, 50 candidates per ranking | Rank-only fusion, no score calibration between cosine and BM25. |

## Current build

1,241 chunks from 164 documents: 544 FAQ, 63 statute, 634 windows. Tokens: median 247, p90 382, max 511; 15 units split; 9 chunks under 30 tokens. The first build (no scope filter) had 1,277 chunks from 172 documents: the 8 `non_pit` documents account for 36 windows. The smoke test below was run on that first build and not repeated.

Smoke test (6 hand-written questions, all three modes, not an evaluation): the right topic is in the top 5 for every question in every mode. What shows up already:

- **Tax year.** Allowance questions return the 2560–2563 FAQ pages first; the 2568 poster (`65908_0_lodyon68_update`) did not appear in any top 5. Answers built on these chunks will quote old limits.
- Sparse alone drifts on generic wording ("อัตราภาษี…ขั้นบันได" ranked an index page and rulings first); hybrid recovered the rate-table FAQ at rank 1.
- "Easy E-Receipt" retrieves the กฎกระทรวง (391/2566, 2568 instrument) with sparse and hybrid; dense alone put an FAQ first.

## Not done

- Generation (LLM, prompt, citations): generator not chosen yet.
- Evaluation harness: waits for the question CSV; retrieval metrics (recall@k, MRR) need gold sources in it.
- Tax-year handling, reranker: candidate ablations. The scope filter is on; the filter-off baseline is not kept in git, rebuild it by running the clean build with an empty `legal_scope.csv`.
