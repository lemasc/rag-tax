# E2: do neighbouring clauses help?

Status: done 2026-10-23. Plan: [`../../plans/ablation-plan-retrieval-context-generator.md`](../../plans/ablation-plan-retrieval-context-generator.md) (E2). Code `rag/neighbours.py` (tests `rag/tests/test_neighbours.py`), outputs `rag/out/neighbours/` (`sample.jsonl`, `judgments/`, `summary.json`). Builds on [E1](../2026-10-23-e1-ranking-ablation/README.md).

**Question.** A chunk the panel graded 1 ("on topic, does not answer") in E1: does it become a 2 when the text next to it is shown with it?

**Setup**
- Sample: chunks graded 1 (panel median) in the dense or hybrid top 5 of E1, two strata reported separately.
  - clause: `origin == "clause"`, 218 pairs from 115 questions (111 distinct chunks).
  - later-part: a later part (part > 1) of a split statute or annex unit, 59 pairs from 48 questions, **12 distinct chunks** (a few chunks come up under many questions).
  - Sparse-only chunks, boilerplate (none matched: none of the 15 boilerplate chunks is in any mode's E1 top 5) and chunks with no neighbour that fits (none) were left out; windows, FAQ and guide chunks are not expanded (see the plan). 1,594 chunk-question pairs were of other types.
- Dilution sample: 54 chunks graded 2 in the same strata (40 clause, 14 later-part; seeded, 32 more were not sampled).
- Two conditions per pair, graded by the three judges (all on OpenRouter) in the batches of `rag.depth`, blind to the E1 grade (the judge does see the marker on the neighbouring text, so it can tell the expanded condition):
  - **alone**: the chunk as in E1, the control (the noise floor);
  - **expanded**: the chunk plus the other parts of its unit, then sibling units under the same parent (nearest first, the next one before the previous one), at most 512 extra tokens (median 467), each neighbour marked as such.
- 662 grades per judge (331 pairs × 2), 314 calls per judge. A batch with the same chunks as an E1 batch is put in reverse order in both conditions, so a judge's cached E1 reply cannot come back as the "alone" grade (3 of 157 questions).
- Gain = share of the 1s that are 2 expanded, minus the share that are 2 alone. 95% bootstrap interval over questions. A 2 is the panel median, or all three judges when strict.

**Result** (277 chunks graded 1)

| group | n | questions | distinct chunks | expanded is 2 | alone is 2 | gain |
|---|---|---|---|---|---|---|
| all | 277 | 143 | 123 | .14 | .10 | **+.05** [+.01, +.09] |
| clause | 218 | 115 | 111 | .14 | .08 | **+.06** [+.02, +.10] |
| later-part | 59 | 48 | 12 | .15 | .15 | **.00** [−.11, +.12] |
| no-"2" questions | 33 | 15 | 29 | .06 | .03 | +.03 [−.09, +.11] |
| in dense top 5 | 198 | 120 | 91 | .16 | .12 | +.04 [−.02, +.09] |
| in hybrid top 5 | 158 | 94 | 94 | .14 | .08 | +.06 [.00, +.12] |

- Strict (all three say 2): +.05 [+.02, +.08] overall, +.06 [+.02, +.09] clause, +.02 [.00, +.06] later-part.
- Per judge, all strata: sol +.05 [−.01, +.10], haiku +.03 [−.03, +.08], DeepSeek +.03 [−.02, +.07]. The same direction and size.
- Per chunk: 17 of 123 distinct chunks gain (14 of 111 clause, 3 of 12 later-part), on average +.04.
- Dilution (the 54 chunks graded 2, share below 2 expanded minus alone): 0.00 by the median; −.11 strict (clause −.15). Neighbours do not dilute good chunks.
- The noise floor is large: about 10% of the 1s are 2 when asked again alone (16% for sol). Among the 1s, haiku moves 21 chunks up to 2 expanded but 16 chunks it graded 2 alone fall to 1, so much of the movement is re-grading noise.

**Reading it**
- The plan's rule was 10 points over the noise floor. The clause gain of +.06 is real (interval above zero) but below that (the interval's upper end, +.10, does not rule 10 points out; the decision rests on the estimate): about 13 of the 218 clause pairs are upgraded. By the plan's outcome table: "about the floor" for most of the sample, with a small effect on clauses.
- The later-part stratum, where a hand review of 10 chunks (1 yes, 3 unsure, 6 no) was most hopeful, shows nothing, on only 12 distinct chunks.
- The 1s are mostly on-topic misses (the chunk is about a different subtopic), not clauses missing a condition next door.
- Decision: neighbours are out of E3. A neighbours variant would cost about a quarter of E3's judge bill for a grade gain of about six points on a third of the questions. The k = 10 control stays.

**Caveats**
- E2 measures the panel's grade of a chunk, not the quality of an answer; it says nothing about whether the generator uses the extra text better.
- Alone and expanded batches contain only the sampled chunks of a question, not the ~21 of E1's pool. The alone control therefore also absorbs the effect of the different batch; the gain subtracts it.
- The panel is lenient (E1 notes), so absolute shares of 2 are too high; the comparison between conditions is the reliable part.
- The pre-review that chose the later-part stratum was a hand mark of 10 chunks, not a measurement.

## Run notes

**Sol**
- All three judges started together on OpenRouter; sol stopped with a 402 ("would exceed your available credits given your current in-flight requests") after 217 of its 314 calls. The OpenRouter balance was then about $0.69 of $10, with a daily limit of $8. The 217 replies were cached and paid for, but nothing had been saved to `judge-sol-or.jsonl`, because `rag.neighbours` writes a judge's grades only at the end of its run.
- After a top-up, DeepSeek's one batch that had failed twice and sol's remaining calls were run one after the other; the cached replies came back free.
- All judges ran on one route (OpenRouter) for both conditions. Sol's E1 grades came from two routes, but the gain is expanded minus alone, both from this run, so the route effect cancels. The route-drift re-grade planned in the plan was not needed.

**Cost**: not tallied from the cache; the price file estimates about $2.1 for about 280 calls per judge (this run made 314).

**Fixes made after the run** (`rag/neighbours.py`; the numbers above did not change):
- the report crashed on a numpy integer when saving `summary.json`;
- the per-judge rows now keep only grades of the text the sample shows (as the panel rows already did), and are listed once, under the median, since one judge's grade is the same under either rule.
