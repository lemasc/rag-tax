# Generation and evaluation: plan

Status: draft 2026-10-19, order revised 2026-10-22; chunks frozen 2026-10-22 (next: qrels on the frozen chunk ids). Steps 1–2 built 2026-10-20 (`rag/llm.py`, `rag/models.toml`, `rag/questions.py`, dev subset in `rag/eval/dev_questions.txt`); model ids not set until keys exist. Follows `rag-baseline.md` (retrieval works: dense, sparse, hybrid). This plan adds answer generation, the evaluation harness and the first ablations. Each step lists what it produces and what would make it done.

## Inputs and constraints

- **Questions:** `rag/eval/tax-questions-pass-1.csv`, 369 questions, 20 categories, difficulty easy/medium/hard. No reference answers, no gold sources. No question names a tax year; 23 carry an amount.
  - Multi-turn: 12 questions in sets tagged `[รอบ n: ชุด X]`.
  - Behavioural, where retrieval is not the point: `โจทย์ข้อมูลไม่ครบ` (15, should ask back), `ความเข้าใจผิด` (15, should correct the premise), `นอกขอบเขต` (1, Q0369, also missing its difficulty). Q0369 (lottery) is treated as a normal question since 2026-10-23 (`KIND_OVERRIDES` in `rag/questions.py`): มาตรา 42(11) and the ภ.ง.ด.94 FAQ (`61549#018`) answer it, so no question is out of scope any more.
  - Thin corpus coverage: crypto (4 chunks), freelance (1), online selling and part-time (0).
- **Assignment:** at least 2 metrics from BERTScore, BLEU/ROUGE, LLM-as-Judge, RAGAS Faithfulness, RAGAS Answer Relevance; at least 2 system variants compared. Without reference answers, BERTScore and BLEU/ROUGE are out, so every answer metric needs an LLM judge.
- **Models:** an OpenAI key now; OpenRouter (or similar) later for variety. No local LLM for now (the Ollama install is broken); `OLLAMA_BASE_URL` stays as an option. All of them speak the OpenAI chat API. Embeddings stay local (bge-m3), so retrieval needs no API.

- **Thai-tuned providers** (each on its own endpoint, not through OpenRouter as far as we know; all unverified until a key is tried):
  - Typhoon (SCB 10X): own API, believed OpenAI-compatible at `api.opentyphoon.ai/v1`.
  - ThaiLLM (national programme, launched April 2026): OpenThaiGPT, Pathumma, Typhoon-S, THaLLE, 8B–30B, free API with rate limits. Sources disagree on OpenAI compatibility; LiteLLM is the fallback.
  - OpenThai 2.0 (iApp): a Qwen3.8-27B fine-tune, OpenAI-compatible, 30 requests/minute; the free period was announced to end 30 September 2026.
  - A Thai fine-tune next to its own base model on OpenRouter (OpenThai 2.0 vs Qwen3.8-27B) is the cleanest "does Thai tuning help" comparison: same size and architecture, only the tuning differs.

## Principles

- **The judge is fixed.** One judge panel (see *Judge panel*), one prompt version, for every variant. The judges should be a different family from the generators; changing any judge or the prompt invalidates earlier numbers.
- **Every result file records its configuration:** model ids as served, base URL, prompt version, retrieval mode, k, chunk file hash, date.
- **Cache every LLM call on disk** keyed by (model, messages, parameters), so re-runs and re-scoring are free and reproducible.
- **Iterate on a dev subset** (about 40 questions, stratified by category); run all 369 only for reported numbers.

## Steps

### 1. LLM client: `rag/llm.py`

One thin wrapper over the `openai` package. Backends come from `.env` (gitignored; `.env.example` lists the variables):

```
OPENAI_API_KEY=
OPENROUTER_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434/v1
```

Models are named profiles in `rag/models.toml` (`name -> backend, model id, parameters`), so a run says `--gen gpt-small --judge judge` and the profile file is the record of what those names meant. The wrapper does the disk cache, retries with backoff and token/cost logging, and supports JSON output for the judge.

Done when: the same call works against OpenAI and, once keys or networking exist, OpenRouter and Ollama, and a repeated call is served from the cache.

### 2. Question loader: `rag/questions.py`

Parses the CSV into `id, category, difficulty, text, set, turn, kind`, with `kind` = `normal | multi_turn | ask_back | misconception | out_of_scope`. It strips the `[รอบ n: ชุด X]` tag from the text. It defines the dev subset once (fixed seed) and saves it.

