# Retrieval baseline

Status: first build 2026-10-19; rebuilt the same day with the PIT scope filter. **Chunks frozen 2026-10-22** (see *Frozen chunks*). Code in `rag/`; run from the repo root.

```
uv run python -m rag.chunk     # crawler/data/clean -> rag/out/chunks.jsonl
uv run python -m rag.index     # -> rag/out/dense/BAAI__bge-m3.npz, rag/out/sparse_tokens.jsonl (both gitignored)
uv run python -m rag.retrieve "ลดหย่อนบิดามารดาได้เท่าไร" --mode hybrid -k 5
```

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Chunk unit | One structural unit per chunk when it fits: FAQ item, statute มาตรา, legal clause (`ข้อ`/`มาตรา`, or an `(N)` item of a long one), filling-guide section or table; otherwise paragraphs packed to the limit. Documents without units (articles, rulings) are windowed | Keeps a question with its answer, a clause with its items and a table with its header. Units are cut by the corpus' own structure in `crawler.clean.units`, so a chunk boundary is a boundary of the source. |
| Size | cap 512 bge-m3 tokens (header included); windows target 384; no merging of short units | The cap is set by the natural units, not by the model (bge-m3 takes 8,192): at 512, 1,587 of 1,661 included units stay whole (FAQ 522 of 530, clauses 863 of 885, guide sections 155 of 189, statute 36 of 43); the 74 that do not are long by nature (statute มาตรา 40/42/47, guide sections, annex forms) and are split at paragraphs with the header repeated. A larger cap would mostly merge already-whole units into fewer, less specific chunks; a smaller one would split many clauses mid-sentence. Windows target 384 so a window of an article or ruling holds one or two paragraphs. Short units are left alone: a 60-token clause such as `(15) การขนส่ง… ร้อยละ 60` answers its question exactly, and its header carries the context. Merging short units, or passing a hit's neighbours to the generator, are ablation candidates. |
| Header | `title \| section \| unit title or label` embedded with each chunk; later parts of a split FAQ item also repeat its question, later parts of a split table repeat its header row | A window cut from the middle of a document otherwise has no subject. |
| Overlap | none | Baseline. |
| Exclusions | `include = false` documents and units (hubs, TOC, duplicate decisions: 61065, 20 FAQ units, 62 filling-guide copies) | `unit_decisions.csv` applied by the clean build. PIT scope filter on: legal documents labelled `non_pit` in `legal_scope.csv` are `include = false` (8 documents; see `pit-scope.md`). `mixed` and unlabelled documents stay in. |
| Dense model | `BAAI/bge-m3`, normalised, cosine | Multilingual with strong Thai, 8K context, runs on CPU (assignment requirement); indexing 1,241 chunks takes ~30 s. Other models index side by side (`--model`); e5 prefixes are handled. |
| Sparse | BM25 (k1 1.5, b 0.75), own implementation, PyThaiNLP newmm, no stopwords | Thai needs word segmentation; newmm keeps `100,000`, `ภ.ง.ด.`, `(1)` whole. IDF handles common words. |
| Hybrid | RRF, k = 60, 50 candidates per ranking | Rank-only fusion, no score calibration between cosine and BM25. |

## Frozen chunks (2026-10-22)

`rag/out/chunks.jsonl`: 2,069 chunks from 172 documents, built from the corpus at `d821564` (`feat/corpus-update-1`). `rag/chunks_freeze.json` records its sha256 and the settings, and `rag/tests/test_chunk.py` fails if the file changes: qrels key on chunk ids, so the table changes only on purpose (regenerate, re-map the qrels, update the freeze).

| Origin | Chunks | Median tokens | p90 | Max | Under 50 |
|---|---|---|---|---|---|
| clause (legal instruments) | 909 | 148 | 334 | 509 | 6 |
| faq | 543 | 127 | 284 | 509 | 6 |
| window (documents without units) | 277 | 259 | 377 | 383 | 19 |
| guide (filling guides) | 252 | 288 | 495 | 512 | 0 |
| statute | 63 | 285 | 501 | 511 | 2 |
| annex | 19 | 465 | 507 | 509 | 0 |
| section (page 63437) | 6 | 269 | 378 | 378 | 0 |
| all | 2,069 | 168 | 383 | 512 | 33 |

Chunks carry the document's `flags`, so an instrument amended or repealed by a newer one in the corpus is marked (`amended`, `repealed`; `crawler/data/legal_relations.csv`). Labels carried over: of the 155 chunk ids labelled so far (`rag/eval/labels/*`), 92 keep the same id and text; the other 63 (mostly legal-instrument windows, now clauses) need re-mapping in the qrels step. The dense and sparse indexes were rebuilt from this table.

**Runs made with other chunks** (`rag/chunk_version.py`). Every run records the chunks it retrieved from (`retrieval.chunks_sha`), and `rag/chunks_freeze.json` lists the earlier versions with a commit that has them (`95bba22006ba` at `482191b`: both dev runs and the top-50 pool; `889c2cc8ce2c` at `8bfd02f`). Tools that compute from a run stop on a mismatch and name that commit: `rag.evaluate` (scoring) and `rag.depth` (pool, judging; `--report` reads saved judgments only and still runs). The notebooks open such a run read-only: `review.py` and `depth_review.py` show a warning and save no labels, chunks the current table lacks show as placeholders; `browse.py` warns that the chunk text may not be what the run retrieved. To work with an older run, check out that commit (the whole codebase) and run `python -m rag.index`. On the next re-freeze, the current version moves to `earlier` with the commit of this freeze.

## Earlier build (2026-10-19)

Superseded by the frozen chunks above. 1,241 chunks from 164 documents: 544 FAQ, 63 statute, 634 windows. Tokens: median 247, p90 382, max 511; 15 units split; 9 chunks under 30 tokens. The first build (no scope filter) had 1,277 chunks from 172 documents: the 8 `non_pit` documents account for 36 windows. The smoke test below was run on that first build and not repeated.

Smoke test (6 hand-written questions, all three modes, not an evaluation): the right topic is in the top 5 for every question in every mode. What shows up already:

- **Tax year.** Allowance questions return the 2560–2563 FAQ pages first; the 2568 poster (`65908_0_lodyon68_update`) did not appear in any top 5. Answers built on these chunks will quote old limits.
- Sparse alone drifts on generic wording ("อัตราภาษี…ขั้นบันได" ranked an index page and rulings first); hybrid recovered the rate-table FAQ at rank 1.
- "Easy E-Receipt" retrieves the กฎกระทรวง (391/2566, 2568 instrument) with sparse and hybrid; dense alone put an FAQ first.

## Not done

- Generation (LLM, prompt, citations): generator not chosen yet.
- Evaluation harness: waits for the question CSV; retrieval metrics (recall@k, MRR) need gold sources in it.
- Tax-year handling, reranker: candidate ablations. The scope filter is on; the filter-off baseline is not kept in git, rebuild it by running the clean build with an empty `legal_scope.csv`.
