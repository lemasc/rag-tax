# AI audit

Findings where AI output was wrong or needed correcting. One section per finding.

## Garbled PDF text passed the "image-only" check

- **What happened:** the first crawl flagged a PDF as needing OCR only if `pdftotext` returned fewer than 150 characters. About 370 Royal Gazette PDFs (11 in the core set) returned plenty of characters, but they were nonsense because of broken font encoding, so the check passed them as good text.
- **How it was caught:** reading sampled documents in the review notebook showed unreadable Thai.
- **Fix:** `text` is now set by a common-legal-word density check (garbled = 0 per 1k characters, real text at least 8). The 11 core documents went through Typhoon OCR, and a few samples were checked by hand and read clean.
- **Files:** `crawler/src/crawler/legal_core.py` (`quality`), `crawler/src/crawler/extract.py`, `docs/plans/text-extraction.md`

## Mislabelled and duplicate-looking listings

- **What happened:** `2502.html` is listed as กฎกระทรวง ฉบับที่ 380 but holds the consolidated ฉบับที่ 126 (2509). `dg457A`/`dg459A` and `dg438A`/`3186.html` look like duplicates by title but are a base notice plus its amendment.
- **Fix:** kept both pairs and recorded the decisions in the notebook; titles on rd.go.th can't be trusted without reading the body.
- **Files:** `crawler/notebooks/legal_review.py` (section 0)

## Windows-1252 quotes left as control characters

- **What happened:** the extracted legal text kept `\x93`/`\x94` (cp1252 quotes decoded as C1 control characters) in 38 files, 169 characters. They delimit the replacement clause in amending instruments ("ให้ใช้ความต่อไปนี้แทน “…”"), and the earlier cleanup step did not look for them.
- **How it was caught:** a character-class count over the corpus while profiling the cleaning work, not by reading documents.
- **Fix:** `normalize` maps them to curly quotes; a test checks every legal file and that none are left behind. Quote style is otherwise left as found: the source also uses `"` and sometimes closes a quote with `“` (`13481.html`), so a quote-balance test would have tested the source, not the repair.
- **Files:** `crawler/src/crawler/clean/text.py`, `crawler/tests/test_text.py`

## Trafilatura dropped a paragraph from an FAQ answer (fixed)