Multi-turn baseline: the retrieval query is the current turn plus the earlier turns' questions; the generator sees the earlier turns and its own earlier answers. Rewriting the query with an LLM is a later ablation.

### 3. Answer generation: `rag/answer.py`

Retrieve the top k chunks (default 5, hybrid) and build a Thai prompt with the chunks numbered `[1]..[k]`, each with its header, document kind and tax year or Gazette date. The instructions:

- Answer only from the context and cite `[n]`.
- If the context does not cover the question, say so; do not answer from memory.
- If the question lacks facts the answer depends on (income, status), ask for them.
- Correct a wrong premise.
- Say which tax year a figure comes from when the source has one.

The prompt is versioned (`PROMPT_VERSION`). Output: `rag/out/runs/<run_id>/answers.jsonl` (question, retrieved chunk ids and ranks, prompt version, answer, tokens, latency) and `config.json`.

Also a `demo.py` (CLI first, notebook later) that answers a typed question and shows the sources. The assignment requires a demo script.

Done when: the dev subset runs end to end with one generator, and the answers have been read by a person.

### 4. Retrieval labels: `rag/label.py` and a marimo notebook

Retrieval metrics need gold chunks, and the CSV has none.

- Sample about 60 non-behavioural questions, stratified by category.
- For each, pool the top 10 from dense and the top 10 from sparse (union, 10–20 chunks), shown in random order without the mode they came from.
- A person marks each chunk 2 (answers it), 1 (related, partial) or 0 (not relevant). Saved to `rag/eval/qrels.csv`.
- Metrics: recall@5, MRR@10, nDCG@10 per retrieval mode.
- Known bias: chunks that neither mode retrieves are never judged, so recall is relative to the pool. State it in the report.

Done when: the qrels exist and `python -m rag.evaluate --retrieval` prints the table for dense, sparse and hybrid.

### 5. Answer evaluation: `rag/evaluate.py`

| Metric | What it measures | How |
|---|---|---|
| RAGAS Faithfulness | share of the answer's claims supported by the retrieved context | Judge splits the answer into claims, then checks each against the context. |
| RAGAS Answer Relevance | whether the answer addresses the question | Judge writes questions the answer would answer; mean cosine similarity to the real question with bge-m3. |
| LLM-as-Judge (rubric) | overall usefulness, and the behaviour the question type calls for | One call with a fixed rubric: grounded, complete, asked back when it should, flagged the tax year. Scored 1–5 per item, with a short reason. |

Decision to make: use the `ragas` library or implement the two RAGAS metrics directly from the paper's definitions. The library carries the name the rubric uses; a direct implementation is about 100 lines, easier to explain in the Q&A, and does not depend on the library's version changes. Suggested: try the library first with the chosen judge; fall back to the direct version if it fights the OpenAI-compatible backends or Thai.

**Validate the judge:** a person grades about 30 answers with the same rubric, and the report gives the agreement (exact and within one point). Without this, "the judge said so" is the only evidence.

Behavioural questions are scored on behaviour only (did it ask back, correct the premise, decline), not on faithfulness to retrieved text.

### 6. Ablations

| Ablation | Variants | Measured by |
|---|---|---|
| Retrieval (required) | dense, sparse, hybrid | qrels metrics, then faithfulness and rubric with one fixed generator |
| Generator | a small open model (Qwen or Gemma, about 8B), a mid-size open model, a small GPT model | faithfulness, relevance, rubric; per category, especially calculation and behavioural |
| Later candidates | PIT scope filter on/off; chunk size 256 / 384 / 512 (needs qrels that survive re-chunking: chunk-id qrels do not); tax-year handling (prefer the newest source); a cross-encoder reranker; LLM query rewriting for multi-turn | as above |

Report per category, not only the mean: the corpus gaps (freelance, crypto) and the tax-year problem will show up as specific categories, which is the failure-analysis slide.

## Cost (rough)

- Generation: about 2.5K tokens in and 300 out per question (5 chunks of ~300 tokens plus instructions). 369 questions × 3 generators ≈ 1,100 calls ≈ 3M tokens.
- Judging: about 4 calls per answer (claims, verification, relevance, rubric) at ~3K tokens ≈ 13M tokens for the same 1,100 answers.
- About 15–20M tokens for one full round. Cheap at small-model prices; the judge's price dominates. Dev-subset runs are about a tenth of that, and the cache makes re-scoring free.

## Order

Done: `.env.example`, `llm.py`, `questions.py`; `answer.py` and `demo.py` on the dev subset; the labelling notebook and the human labels; `evaluate.py` and the judge panel; the per-document cap run; the top-50 diagnostic (verdict mixed, see *Top-50 diagnostic*).

