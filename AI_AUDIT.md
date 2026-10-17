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

## Trafilatura truncated an FAQ answer (not fixed)

- **What happened:** `60061.html` lost the tail of its first answer (the paragraph on a spouse's social-security contributions). The first-pass extraction was reviewed as "fine" on page-level checks, and nothing flagged it.
- **How it was caught:** comparing each text node of the raw `col-main` with the extracted text. Of 15 pages with unmatched fragments, 14 were page chrome ("Untitled Document", visitor counter) and one was this content loss.
- **Fix:** none yet. It is recorded in `KNOWN_ISSUES` and pinned by a test. Repairing it means changing `parse.py`, which re-extracts every page.
- **Files:** `crawler/src/crawler/clean/audit.py`, `crawler/src/crawler/clean/build.py`, `crawler/tests/test_audit.py`

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
