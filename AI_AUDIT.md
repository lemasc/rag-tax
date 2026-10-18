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

## The OCR text of the allowance poster drops the personal allowance

- **What happened:** the 2568 allowance poster (`65908`) is the only source of the current allowance amounts in the corpus, and was kept on the strength of its OCR output looking complete (all sections, most amounts present). Reading the image next to the text shows `ส่วนตัว 60,000 บาท` has lost its amount, one `60,000 บาท` serves two rows, a shared `ตามจริงไม่เกิน` brace label is gone and one donation row is duplicated.
- **How it was caught:** opening the image after the text was exported, before the build was committed; no automatic check can see a missing row.
- **Fix:** none yet; recorded as open item 11 in `docs/plans/cleaning-open-items.md` with what would settle it. The document is in the corpus as it came out of OCR.
- **Files:** `crawler/data/text/image/65908_0_lodyon68_update.md`, `crawler/data/image_decisions.csv`
