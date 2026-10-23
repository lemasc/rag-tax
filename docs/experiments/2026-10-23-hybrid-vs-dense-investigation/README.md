# Investigation: why hybrid does not beat dense

Status: done 2026-10-23; the E3 baseline decision at the end is confirmed (dense), and the plan's Log has a summary. Follows [E1](../2026-10-23-e1-ranking-ablation/README.md). Scratch scripts for the tests live outside the repo; nothing in the frozen chunks changed.

Entries are in the order they were done. Here "k" (RRF_K, "hybrid k = 10") is the RRF fusion constant, not the number of chunks the generator sees (the "k = 10" of E3 in the plan).


## Pending investigation: why hybrid does not beat dense (not run)

Dense-wins cases read: Q0021, Q0057, Q0062, Q0065, Q0106 (first lines of the chunks only), plus the retriever code.

**Cause 1, structural (checked on all 339 queries)**
- With RRF_K = 60 and DEPTH = 50, hybrid ranks every chunk both lists found above every chunk only one found. The best a single list gives is 1/61 = 0.0164; the least a both-lists chunk gives is 2/110 = 0.0182.
- 0 cases in 339 where a one-list chunk outranks a both-lists chunk. On average 96% of hybrid's top 5 are both-lists chunks (33 questions have fewer than 5, where one-list chunks enter).
- So a chunk dense ranks 1st is lost whenever BM25 has it below its top 50 and five other chunks overlap. A k below about 48 makes rank count again.

**Cause 2, lookalikes (5 cases read)**
- The chunks both rankings share and hybrid puts first are lookalikes graded 1: worked examples with the same numbers (Q0021, คำสั่ง ป.96/2543), neighbouring deduction rules (Q0057, Q0062), other clauses of one decree (Q0106).

**Lead 3, chunking (untested)**
- Every clause chunk of a decree carries the decree's title in its header. For Q0106 the title contains the query word (คริปโทเคอร์เรนซี), so all of the decree's clauses match it. Whether the header text is the cause is not checked.

**Limits**
- 5 of the 30 dense-wins read; the k effect is arithmetic plus the 0/339 check, not a measured gain.

**Planned variant: k = 10, declared before it is scored**
- k = 5, 20 and 30 only as a sensitivity table, not to choose k on these grades (they are the E1 grades).
- Pairs to grade (count made on the same pool and chunk hashes): k = 5: 0; **k = 10: 1** (1 question, 1 call per judge); k = 20: 6; k = 30: 3. The hybrid top 5 changes on 301 of 339 questions at k = 10. Scoring costs a few cents and needs no re-grade.

**Not done**
- Adding k as a variant in `rag/pooled.py`, the one missing grade, the sensitivity table, reading about 10 more cases, the header test.
- Until then E3's baseline stays an open choice between dense and hybrid k = 60.

## Update to the pending investigation: cases read, tokenization finding, k test

**(a) Cases read**
- 15 of the 30 dense-wins: 5 first, then a seeded random 10 of the other 25 (seed 20261023), first lines of each chunk only.
- In 8 of the 10 the dense 2 is outside BM25's top 50; in the other two it is at BM25 rank 24 and 31.
- Hybrid's top 5 holds no 2 but mostly 1s: right area, wrong rule. Examples: worked examples of ป.96/2543 for Q0021 and Q0187, adopted-child edge cases for Q0277, spouse-deduction rules for Q0283. In 5 of the 10 dense itself ranks several of those chunks in its own top 10.
- When the answer is a statute or a table (Q0192, Q0277, Q0187, Q0021), FAQ and worked-example chunks outrank it.
- In 3 of the 10 (Q0007, Q0218, Q0251) the dense "2" is doubtful (strict 1 in two): part of dense's lead is lenient grading.
- The header lead looks weaker: only Q0106 and Q0115 show clauses of one decree sharing a title.

**(b) Why BM25 misses** (found in `rag/sparse.py`)
- newmm tokens, no stopwords; the questions are colloquial and the chunks formal. Q0062's "พ่อแม่" shares no token with the chunk's "บิดามารดา"; "ฐานภาษี" (Q0192) is split into ฐาน + ภาษี, and ภาษี is in nearly every chunk.
- These are query-to-text mismatches, not evidence that the content is weak. That claim stays untested: the 31 questions (9%) with no 2 anywhere in the pool (56 strict) are a different group.
- Redundancy is real (the same FAQ topics occur in several documents), which makes lookalikes easy.
- To test, in this order: tokenization fixes and a colloquial-to-formal mapping, then the header hypothesis.