- **What happened:** `60061.html` is missing the last paragraph of its item 4 (ชื่อเรื่อง 4): "if the spouse also paid social-security contributions all year, the taxpayer may deduct those too (ม.47(1)(ฌ))". The extracted answer stops one paragraph early and reads as if only the taxpayer's own contributions count. The first-pass extraction was reviewed as "fine" on page-level checks, and nothing flagged it.
- **How it was caught:** comparing each text node of the raw `col-main` with the extracted text. Of 15 pages with unmatched fragments, 14 were page chrome ("Untitled Document", visitor counter) and one was this content loss.
- **A second error, caught later:** the first write-up (code comment, this log, the notebook) said trafilatura "cut the tail of the first answer". That was wrong on both counts: it is the last item, and a whole paragraph is missing rather than a sentence cut off. Found when asked to explain the issue, by printing the raw nodes next to the extracted unit. I also guessed the cause was a `<strong>` inside a `<p>`; the real shape is different (below).
- **Cause (verified):** the paragraph is a bare `<strong>` that is a direct child of the page's `<div>`, with no `<p>` around it (it follows the `</p>` that closes the answer). Wrapping that one node in a `<p>` before calling trafilatura makes the paragraph come out; `favor_precision` and `no_fallback` do not. Re-extracting all 76 pages with the current settings reproduces `pages.jsonl` exactly, and re-extracting with bare inline children of a `<div>` wrapped in `<p>` changes exactly one page (`60061`, +244 characters). The other bare inline fragments in the corpus are page chrome ("<< กลับ", visitor counters) and stay dropped.
- **Fix:** `parse._wrap_bare_inline` wraps inline elements that are direct children of a `<div>` in `<p>` before extraction. `pages.jsonl` was regenerated: one record differs (`60061`, `text` only). A test on the real page fails without the fix, and another re-parses every raw page and compares with `pages.jsonl`. A first attempt at a synthetic-HTML test passed even with the fix disabled (trafilatura's choice depends on the whole page), so it was dropped.
- **Files:** `crawler/src/crawler/parse.py`, `crawler/tests/test_parse.py`, `crawler/tests/test_audit.py`

## Exploratory regexes reported FAQ defects that were not there

- **What happened:** my first profile said 9 of 18 FAQ pages had Q/A count mismatches, `60062` had a gap in its numbering, and `60061` had a missing title. All three were false. The regexes required `คำตอบ` at line start and a single dot in `3. ชื่อเรื่อง`, but the source also has `3..ชื่อเรื่อง`, `1. .ชื่อเรื่อง`, answers without a colon, answers after a `<br />`, and an answer glued to its question. I also said the documents without `ข้อ` markers were คำสั่ง and คำวินิจฉัย; they are พ.ร.ฎ. (which use `มาตรา`) and คำวินิจฉัย.
- **How it was caught:** comparing marker counts in the raw HTML with the extracted text (both had 16 of 16), then writing the splitter's tests against the real pages, which failed on my own expectations.
- **Fix:** the splitter accepts the marker variants; tests name the pages that exhibit each one; the notebook's `ข้อ` table now reports by kind.
- **Files:** `crawler/src/crawler/clean/units.py`, `crawler/tests/test_faq_units.py`, `crawler/notebooks/clean_review.ipynb` (section 4c)

## Section-heading search swallowed answer text

- **What happened:** the first FAQ splitter assumed every Clear Cut page numbers its section headings ("3. การบันทึกเงินได้") and cut the last line matching the next number off the previous answer. On `62149` and `62777`, whose headings are unnumbered, it took numbered list items inside answers as headings and produced "sections" of several hundred words.
- **How it was caught:** printing the distinct section values for those two pages.
- **Fix:** numbered mode applies only when the page's first heading is numbered. Unnumbered pages guess the last short line (at most 40 characters) and flag `section_guessed`; all 30 guesses are listed in the notebook for review. A property test checks that units, preamble and cut headings reproduce each page with no text lost or added.
- **Files:** `crawler/src/crawler/clean/units.py` (`_split_clearcut`), `crawler/tests/test_faq_units.py`

## Gazette page headers survived the extraction cleanup

- **What happened:** `extract.py` strips Royal Gazette running headers with a regex that knows `เล่ม … ตอน …`, a bare `หน้า N` and a bare `ราชกิจจานุเบกษา`. It misses two shapes: pdftotext writes the tone mark out of order (`เลม่ 136 ตอนที่ 79 ก`, 19 lines in 9 documents), and Typhoon OCR keeps `หน้า 3 ราชกิจจานุเบกษา` on one line (`mr396`). The publication date also comes back at the start of every page (46 header lines in 17 of 28 PDF-derived documents). My coverage audit reported these documents as clean because its own header pattern had the same blind spot.
- **How it was caught:** by you, reading the OCR output next to the PDFs (page headers mostly gone, but the date repeated). A scan for header-like lines in all PDF-derived text then found the `เลม่` shape.
- **Fix:** `crawler.clean.gazette.strip_page_headers` handles both shapes, keeps the first standalone date as `gazette_date` (it is the publication date, needed for "effective the day after publication") and drops identical repeats. Applied in the clean stage, so no OCR re-run. `extract.py` still has the narrower regex.
- **Files:** `crawler/src/crawler/clean/gazette.py`, `crawler/tests/test_gazette.py`, `crawler/src/crawler/clean/build.py`

## pdftotext had lost sara am in half the PDFs, and the dictionary metric did not show it

- **What happened:** the cleaning pass judged pdftotext by out-of-dictionary tokens per 1k (median 37.4 against OCR 6.5) and repaired tone-mark order with rules. In 8 of the 17 pdftotext documents the text layer has no `ำ` at all (`กาหนด`, `คานวณ`, `สาหรับ`). The broken pieces are valid words, so `e9c223c3262b` and `0735ac19649b` scored OOV 0.0 and looked clean.
- **How it was caught:** re-OCR'ing 5 documents and reading the word-level diff, then counting `ำ` and likely lost-`ำ` words in all 17.
- **Fix:** PDFs use Typhoon OCR by default (`extract.py`); the 17 documents were re-extracted from OCR. Word diffs for review are in `crawler/data/raw/ocr_compare/` (not in git). The rule-based repairs in `rejoin.py` stay but no document uses them now.
- **Files:** `crawler/src/crawler/extract.py`, `crawler/data/text/legal/`, `crawler/data/legal_text.csv`

## Switching to OCR lost the Gazette publication date on 6 documents

- **What happened:** after the PDFs moved to OCR and the clean stage was rebuilt, `gazette_date` went from set to null on 6 documents. Typhoon writes the volume and the date as one line (`เล่ม 133 ตอนพิเศษ 174 ง ราชกิจจานุเบกษา 8 สิงหาคม 2559`). `extract.normalise` deleted that whole line with its `เล่ม … ตอน.*` rule, and `gazette.py` only knew standalone date lines. The same loss had silently hit 4 of the 11 documents that were already OCR.
- **How it was caught:** diffing every field of `documents.jsonl` against the previous commit after the rebuild, instead of only checking the text.
- **Fix:** `extract.HEADER` leaves volume lines that carry a date; `gazette.strip_page_headers` reduces them to the standalone date (kept once, repeats dropped). 25 of 28 PDF-derived documents now have a date, none lost.
- **Files:** `crawler/src/crawler/extract.py`, `crawler/src/crawler/clean/gazette.py`, `crawler/tests/test_gazette.py`

## The OCR text of the allowance poster lost and invented amounts

- **What happened:** the 2568 allowance poster (`65908`) is the only source of the current allowance amounts in the corpus, and was kept on the strength of its OCR output looking complete. Reading the image next to the text shows `ส่วนตัว 60,000 บาท` had lost its amount, one `60,000 บาท` served two rows, a shared `ตามจริงไม่เกิน` brace label was gone and one donation row was duplicated. A closer look at zoomed crops found worse: a `100,000 บาท` limit invented for the CCTV row (the poster states none) and a `ตามที่จ่ายจริง` invented for the public-hospital donation row. My first comparison missed the CCTV one.
- **How it was caught:** the user's spot check of the image after export; a second, closer read of crops found the invented amounts. No automatic check can see a missing or invented row.
- **Fix:** the text was transcribed from the image by Claude and stored as `source = manual` (never overwritten by export), flagged `unverified` in the corpus until a person compares it with the poster. The model that transcribed it is not independent of the one that misread it, so the `verified` step is the real control. Regression test: `test_65908_text_is_the_corrected_one`.
- **Files:** `crawler/data/text/image/65908_0_lodyon68_update.md`, `crawler/data/image_decisions.csv`, `crawler/src/crawler/images.py`, `crawler/tests/test_images.py`

## A stale notebook server truncated image_decisions.csv

- **What happened:** after the `source`/`verified` columns were added, a `marimo edit --watch` server that had started earlier reloaded the notebook file but kept the old `crawler.images` module (5 columns) in memory. Saving an edit from the UI built a 7-key row, and the old `save_decisions` opened the file for writing, wrote the 5-column header and raised mid-way. The file ended with the header and 15 of 17 rows (`65908` and `66379_0` gone, `source` and `verified` gone). The bug on my side: `save_decisions` truncated the real file before it knew the write would succeed.
- **How it was caught:** the user saw missing columns in the CSV and suspected the server. `git diff` showed the two lost rows.
- **Fix:** the CSV was restored from git (no value in the surviving rows had changed). `save_decisions` now writes a temporary file and replaces the original, so a failure leaves the old file; regression test `test_a_failed_save_leaves_the_decisions_file_intact`. A running notebook still needs a restart after `crawler/` code changes: `--watch` does not reload imported modules.
- **Files:** `crawler/src/crawler/images.py`, `crawler/tests/test_images.py`

## Judge scores from v1 were compared with v2 human labels

- **What happened:** the saved dev-run scores were made by judge v1, before the v2 rubric (behaviour on behavioural questions only, the refusal rule). The human labels were v2. I ran `--compare` and reported the agreement (grounded 68%, correct 56%, useful 70%) and a conclusion built on it, without looking at `scores_config.json`, which said `judge_version: "v1"`. The comparison also pooled every complete label, including 21 made before v2 (81 pairs, not the 60 under v2).
- **How it was caught:** the user asked whether the dev eval should be rerun under v2. Checking showed it had never been. The v2 re-score changed 7 of 40 grounded, 10 of 40 correct and 1 of 40 useful scores; agreement on the 60 v2 labels is grounded 72%, correct 67%, useful 70%.
- **Related, in the same discussion:** I first said the panel would "reduce noise"; the judge was already as consistent with the humans as they were with each other, so I withdrew it (the reason is independence from the generator's family). I put Haiku's 559K input tokens down to retries; it made the same 161 calls as the other judges and its prompts are just long.
- **Fix:** `--compare` uses only labels made under the current rubric and stops when the scores' judge version is not the labels' rubric version. `rag/panel.py` also refuses to combine judges scored under different versions.
- **Files:** `rag/evaluate.py` (`compare`, `main`), `rag/panel.py` (`combine`), `docs/plans/generation-and-eval.md` (*Judge panel*)


## The top-50 human check could only confirm "D" from the first three chunks

- **What happened:** I designed the human check of the top-50 diagnostic to show a reviewer at most three chunks per miss question, the panel-median 2s with the best hybrid rank, and to class a question D when none of the three was graded 2. On the D questions the panel had given a 2 to 2–17 chunks, so the chunks past the third were never read by a person, and chunks outside the pool were never considered. Round 1 came out at D 9 of 13, exactly the pre-registered threshold for "corpus or wording", and I told the user the result "mostly points at the corpus" and that the reranker ablation was now worth much less. That conclusion was drawn from "the first three panel picks don't answer", not "nothing answers".
- **How it was caught:** a keyword search over every chunk, done to split D into coverage gaps and wording mismatches, listed panel-2 chunks no one had graded (e.g. Q0329 `5937#042`, section 63 on refunds of excess withholding, rank 27; Q0301 `552~001`, the 180-day rule, rank 31) and one plausible answer outside the pool (Q0223 `63908#008`). Two or more of them graded 2 would make the verdict "mixed".
- **Related, earlier in the same experiment:** the plan doc's cost estimate (about 650 pairs) was a third of the real pool (1,954 pairs, 206 calls per judge); the pool is the whole fused list, not the top 50. The pre-registered panel grading turned out too lenient on miss questions (people kept 25 of 132 chunks the panel graded 2), which is why the human check was added at all.
- **Fix:** a round 2 grades the 8 chunks picked from the search (`depth.ROUND2`) for the 5 questions concerned, in the same notebook, with the reason and each chunk's origin shown on screen; labels go to `depth_r2.csv` and round 1's stay as they were. The verdict is reported for round 1 alone and for both rounds. The chunks were picked by Claude after reading them, so the selection is not blind; the grades are the reviewers'. Round 2 has fewer reviewers than round 1 (one or two).
- **Files:** `rag/depth.py` (`ROUND2`, `round2_candidates`, `final_class`, per-round label files), `rag/depth_review.py`, `rag/tests/test_depth.py`, `docs/plans/generation-and-eval.md` (*Round 2*)


## Shared text read as duplicates and as versions

- **What happened:** reviewing the corpus update, I reported `af50cc814dee` and `eda74e6fd349` as a likely duplicate because their longest lines start and end alike, and I sorted the 631 legal-to-legal near-duplicate pairs as "versions of an instrument", naming ประกาศ 224 → 396/397/398 as an example. Both were wrong. The two คำวินิจฉัย are rulings 20/2533 and 21/2533 from one meeting, sharing one paragraph. 224, 397 and 398 are listing numbers: the documents are the consolidated ประกาศ 165, 166 and 167, parallel rules that each replace a different older notice and share their criteria clauses.
- **How it was caught:** the first by listing whole-document pairs with their titles (Jaccard 0.77, different numbers); the second by reading each instrument's `ให้ยกเลิก` clause before writing version metadata.
- **Fix:** duplicates and versions are now separate. `crawler.dups` puts each pair in a case, and only filling-guide copies are dropped. Versions come only from the instruments' own repeal and amend clauses (`crawler.legal_relations`, checked by hand into `data/legal_relations.csv`), and instrument numbers come from the text's heading, since listing titles give the latest amendment's number.
- **Files:** `crawler/src/crawler/dups.py`, `crawler/src/crawler/legal_relations.py`, `crawler/data/legal_relations.csv`, `crawler/data/unit_decisions.csv`, `docs/plans/cleaning-open-items.md` (Decisions)

