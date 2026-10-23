# E1b: a cross-encoder reranker on dense's candidates

Status: done 2026-10-23. Plan: [`../../plans/ablation-plan-retrieval-context-generator.md`](../../plans/ablation-plan-retrieval-context-generator.md) (E1b). Code `rag/pooled.py --rerank` (tests in `rag/tests/test_pooled.py`), outputs `rag/out/pooled/` (`pool.jsonl`, `judgments/`, `summary-luna-or+haiku+deepseek.json`, `summary-haiku+deepseek.json`). Builds on [E1](../2026-10-23-e1-ranking-ablation/README.md) and the [judge swap](../2026-10-23-judge-swap/README.md).

**Question.** Does reading the question and the chunk together (a cross-encoder) rank answering chunks higher than comparing two separate vectors (bge-m3)?

**Setup**
- Variant `dense-rerank`: dense's top 50 for the retrieval query, reordered by `BAAI/bge-reranker-v2-m3` on the query and each chunk's header + body (the text dense embeds), top 10 kept. Same candidates as dense, so only the order changes.
- The reranker reorders a lot: its top 10 shares 4.8 chunks with dense's on average, its top 5 shares 2.1, and its first chunk is dense's first on 112 of 339 questions.
- Its top 10 brought 1,213 new pairs into E1's pool (7,018 → 8,231). Graded by the new panel (luna, haiku, DeepSeek) in the batches of E1, 330 calls per judge. Cost about $1 or less (not tallied).
- The pool grew, so every mode is re-scored on the larger pool: dense's nDCG@10 and recall@10 drop (.696 → .648, .682 → .532) because the pool now holds the reranker's 2s too. hit@5, precision@5 and MRR do not depend on the pool.
- The sol rule (fixed before the run): sol grades E1b only if the reranker − dense interval on hit@5 or nDCG@10 touches 0, or the haiku + DeepSeek check gives the other sign.

**Result** (339 questions, a 2 is the panel median; difference = reranker − dense, 95% bootstrap interval over questions)

| | hit@5 | precision@5 | MRR@10 | nDCG@10 | recall@10 |
|---|---|---|---|---|---|
| dense | .687 | .268 | .519 | .648 | .532 |
| hybrid | .658 | .247 | .486 | .615 | .487 |
| **dense + reranker** | **.794** | **.352** | **.597** | **.744** | **.703** |
| reranker − dense | +.106 [+.062, +.153] | +.083 [+.063, +.105] | +.078 [+.039, +.116] | +.096 [+.078, +.115] | +.172 [+.129, +.210] |

- Strict (all three say 2): reranker − dense hit@5 +.074 [+.029, +.118], nDCG@10 +.104 [+.083, +.125].
- Free check, haiku and DeepSeek alone (a 2 needs both): hit@5 +.115 [+.068, +.162], nDCG@10 +.094 [+.072, +.116]. Same sign and size.
- Without the 36 dev questions: hit@5 +.112 [+.066, +.158], nDCG@10 +.096.
- Reranker − hybrid: hit@5 +.136, nDCG@10 +.129, all outside the interval.
- By the sol rule: not borderline, so sol is not used. By the outcome table: **reranker above dense, beyond the interval: into E3.**

**Is the gain an artefact of grading the new chunks later?** The 1,213 new chunks were graded in their own batches (about 4 chunks a question, not E1's 10). If judges were more lenient there, the reranker would gain.
- The new chunks are 2 less often than the reranker's chunks that E1 had already graded: .242 vs .319 in its top 10, .272 vs .378 in its top 5. They are in line with dense's own top 10 and top 5 (.227, .268). No sign of extra leniency.
- Counting every new chunk as not a 2 (a floor, too pessimistic since a quarter of them are 2 at dense's own rate): hit@5 +.012 [−.029, +.053]. So part of the hit@5 gain comes from chunks dense ranked 11–50 and the reranker lifted, the rest from reordering chunks already in the pool.
- A direct control (re-grade new chunks mixed into E1-sized batches, about $0.3) was not run.

**Reading it**
- The mechanism: bge-m3 compares a question vector with a chunk vector made without the question, so a chunk on the right topic but the wrong rule (the lookalikes of E1: worked examples, neighbouring deduction rules) can sit as close as the answer. The cross-encoder reads both together and can tell which one states the rule asked about. It finds answering chunks dense had at ranks 11–50, which matches the dev diagnostic (7 of 13 misses had an answer at ranks 6–50).
- The gain is largest on recall@10 (+.17): the reranker's top 10 holds many more of the pool's answering chunks.

**Caveats**
- Panel grades, not human grades; lenient on hard questions in absolute terms (E1 notes). The comparison is the reliable part.
- The pool is the union of the modes' top 10s, so recall is relative to the pool; adding the reranker raised the bar for every mode.
- Chunks dense did not have in its top 50 are out of the reranker's reach; it cannot fix the 29 questions with no 2 in the pool.
- Run note: the run ended early once (the session moved); all grades but one were saved, and that one batch was graded on the next run.