**(c) k test done** (`--variants 10 5 20 30`; k = 10 declared first)
- 8 pairs added and graded by all three judges: pool 7,010 → 7,018 pairs. The baseline numbers did not move at three decimals.

| mode (panel median, 339) | hit@5 | nDCG@10 | recall@10 |
|---|---|---|---|
| dense | .717 | .695 | .686 |
| hybrid k = 60 | .699 | .664 | .608 |
| **hybrid k = 10** | .699 | .659 | .623 |
| hybrid k = 5 | .705 | .649 | .610 |
| hybrid k = 20 | .693 | .668 | .624 |

- k = 10 against k = 60: no measurable difference (every interval contains 0, on every metric).
- k = 10 against dense: nDCG −0.036 [−0.055, −0.017] and recall −0.063 [−0.108, −0.019] stay outside the interval; hit@5 −0.018 [−0.053, +0.018] inside.
- Where it goes: k = 10 recovers 16 of the 30 dense-wins but loses 9 of the 24 hybrid-wins (k = 5: 19 of 30, loses 13 of 24). The constant moves which questions win, not how many.
- Strict: k = 5 gains hit@5 over k = 60 (+0.047 [+0.009, +0.086]) and matches dense on it (+0.009), but nDCG@10 stays 0.040 below dense.
- **Reading:** the fusion constant is not the main cause. The remaining gap sits in what BM25 contributes (the vocabulary mismatch above).
- Caveat: recall@10 is relative to a pool whose fused top 10 always takes some chunks from the weaker ranking.

**Not done:** tokenization and synonym test, header test.

## Tokenization, mapping and header tests (retrieval only)

Scratch scripts, no LLM calls; nothing in the repo or the frozen chunks changed. All scored on the E1 grades, so a chunk a variant brings in that nobody graded counts as "not a 2". The hit@5 below are lower bounds, and variants that bring in many ungraded chunks are the most underrated. The base rows reproduce E1 exactly (sparse hit@5 .504, hybrid .699).

**(a) Sparse input**

| variant | sparse hit@5 | hybrid k = 60 | hybrid k = 10 | dense 2 in sparse top 50 (of 30 dense-wins) |
|---|---|---|---|---|
| current newmm | .504 | .699 | .699 | 6 |
| newmm + colloquial-to-formal query mapping | .516 | .699 | .708 | 7 |
| character 3-grams | .504 | .676 | .705 | 11 (4 in the top 10) |
| character 4-grams | .472 | .681 | .684 | 12 |

- The mapping (พ่อแม่ → บิดา มารดา, ลูก → บุตร, ภรรยา → ภริยา and a few more) was written after reading the failures, so this is a best case, and it is a no-op.
- Chunk and query are tokenized the same way, so compounds such as ฐานภาษี do match. The earlier worry that splitting hurts was wrong.
- N-grams reach more dense answers but bring about 5 ungraded chunks per question into the top 10 (848 new pairs for 3-grams at k = 60, 629 at k = 10). Unresolved, not graded.

**(b) Header test** (document title removed from the indexed text of every chunk, sparse and dense, on the GPU)
- Variant B strips the title only where a section or unit label remains, because 275 of the 2,070 chunks have a header that is only the title.
- **Q0106 is fixed** (the crypto clause): dense rank 5 → 1, sparse outside the top 50 → 4, hybrid 12 → 1. This confirms the mechanism for decree clauses that share a title containing the query word.
- Over all questions the known hit@5 barely moves: dense .717 → .714 / .705; hybrid k = 60 .699 → .702 / .702. Per-question changes balance (dense +15 / −19; hybrid k = 60 +7 / −6 for variant B).
- 758–870 ungraded chunks enter dense's top 10, so a small gain or loss is hidden; grading them would take about 760–870 pairs.
- The 30 dense-wins stay mostly unfixed (dense 2 in sparse's top 50: 8 of 30, was 6).

**Reading the four tests together** (RRF k, tokenization, mapping, header)
- None closes the dense-over-hybrid gap, which is small (nDCG@10 −0.03, hit@5 −0.02 inside the interval).
- Hypothesis, not shown: BM25 contributes little on these colloquial questions because they share few words with the formal chunk text, and RRF gives it an equal vote.

**Decision for E3 (confirmed 2026-10-23):** baseline dense, with hybrid k = 60 as the other-mode variant (the plan's outcome row "a single mode beats hybrid", weakly). After E1b, dense + reranker joins as the main variant compared with dense, and hybrid is the first variant to drop.

**Not done, not planned:** grading the n-gram and title-less variants (about 760–870 pairs each); a stronger query rewrite, for example an LLM expansion.
