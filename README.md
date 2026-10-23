# rag-tax: RAG Q&A over Thai personal income tax

A retrieval-augmented question answering system for Thai personal income tax. It answers in Thai and cites the source passages.

- **Corpus:** 173 documents (Revenue Department FAQ pages, Royal Gazette instruments, rulings, filing guides), cleaned and frozen as 2,070 chunks.
- **Retrieval:** dense (`BAAI/bge-m3`), sparse (BM25 over `newmm` Thai words), hybrid (RRF), and dense + cross-encoder reranker (`bge-reranker-v2-m3`).
- **Generation:** OpenAI-compatible chat models, configured as named profiles in `rag/models.toml` (the E3 generator is `typhoon-v2.5-30b-a3b-instruct`).
- **Evaluation:** 369 questions in 20 categories. Retrieval is scored against LLM-panel chunk grades (hit@5, precision@5, MRR@10, nDCG@10, recall@10). Answers are scored with RAGAS faithfulness and answer relevance, and with a rubric LLM-as-Judge, using a three-model panel.

## Layout

| Path | Contents |
| --- | --- |
| `crawler/` | Crawl, extract, clean and split the sources into units (`crawler/README.md`). The cleaned output is committed in `crawler/data/`. |
| `rag/` | Chunking, indexes, retrieval, answer generation, evaluation, judge panel, ablation scripts, tests. |
| `analysis/` | Corpus exploration (topic modeling, token statistics). |
| `demo.py` | Chat demo with sources under each answer. |
| `docs/` | Plans, experiment write-ups (E1, E1b, E2, hybrid vs dense, judge swap), model prices. |
| `AI_AUDIT.md` | AI tool usage, prompt log and findings. |

## Setup

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/). The torch wheels in `pyproject.toml` target CUDA 12.6; edit `[tool.uv.sources]` for a different setup (CPU also works, just slower for indexing).

```bash
uv sync --group rag --group dev
cp .env.example .env             # then fill in keys, see below
uv run python -m rag.llm check   # which providers have a key
```

### `.env`

`.env` is gitignored. Each variable is the API key for one provider in `rag/models.toml`; leave unused ones empty.

| Variable | Needed for |
| --- | --- |
| `OPENAI_API_KEY` | Demo default generator (`gpt-mini`) and the `judge` profile. **Enough to run the demo.** |
| `TYPHOON_API_KEY` | The E3 generator (`typhoon`). |
| `OPENROUTER_API_KEY` | The other judges (`judge-haiku`, `judge-deepseek`). |
| `THAILLM_API_KEY`, `THAILLM_BASE_URL`, `IAPP_API_KEY` | Other Thai generators tried in development (optional). |
| `OLLAMA_BASE_URL` | Local Ollama server (optional, default `http://localhost:11434/v1`). |

Retrieval, indexing and the tests need no key; only answer generation and scoring call an LLM.

The chunks (`rag/out/chunks.jsonl`) are committed. The dense index (`rag/out/dense/`) is built locally, so run the index step once before the first demo or retrieval run (a few minutes on CPU; it downloads `bge-m3`):

```bash
uv run python -m rag.index
```

To rebuild the chunks as well, run the chunker first:

```bash
uv run python -m rag.chunk
uv run python -m rag.index
```

## Run the demo

```bash
uv run --group rag streamlit run demo.py
```

Pick the generator, retrieval mode (dense / sparse / hybrid / …) and k in the sidebar. Follow-up questions keep the conversation context.

## Reproduce the experiments

```bash
uv run python -m rag.answer --subset ablation --gen typhoon --mode dense   # generate answers (E3 baseline)
uv run python -m rag.evaluate                                              # score a run (per judge)
uv run python -m rag.panel --judges judge judge-haiku judge-deepseek       # median over the judge panel
uv run python -m rag.e3                                                    # E3 table -> rag/out/e3/table.md
uv run pytest                                                              # tests, including the chunk freeze check
```

### Results without re-running

Re-running needs the API keys above and costs money. The results we report are committed, so nothing needs re-running to check them:

- `rag/out/e3/table.md`: E3 end-to-end table.
- `rag/out/runs/`: generated answers and per-answer scores for each run.
- `rag/out/pooled/`, `rag/out/depth/`: LLM-panel chunk grades used for the retrieval metrics.
- `docs/experiments/`: write-ups and tables for E1, E1b, E2, hybrid vs dense and the judge swap.

LLM responses are cached locally in `rag/out/llm_cache/` (about 250 MB, gitignored and not submitted), so a re-run on a machine that has it is cheap; without it, a re-run calls the APIs again and may differ slightly. See the module docstrings in `rag/` for each script's options.
