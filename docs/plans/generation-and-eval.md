# Generation and evaluation: plan

Status: draft 2026-10-19, not started. Follows `rag-baseline.md` (retrieval works: dense, sparse, hybrid). This plan adds answer generation, the evaluation harness and the first ablations. Each step lists what it produces and what would make it done.

## Inputs and constraints

- **Questions:** `tax-questions-pass-1.csv`, 369 questions, 20 categories, difficulty easy/medium/hard. No reference answers, no gold sources. No question names a tax year; 23 carry an amount.
  - Multi-turn: 12 questions in sets tagged `[รอบ n: ชุด X]`.
  - Behavioural, where retrieval is not the point: `โจทย์ข้อมูลไม่ครบ` (15, should ask back), `ความเข้าใจผิด` (15, should correct the premise), `นอกขอบเขต` (1, Q0369, also missing its difficulty).
  - Thin corpus coverage: crypto (4 chunks), freelance (1), online selling and part-time (0).
- **Assignment:** at least 2 metrics from BERTScore, BLEU/ROUGE, LLM-as-Judge, RAGAS Faithfulness, RAGAS Answer Relevance; at least 2 system variants compared. Without reference answers, BERTScore and BLEU/ROUGE are out, so every answer metric needs an LLM judge.
- **Models:** an OpenAI key now; OpenRouter (or similar) later for variety. No local LLM for now (the Ollama install is broken); `OLLAMA_BASE_URL` stays as an option. All of them speak the OpenAI chat API. Embeddings stay local (bge-m3), so retrieval needs no API.

- **Thai-tuned providers** (each on its own endpoint, not through OpenRouter as far as we know; all unverified until a key is tried):
  - Typhoon (SCB 10X): own API, believed OpenAI-compatible at `api.opentyphoon.ai/v1`.
  - ThaiLLM (national programme, launched April 2026): OpenThaiGPT, Pathumma, Typhoon-S, THaLLE, 8B–30B, free API with rate limits. Sources disagree on OpenAI compatibility; LiteLLM is the fallback.
  - OpenThai 2.0 (iApp): a Qwen3.8-27B fine-tune, OpenAI-compatible, 30 requests/minute; the free period was announced to end 30 September 2026.
  - A Thai fine-tune next to its own base model on OpenRouter (OpenThai 2.0 vs Qwen3.8-27B) is the cleanest "does Thai tuning help" comparison: same size and architecture, only the tuning differs.

## Principles

- **The judge is fixed.** One judge model, one prompt version, temperature 0, for every variant. It should be a different family from the generators and stronger than them. Changing it invalidates earlier numbers.
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
| Later candidates | PIT scope filter on/off; chunk size 256 / 384 / 512; tax-year handling (prefer the newest source); a cross-encoder reranker; LLM query rewriting for multi-turn | as above |

Report per category, not only the mean: the corpus gaps (freelance, crypto) and the tax-year problem will show up as specific categories, which is the failure-analysis slide.

## Cost (rough)

- Generation: about 2.5K tokens in and 300 out per question (5 chunks of ~300 tokens plus instructions). 369 questions × 3 generators ≈ 1,100 calls ≈ 3M tokens.
- Judging: about 4 calls per answer (claims, verification, relevance, rubric) at ~3K tokens ≈ 13M tokens for the same 1,100 answers.
- About 15–20M tokens for one full round. Cheap at small-model prices; the judge's price dominates. Dev-subset runs are about a tenth of that, and the cache makes re-scoring free.

## Order

1. `.env.example`, `llm.py`, `questions.py`.
2. `answer.py` and `demo.py` with the OpenAI key on the dev subset; read the answers.
3. The labelling notebook; a person labels the sample.
4. `evaluate.py`: retrieval metrics, then the three answer metrics; judge validation.
5. Full runs: the retrieval ablation, then the generator ablation once OpenRouter is set up.

## Open decisions

- Judge model (fixed for the project) and the generator list.
- `ragas` library or a direct implementation.
- Who labels the retrieval sample and grades the judge-validation sample, and how many questions each.
- Whether to write reference answers for a small subset anyway. That would add BERTScore as a third metric, but it costs a person's time.
