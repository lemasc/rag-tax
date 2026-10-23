# E1: ranking ablation, dense vs sparse vs hybrid

Status: done 2026-10-23. Plan: [`../../plans/ablation-plan-retrieval-context-generator.md`](../../plans/ablation-plan-retrieval-context-generator.md) (E1). Code `rag/pooled.py`, outputs `rag/out/pooled/`, notebook `rag/pooled_browse.py`. Follow-up: [hybrid vs dense investigation](../2026-10-23-hybrid-vs-dense-investigation/README.md).


**Setup**
- 339 content questions, 36 of them dev (339, not 338, because Q0369 is now a normal question).
- 7,010 pairs (20.7 per question), 873 calls per judge (batches of 10, more than the ~700 planned).
- Panel: gpt-6-sol, Claude Haiku 5.5, DeepSeek V4.1 Flash. A "2" is the panel median; strict means all three say 2.

**Result** (panel median, 339 questions)

| mode | hit@5 | precision@5 | MRR@10 | nDCG@10 | recall@10 |
|---|---|---|---|---|---|
| dense | .717 | .297 | .548 | .695 | .686 |
| sparse | .504 | .173 | .344 | .471 | .403 |
| hybrid (RRF k = 60) | .699 | .280 | .520 | .664 | .608 |

- Sparse is clearly worst: hybrid beats it by about 0.2 on every metric (hit@5 +0.195 [+0.145, +0.245]), with and without dev, median and strict.
- Hybrid minus dense, 95% bootstrap interval: hit@5 −0.018 [−0.062, +0.024], precision@5 −0.017 [−0.039, +0.005], MRR@10 −0.028 [−0.065, +0.007] (all inside); nDCG@10 −0.031 [−0.053, −0.009] and recall@10 −0.078 [−0.125, −0.030] (outside). Strict grading agrees and adds precision@5 and MRR.
- By the plan's outcome table this is "a single mode beats hybrid", weakly.

**Where it differs** (hit@5, dense / sparse / hybrid; categories hold 12–35 questions, so these are leads, not results)
- Dense leads on ค่าใช้จ่ายและค่าลดหย่อน (.83 / .49 / .69), ครอบครัวและวางแผนภาษี (.93 / .67 / .73), รายได้ข้ามประเทศ (.73 / .27 / .60), หัก ณ ที่จ่ายและคืนภาษี (.94 / .56 / .72).
- Hybrid leads on กำหนดเวลาและแบบภาษี (.78 / .56 / .94) and ธุรกิจเล็กและขายออนไลน์ (.55 / .50 / .65), where BM25 matches exact terms.

**Open**
- 31 questions have no 2 anywhere in the pool (56 strict): corpus or wording problems, kept for failure analysis.
- Next: find where and why fusion costs, before changing RRF settings or the E3 baseline.

## E1 grading notes

**gpt-6-sol came from two routes**
- 6,404 pairs came from OpenAI direct (`judge.partial.jsonl`). The OpenAI credit then ran out, and the last 606 went through OpenRouter (profile `judge-sol-or`, same model and reasoning effort, `rpm = 18`). The report uses `judge-sol-or.jsonl`, which holds both.
- The two routes are not checked against each other.

**Cost**
- A sol call averages about 3,420 prompt + 298 completion tokens, about $0.0098; a full pass of 873 calls is about $8.6. gpt-6-luna would be about $0.4.
- So sol may not stay on the panel. Replacing it needs a luna-vs-sol-vs-people check on a sample first.

**Judge agreement**
- Exact agreement between judges is 76–79% and 2-point gaps are under 1%: the tier gap is small on these pairs.
- Share of 0/1/2: sol .39/.40/.21, haiku .38/.45/.17, deepseek .45/.37/.18. All three say 2 for 12% of pairs, at least one for 26%.

**Skipped batches**
- A batch a judge answers badly twice is skipped and retried on the next run: one each for haiku and deepseek, both graded since.