Next (revised 2026-10-22, after the top-50 diagnostic). No tuning on the 13 miss questions: they are dev questions read closely, so a setting chosen to rescue them would look better than it is. What they suggest goes into the full-run ablations instead.

1. **Corpus fixes, as needed:** the cut chunk (Q0145's `558~002`) is fixed (2026-10-23): the image holding the current steps is now its own chunk, `558_0_web~001`, rank 2 for Q0145's wording in a hybrid check, not a result. Still open: sources for the corpus gaps if that is decided (see *Open decisions*).
2. **Settle chunking and write down why.** Done 2026-10-22: 2,069 chunks frozen (2,070 since 2026-10-23, one added chunk, no id moved) (`rag/chunks_freeze.json`, enforced by a test); the size argument is in `rag-baseline.md` (*Decisions*, *Frozen chunks*). The corpus was settled first on `feat/corpus-update-1`: clause splitter for legal instruments, the 2568 filling guides cut at their own numbering and tables, explicit table rewrites, guide duplicates dropped, amend/repeal metadata. 92 of the 155 labelled chunk ids survive with the same text; the other 63 are re-mapped in step 3.
3. **Qrels:** the panel's chunk grades as a first pass, with a person confirming each 2. The panel alone is too lenient on hard questions (people kept 25 of 132 of its 2s). Qrels are keyed by chunk id, which is why chunking is settled first; the round 1 and 2 labels of the top-50 diagnostic are kept for chunks whose text does not change (text hash).
4. **Full run, retrieval ablation:** dense, sparse, hybrid (required). A cross-encoder reranker and k = 10 as candidates, justified by 7 of 13 misses having an answering chunk at ranks 6–50.
5. **Generator ablation**, as planned.
6. **Failure analysis:** corpus gaps (Q0111 general mutual-fund gains, Q0145 documents for a first online filing), a likely wording mismatch (Q0223, a case for query rewriting), a generation failure with the answer in the top 5 (Q0272), and the category breakdown.

## Open decisions

- The generator list. The judge is decided (see *Judge panel*).
- `ragas` library or a direct implementation.
- Who labels the retrieval sample and grades the judge-validation sample, and how many questions each.
- Whether to add sources for the corpus gaps the top-50 diagnostic confirmed (Q0111, Q0145) or only report them. Adding them adds chunks and can shift ids, so it belongs in step 1, before chunking is settled and qrels are made.
- Whether to write reference answers for a small subset anyway. That would add BERTScore as a third metric, but it costs a person's time.

## Dev run 1 (2026-10-20)

`rag/out/runs/20261020-dev-gpt-mini-hybrid-k5-v1`: gpt-6-luna (reasoning low), hybrid, k = 5, prompt v1. 40 calls, 103K tokens in, 7K out, median 9.6 s per answer. Built with `answer.py` and `demo.py` (step 3); not yet read in full by a person.

- Every answer cites at least one source; no citation points outside the 5 sources.
- Behavioural questions behave: the ask-back questions ask for the missing facts, both misconceptions are corrected, the lottery question says the sources do not cover it (counted as correct then; Q0369 is now a normal question, so this was a retrieval miss).
- **One document fills all 5 slots.** Q0091 and Q0301 (foreign income) get five windows of ป.120/2545 (film crews); Q0327 gets five windows of ป.96/2543. ป.161/2566 and ป.162/2566 (foreign income, มาตรา 41 วรรคสอง), which answer Q0091, are in the corpus and not retrieved. A per-document cap on hits is a candidate fix and ablation.
- **Calculation questions get old worked examples** (2542–2543 withholding orders) instead of the current rate table, and the answer declines to compute. Tax-year handling again.
- The demo question on parents' allowance mixed the half-year ภ.ง.ด.94 amount (15,000) into the answer as if it were an older year's figure.

## Judge panel (2026-10-22)

Why a panel: on the 10 shared questions the four human reviewers agree exactly 57–66% of the time (grounded 62%, correct 58%, useful 57%, chunk relevance 66%), and rubric v2 did not change that. The single judge (`gpt-6-sol`) already agreed with the humans about as well as they agree with each other, so the panel is not for noise. It is for independence: the dev generator and the judge are both OpenAI, and one model cannot show its own family's bias. The panel is not ground truth; it is a judged reference validated against the human labels, and the report should say so.

**Backends.** OpenRouter for the panel and the open generators (one key, one call shape, cached by `llm.py`); direct only for Typhoon and OpenAI. OpenRouter can route a model id to different hosts, so the served model is recorded with every call. New accounts are limited to 20 requests a minute on some models (Gemini 3.8 Flash); a profile may set its own `rpm`, throttled per model.

**Bake-off.** Three candidates from other families scored the 40 dev answers under judge v2 (`rag/out/runs/<run>/judges/<profile>/`). Agreement with the 60 human answer labels made under rubric v2, exact:

| Judge | grounded | correct | useful | relevance | mean grounded / correct |
|---|---|---|---|---|---|
| gpt-6-sol | 72% | 67% | 70% | 65% | 1.68 / 1.73 |
| Haiku 5.5 | 73% | 48% | 70% | 66% | 1.77 / 1.55 |
| DeepSeek V4.1 Flash | 77% | 73% | 68% | 70% | 1.85 / 1.90 |
| Gemini 3.8 Flash | 78% (n=81, all labels) | 77% | 79% | 66% | 2.00 / 1.98 |
| **Panel: sol, Haiku, DeepSeek** | 78% | 72% | 70% | 69% | |

- Gemini is left out of the panel. Its mean is about 2.0 on grounded and correct: it gives nearly everything a 2, so its high agreement is leniency, and it cannot catch the old-figure cases `correct` exists for. It was only scored against all 81 labels, not the v2-only 60. It can come back as a fourth judge for flagging.
- Haiku is the strictest on `correct` (mean 1.55, 48% agreement); the median keeps it from dominating.
- All judges score higher than the humans on `correct` and `useful` (the panel about +0.2). Report it.
- With n = 60, differences of about 5 points are noise.
- Reasoning dominates the judges' output (DeepSeek 98% of 347K output tokens, about 2,100 per call). Left at the default: capping it changes the judge and means re-scoring and re-validating. Revisit if a full run is costly (about 9 times the dev run, so DeepSeek near 3M output tokens).

**Aggregation (`rag/panel.py`, no LLM calls).** Median of grounded, correct, useful and each chunk's relevance; majority of behaviour (a tie goes to the more severe value) and of tags; mean of faithfulness and answer relevance. An answer is contested when two judges are two points apart on grounded, correct or useful: 2 of 40 on the dev run (Q0318 and Q0327, both on grounded), and the ones to give to a person. At least three judges, all scored under the same judge version.

**Commands.**

```
uv run python -m rag.evaluate --judge judge-haiku      # one judge; judge-* profiles write to runs/<id>/judges/<profile>/
uv run python -m rag.panel --judges judge judge-haiku judge-deepseek
uv run python -m rag.evaluate --compare --judge panel  # against the human labels; v2 labels only
```

## Next pass: per-document cap

The dev run showed one document filling all five slots (Q0091, Q0301, Q0327; see *Dev run 1*). Do it as a new run, not in the judging work: a cap changes which chunks come back, so it produces new answers, and the human labels belong to the old ones.

1. Add a per-document cap to retrieval (a parameter in `retrieve.py`, off by default), try 2 hits per document.
2. Generate a dev run with it next to the baseline; the run id carries the setting.
3. Score both with the panel and compare faithfulness, answer relevance and the rubric, per category.
4. Re-label by hand only the questions whose retrieved chunks changed; the other answers still have valid labels.

## Top-50 diagnostic (2026-10-22)

Question: for the dev questions tagged `retrieval_miss`, is a chunk that answers them in the candidates, and if so where? `rag/depth.py`; the class definitions are in its docstring.

- **Questions:** the 13 content questions tagged `retrieval_miss` by a person or the panel on either dev run (Q0369, then out of scope, is left out), and 10 control questions the panel scored 2/2/2 with no tag (a seeded sample).
- **Pool:** every chunk the dense top 50 or the sparse top 50 found (the whole fused list, up to 100). Graded 0/1/2 by the three-judge panel in shuffled batches of 10, on the rubric's chunk-relevance scale.
- **Classes** by the hybrid rank of the best chunk graded 2: A 1-5, B 6-50, C 51+, D none.
- **Decided before the run:** if B and C together hold most of the miss questions, the next work is ranking (tax-year boost, reranker); if D holds most, it is the corpus and query wording; otherwise the report says mixed and the two are tried cheaply. 13 questions cannot tell a 7/6 split from a 6/7 one, so "most" means at least 9. Reported twice, a 2 meaning the panel median (lenient) and all three judges (strict); a conclusion that changes between the two is reported as unsure.
- **Checks:** each D question and a sample of B ones are read by hand (a keyword search of the corpus for D); the controls show how often a 2 sits outside the top 5 for questions that worked; the new grades of the five returned chunks are compared with the panel's earlier relevance for the same chunks.
- **Chunk ids:** the grades are keyed by chunk id with a text hash, so they survive the chunk fix only for chunks whose text does not change.
- **Cost:** about 1,950 pairs, 206 calls per judge.

**Human check (added after the first run).** On a hand read the panel's 2s were too lenient for the miss questions (the median grading gave A 9, B 4, D 0; the strict one A 6, B 7, D 0, and several of the "best" chunks did not answer the question). A person now grades, per miss question, the best-ranked chunk the panel median gave a 2, and the next (at most 3) only if that is not a 2: 13 decisions, more only when a chunk is rejected. `uv run marimo run rag/depth_review.py --token-password <password>`; labels in `rag/eval/labels/<name>/depth.csv`. The class of a question is then the hybrid rank of the first chunk a person graded 2, or D if none; the rule above applies to those classes. The panel's grade is not shown, so it cannot anchor the reviewer.

**Round 1 result (4 reviewers, median).** A 1 (Q0272), B 3 (Q0091 rank 9, Q0176 rank 7, Q0238 rank 32), C 0, D 9 (Q0078, Q0111, Q0145, Q0207, Q0213, Q0223, Q0240, Q0301, Q0329): corpus or wording under the rule, at exactly 9. Exact agreement between reviewers was low (11 of 34 chunks graded by more than one person, 32%), and Q0207 and Q0213 were split.

**Round 2 (added after round 1).** Round 1's D means "none of the first three panel 2s answers", not "nothing answers": on the D questions the panel gave a 2 to 2–17 chunks, and the rest were never read by a person. A keyword search over every chunk (terms per question, ignoring the retriever) also found chunks outside the pool. From that search Claude picked 8 chunks for 5 questions (`depth.ROUND2`): 7 panel 2s beyond round 1's three, and 1 outside the pool (Q0223 `63908#008`, below the top 50 of both rankings, which counts as C). Round 2 only reads chunks for questions round 1 left at D, so it can move a question out of D but never into it; Q0207 and Q0213 keep their round-1 grades. Unlike round 1, every reviewer grades every round-2 chunk (no stop at the first 2), so a disputed question is never left to one person's grade. Same notebook, round 2 selected by default; labels in `rag/eval/labels/<name>/depth_r2.csv`, round 1's files unchanged. The result will be reported both as round 1 alone and as both rounds together. Search found no answering chunk for Q0111 (general mutual-fund gains: only RMF/SSF and fund profit payouts) or Q0145 (no checklist of documents for a first online filing); those are the clearest corpus gaps.

**Round 2 result (4 reviewers, median, lower middle).** All four reviewers graded all 8 chunks. Four questions leave D: Q0329 (`5937#042`, section 63, rank 27, 2/2/2/2), Q0301 (`552~001`, the 180-day rule, rank 31, 2/2/2/2), Q0078 (`62149#005`, the ภ.ง.ด.90 filing threshold, rank 17, 2/2/2/0) and Q0240 (`553~001`, allowance is type-1 income, rank 44, 0/2/2/2). Q0223's chunk outside the pool got 0/2/2/1 and stays D. The second chunks of Q0078, Q0301 and Q0329 got a team 1 and change nothing. All four reviewers agreed on 2 of the 8 chunks.

| | A | B | C | D | Under the rule |
|---|---|---|---|---|---|
| Round 1 only | 1 | 3 | 0 | 9 | corpus or wording, exactly at 9 |
| Rounds 1 + 2 | 1 | 7 | 0 | 5 | mixed |

The verdict is **mixed** under every aggregation tried: a 2 needing all four reviewers gives D 7, B 5; one reviewer's 2 being enough gives D 4, B 7, C 1. Under the rule decided before the run, mixed means trying both directions cheaply.

**What it means.** For 7 of the 13 missed questions an answering chunk is in the candidates at ranks 6–50 (Q0091, Q0176, Q0238 from round 1; Q0078, Q0240, Q0301, Q0329 from round 2), so ranking work (a reranker, tax-year handling, a larger k) can reach them. Of the 5 D questions, Q0111 (general mutual-fund gains) and Q0145 (documents for a first online filing) are corpus gaps confirmed by the keyword search; Q0207 and Q0213 rest on split round-1 grades; Q0223 may be a wording mismatch the team did not accept. Q0272 (A) is a generation problem, not retrieval. The panel's chunk grades are not good enough on their own for qrels on hard questions (people kept 25 of 132 of its 2s in round 1); qrels built from it need a person's check.
