# Model prices and run costs

Looked up 2026-10-23. Prices change; re-check before a large run. Tokens per call are measured from `rag/out/llm_cache`
(each cache file keeps the API's `usage`); the costs below are tokens times these prices, so they are estimates.

## Prices (USD per 1M tokens)

| Profile (`rag/models.toml`) | Model | Input | Cached input | Output |
|---|---|---|---|---|
| `judge` (OpenAI direct) | gpt-6-sol | 2.00 | 0.20 | 10.00 |
| `judge-sol-or` (OpenRouter) | openai/gpt-6-sol | 2.00 | 0.20 | 10.00 |
| `judge-haiku` | anthropic/claude-haiku-5.5 | 0.10 | 0.01 | 0.50 |
| `judge-deepseek` | deepseek/deepseek-v4.1-flash | 0.165 | 0.006 | 0.66 |
| `judge-gemini` (not in the panel) | google/gemini-3.8-flash | 0.825 | 0.0825 | 4.125 |
| `gpt-mini` | gpt-6-luna | 0.10 | 0.01 | 0.50 |
| (not used) | gpt-6-astra | 10.00 | 1.00 | 50.00 |

Sources:
- OpenRouter: `https://openrouter.ai/api/v1/models` (public JSON, `pricing` field). Its model pages show only EU in-region
  prices, which need a Business plan: do not use them.
- OpenAI: `https://developers.openai.com/api/docs/pricing`, standard short-context tier (up to 272K input tokens). It agrees
  with OpenRouter for sol and luna. `gpt-6-terra` is not listed there.
- OpenRouter may add a fee when credit is bought; it is not in these numbers.
- Reasoning tokens are billed as output. The cache read price applies only if the backend caches the prompt prefix; the
  estimates below ignore it.

## Measured tokens per call (before E2; from the cache)

| Profile | Calls | Mean input | Mean output | Note |
|---|---|---|---|---|
| judge (sol, OpenAI) | 1,279 | 3.3k | 0.3k | about 250 output tokens are reasoning |
| judge-sol-or | 136 | 3.6k | 0.3k | |
| judge-haiku | 1,321 | 6.7k | 1.1k | Thai takes about twice the tokens of sol's tokenizer |
| judge-deepseek | 1,321 | 3.1k | 2.6k | mostly reasoning; one call hit 131,072 output tokens |

By task on sol: chunk grading (10 chunks) 3.6k in / 0.3k out; rubric 3.3k / 0.5k; RAGAS verify 2.6k / 0.3k; RAGAS claim
extraction 0.4k / 0.3k; RAGAS answer relevance 0.3k / 0.2k. One scored answer is about 4 calls, 6.7k in / 1.3k out.

## Spent so far (all cached calls, including dev runs and the top-50 diagnostic)

| Profile | Cost |
|---|---|
| judge (sol, OpenAI) | $12.39 |
| judge-sol-or | $1.40 |
| judge-haiku | $1.60 |
| judge-deepseek | $2.93 |
| judge-gemini | $0.72 |
| gpt-mini | $0.02 |
| **Total** | **$19.07** |

## Estimates for the next rounds (panel of three judges)

| Round | Sol | Haiku | DeepSeek | Round total |
|---|---|---|---|---|
| E1 (done, for scale) | about $7 | about $0.9 | about $1.5 | about $9.5 |
| E2 (about 280 calls per judge) | about $1.3 | about $0.25 | about $0.55 | about $2.1 |
| E3 (3 variants, about 390 answers, about 1,400 calls per judge) | $9–10.5 | about $1.3 | about $2.8 | about $13–15, plus about $0.15 generation |
| E4 (about 500 answers) | $11.5–13.5 | about $1.7 | about $3.6 | about $17–19, plus generators (under $1, not priced) |

How they were made:
- Sol input and output tokens are scaled from the per-task numbers above (E3 about 2.3–2.6M in and 0.45–0.5M out). Haiku
  and DeepSeek reuse their measured tokens per call. The k = 10 variant adds input tokens, so E3 may run
  higher. E3 was first priced with 4 variants (about 520 answers); the neighbour variant was dropped after E2.
- Generator calls (E3: about 390 on luna) are under $1. E4's generators are priced when the list is fixed.
- DeepSeek's output share is the biggest uncertainty: its output tokens vary a lot per call. A `max_tokens` cap in
  `models.toml` bounds the worst case.
- Sol dominates the bill: about 70% of E3 and E4. Sol's share of E3 alone is above OpenRouter's daily limit of $8 (E2 notes):
  raise the limit or split sol over two days.
