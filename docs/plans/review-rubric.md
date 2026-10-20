# Human review rubric

Status: draft 2026-10-21, to be agreed before the shared set is labelled. The values and tags live in `rag/labels.py`; keep the two in step. The LLM judge (plan step 5) will use the same rubric, so these labels double as its validation sample.

## How the review is organised

- Open the notebook, pick your name (or type a new one), pick the run.
- **Shared set first:** 10 dev questions (`rag/eval/shared_questions.txt`) that everyone labels, without discussing them. Agreement between reviewers is measured only there. If agreement is poor, fix the wording here and re-label the shared set before going on.
- Then the queue offers questions nobody has labelled yet. A multi-turn set stays with whoever starts it.
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

**behaviour** (did it do what the question type needs):

| Value | When |
|---|---|
| ไม่เกี่ยว (na) | The question needs no special behaviour (most normal questions) |
| ทำถูก (yes) | Asked for missing facts, corrected a wrong premise, or said the sources do not cover it, when the question called for it |
| ไม่ทำ / ทำผิด (no) | Should have done one of these and did not, or did one when it should not have |

A grounded answer can still be incorrect: the corpus holds outdated material, and an answer faithful to a 2560 FAQ quotes a 2560 limit. Score both items separately; that difference is one of the things the evaluation is meant to show.

## Failure tags (any number)

| Tag | Meaning |
|---|---|
| retrieval_miss | The right document was not retrieved (say which in the note if you know it) |
| one_doc | One document filled most or all of the slots |
| outdated | Uses an old year's figure or rule |
| misread | Misread a source or used it out of context (e.g. a ภ.ง.ด.94 half-year amount presented as an annual one) |
| unsupported | States something not in any source |
| calc_error | Arithmetic or tax calculation wrong |
| needless_refusal | Declined or asked back when the sources were enough |
| bad_citation | The cited source does not say what the sentence says |
| language | Unnatural or hard-to-read Thai |
| other | Anything else; describe it in the note |
