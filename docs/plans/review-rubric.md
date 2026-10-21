# Human review rubric

Status: v2, 2026-10-21. v1 (the draft) left `behaviour` undefined on normal questions and did not say how to score a refusal; shared-set agreement on `behaviour` was 31% (see *Changes from v1*). Re-label the shared set under v2. The values and tags live in `rag/labels.py`, and reviewers read the Thai version, `review-rubric.th.md`, inside the notebook; keep all three in step. Bump `RUBRIC_VERSION` in `rag/labels.py` when a change alters how an item is scored, and update the change notice at the top of `rag/review.py`. The LLM judge (plan step 5) will use the same rubric, so these labels double as its validation sample.

## How the review is organised

- Open the notebook, pick your name (or type a new one), pick the run.
- **Shared set first:** 10 dev questions (`rag/eval/shared_questions.txt`) that everyone labels, without discussing them. Agreement between reviewers is measured only there. If agreement is poor, fix the wording here and re-label the shared set before going on.
- Then the queue offers questions nobody has labelled yet, in an order of your own (so people working at the same time rarely pick the same question). A multi-turn set stays with whoever starts it.
- Each person's labels go to `rag/eval/labels/<name>/`; commit them like code.

## Running and sharing the notebook

```
uv run marimo run rag/review.py --port 2718 --token-password <password>
ngrok http 2718
```

Send reviewers the ngrok URL with `?access_token=<password>` appended (tested), or the URL and the password separately. Each browser gets its own session, so several people can review at the same time; they must use different names. `marimo run` does not reload code: restart it after changing `rag/review.py` or `rag/labels.py`. Commit `rag/eval/labels/` after a session.

## Per retrieved chunk: relevance

Judge the chunk against the **question**, not the answer.

| Value | Meaning |
|---|---|
| 2 | Contains what is needed to answer (or a necessary part of it) |
| 1 | On the topic, but does not answer it: a neighbouring rule, a different year's figure, background |
| 0 | Not relevant |

## Per answer

Score against the retrieved sources and your own knowledge of current PIT law. Pick the nearest value; use the note when unsure.

| Item | 2 | 1 | 0 |
|---|---|---|---|
| **grounded** (ไม่แต่งเพิ่ม) | Every claim is in the sources | A minor detail is not in the sources | A key claim, figure or condition is not in the sources, or contradicts them |
| **correct** (ถูกต้อง) | Correct for the current tax year as far as you know, figures and conditions included | Right rule, but an old figure, a missing condition, or a year not stated where it matters | Wrong, or would mislead a taxpayer |
| **useful** (ตอบตรง) | Answers the question as asked | Partly answers, or buries the answer | Does not answer |

**Refusals.** When the answer declines, asks back, or says the sources do not cover the question, score it like any other answer:

- **grounded** and **correct** judge what the answer actually says. "The sources do not cover this", when they do not, is not a wrong statement.
- **useful** carries the failure: 0 if nothing is answered, 1 if some substance is given.
- Tag `retrieval_miss` when no retrieved source could answer it, or `needless_refusal` when one could.
- Exception: on ask-back and out-of-scope questions, asking back or saying the sources do not cover it *is* the wanted answer; score **useful** as usual.

**behaviour** is scored **only on behavioural questions** (ask-back, misconception, out of scope). On normal and multi-turn questions it is `na` and the notebook does not show it; a needless refusal there shows up in **useful** and the `needless_refusal` tag, not in behaviour.

| Question type | ทำถูก (yes) | ไม่ทำ / ทำผิด (no) |
|---|---|---|
| ask-back | Asks for the missing facts (it may also give the general rule) | Answers as if the facts were known, or asks for the wrong thing |
| misconception | Corrects the wrong premise | Goes along with it |
| out of scope | Says the sources do not cover it, without giving a wrong answer | Answers anyway, or stretches a neighbouring rule to fit (e.g. a prize-draw rule for a government lottery win) |

A grounded answer can still be incorrect: the corpus holds outdated material, and an answer faithful to a 2560 FAQ quotes a 2560 limit. Score both items separately; that difference is one of the things the evaluation is meant to show.

## Per retrieved chunk: quality issues (optional)

Not part of the rubric and not scored: feedback for the chunker. Under each chunk the reviewer can pick any of `cut` (cut mid-content), `garbled` (broken vowels or tone marks, bad characters), `header` (heading does not match the content), `mixed` (several topics, or old and new law, in one chunk), `other`, plus a note. A flag belongs to the chunk, not the question: it is stored once per reviewer in `chunk_issues.csv`, shows again on every question that retrieves the chunk, and clearing it removes it everywhere. `python -m rag.labels --chunk-issues` lists every flagged chunk. Adding this did not change the rubric version.

## Failure tags (any number)

| Tag | Meaning |
|---|---|
| retrieval_miss | No retrieved source can answer the question (no chunk rated 2); say which document was needed in the note if you know it |
| ignored_source | A retrieved source had what was needed, but the answer left it out or used only part of it |
| one_doc | One document filled most or all of the slots |
| outdated | The answer uses an old year's figure or rule. Old sources that were retrieved but not used do not count |
| misread | Misread a source or used it out of context (e.g. a ภ.ง.ด.94 half-year amount presented as an annual one) |
| unsupported | States something not in any source |
| calc_error | Arithmetic or tax calculation wrong |
| needless_refusal | Declined or asked back when the sources were enough |
| bad_citation | The cited source does not say what the sentence says |
| language | Unnatural or hard-to-read Thai |
| other | Anything else; describe it in the note |

## Changes from v1

The first labels (run `20261020-dev-gpt-mini-hybrid-k5-v1`, three reviewers) showed:

- `behaviour` on normal questions was read three ways: "the answer was good" (`yes` on nearly everything), "not applicable" (`na`), and "the model refused" (`yes` or `no`). It is now fixed to `na` there.
- A refusal on a normal question got `correct=0` from one reviewer ("it fails the taxpayer") and `correct=2` from another ("it says nothing false"). The refusal rule settles it: correct judges the statements, useful judges whether the question was answered.
- `retrieval_miss` was used for "retrieved but not used"; that is now `ignored_source`. `outdated` was used for old sources that the answer did not use.

Old labels are kept, and each answer label now records the rubric version it was made under (rows without one are v1). Shared questions labelled under v1 come back into each reviewer's queue, pre-filled, and shared-set agreement counts v2 labels only. Agreement and the judge comparison also ignore `behaviour` outside behavioural questions. The reviewers never saw v1 itself: the notebook showed only one-line item descriptions. v2 is shown in full in the notebook. The judge prompt follows this version as v2.
