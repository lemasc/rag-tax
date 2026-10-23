# Judge swap: gpt-6-luna in gpt-6-sol's seat

Status: done 2026-10-23. Plan: [`../../plans/ablation-plan-retrieval-context-generator.md`](../../plans/ablation-plan-retrieval-context-generator.md) ("Judge swap"). Code `rag/judge_swap.py`, grades `rag/out/pooled/judgments/judge-luna-or.jsonl`, result `rag/out/pooled/judge_swap.json`. Builds on [E1](../2026-10-23-e1-ranking-ablation/README.md).

**Question.** Can gpt-6-luna (about a twentieth of sol's price) replace gpt-6-sol in the panel from E1b on, without changing what E1 says?

**Setup**
- luna (`judge-luna-or`: OpenRouter, reasoning effort medium as sol) graded the whole E1 pool in E1's own batches: 7,018 pairs, 875 calls, one pass, nothing failed. Cost $0.60 (OpenRouter's reported cost).
- Rules fixed and committed before the run (plan, `6342e2b`): pairs pass if luna's exact agreement with each judge is ≥ .72, 2-point gaps < 2%, and its share of 2s ≤ sol's + .05; results pass if the new panel (luna, haiku, DeepSeek) ranks the three modes in the same order on every metric and each of the 15 differences lies inside the old 95% interval.

**Result: both pass; luna takes sol's seat.**

| Judges | exact agreement | 2-point gaps |
|---|---|---|
| sol vs luna | **.804** | .002 |
| sol vs DeepSeek | .787 | .007 |
| DeepSeek vs luna | .785 | .004 |
| haiku vs luna | .767 | .005 |
| sol vs haiku | .766 | .006 |
| haiku vs DeepSeek | .763 | .006 |

- luna agrees with sol more than any other two judges do, and is the strictest: share of 2s .154 (sol .210, haiku .175, DeepSeek .179).
- How they differ (sol → luna, 7,018 pairs): 488 pairs 2 → 1 and 107 pairs 1 → 2; 0 ↔ 2 only 12. luna gives fewer 2s in every one of the 18 categories (−.02 to −.08), most in ภาษาพูด (−.08), รายได้ข้ามประเทศ and ฟรีแลนซ์ (−.07), least in ยื่นภาษีออนไลน์ (−.02). A shift in strictness, not a different reading of relevance.
- E1 under the new panel: dense > hybrid > sparse on all five metrics, as before; all 15 differences inside the old intervals. Hybrid − dense: nDCG@10 −.038 (old −.031), recall@10 −.072 (old −.078).

| a 2 is the median | hit@5 old → new | nDCG@10 old → new | recall@10 old → new |
|---|---|---|---|
| dense | .717 → .687 | .695 → .696 | .686 → .682 |
| hybrid | .699 → .658 | .664 → .658 | .608 → .610 |
| sparse | .504 → .481 | .471 → .466 | .403 → .404 |

**Reading it**
- The comparison between modes does not depend on whether sol or luna is the third judge. Absolute hit@5 and precision@5 fall by .02–.04 because luna gives fewer 2s; nDCG and recall barely move.
- From E1b on, E1 is quoted under the new panel next to E1b; the published E1 numbers (old panel) stay as they are. The new-panel numbers carry no two-route caveat (luna ran on one route).
- luna is a judge from now on, so it is not a generator.

**Caveats**
- This validates luna as a chunk grader. Grading answers (E3) is another task; the plan's sol check on 30 E3 answers covers that.
- Agreement is with other LLM judges, not with people (H1).
