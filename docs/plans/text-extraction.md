# Plan: full-text extraction for the core legal set

Status: built 2026-10-16 (`crawler/src/crawler/extract.py`). Result: 110/112 ok (82 html, 17 pdftotext, 11 OCR); พ.ร.ฎ. 260 and 270 failed because rd.go.th returns HTTP 500. Follows `legal-source-crawl.md` and the core set in `crawler/data/legal_core.csv`.

## Goal

Produce one clean plain-text file per kept core document. Chunking then reads only these files and never touches `data/raw/`.

## Scope

- **In:** the 112 `decision = keep` rows of `legal_core.csv`. Their status today:
  - 99 `text = ok`
  - 11 `text = garbled`: Royal Gazette PDFs with broken font encoding. 8 are the 2566–2568 กฎกระทรวง (Easy E-Receipt, home repair, tourism, …) and 3 are ประกาศอธิบดี (438, 451, 459).
  - 2 `text = missing`: พ.ร.ฎ. 260 (`rd.go.th/2394`) and 270 (`rd.go.th/2390`).
- **Out:**
  - The other ~360 garbled PDFs in tiers A/B. They aren't in the corpus.
  - `data/pages.jsonl` (76 HTML articles/FAQs), which is already extracted with trafilatura.

## Pipeline (`crawler/src/crawler/extract.py`, `uv run python -m crawler.extract`)

For each kept row:

1. **Fetch** if `data/raw/legal/<file>` is missing, using `legal.download`. If either of the 2 missing pages fails again, record it and continue.
2. **HTML:** `legal.doc_text` (the `col-main` text). No OCR.
3. **PDF, text layer:** `pdftotext -layout`, then the `legal_core.quality` check (common legal words per 1k characters).
   - If it is at least `MIN_QUALITY` (5), use this text.
4. **PDF, OCR fallback:** when quality is below 5, call Typhoon OCR as a subprocess so its dependencies stay in their own venv:
   ```
   $OCR_HOME/.venv/bin/python $OCR_HOME/typhoon_ocr_file.py <pdf> -o data/text/legal/_ocr
   ```
   - `OCR_HOME` defaults to `~/san/ocr`.
   - First check that vLLM is up (`GET http://127.0.0.1:8101/v1/models`). If it isn't, mark the row `needs-ocr`, print `~/san/vllm/serve_typhoon.sh start`, and go on to the next row. The run must not fail because of this.
   - Run the same quality check on the OCR output. If it still fails, mark the row `failed`.
5. **Normalise** every result the same way: Thai digits → ASCII, rejoin letter-spaced Thai (as in `doc_text`), collapse runs of blank lines.
6. **Write** the text to `data/text/legal/<file-stem>.md` and one row to `data/legal_text.csv`:
   `url, file, method (html|pdftotext|ocr), quality, chars, status (ok|needs-ocr|failed)`
7. **Back-fill the year.** Re-run `legal_core.year()` on the new text so the 3 undated ประกาศอธิบดี get a year, and update `legal_core.csv`.

The script is idempotent: rows that already have text in the cache are skipped unless `--force` is passed.

## Decisions to make while building

- **`-layout` or not → plain.** On พ.ร.ฎ. 629 both modes keep the same line breaks, but `-layout` pads lines with centring spaces. Plain mode gives the same text without the padding.
- **Found while building:**
  - pdftotext splits sara am into `ํ`+`า`, which breaks tokenisation and BM25. It is recombined *after* letter-spacing repair, because letter-spaced lines put a gap between the two characters.
  - The old letter-spacing rule removed every Thai–Thai space, which also merged real clause breaks. It now applies only to lines where most tokens are fragments.
  - Royal Gazette running headers and Typhoon's `<figure>` captions (the Garuda emblem) are stripped.
- **Commit the text cache → yes.** It's about 564K characters. Committing it lets chunking and evaluation be reproduced without vLLM or the 170 MB of raw files. Recommended.
- **Notebook.** The viewer reads from `data/text/legal/` when a cached file exists, so the OCR output is what gets reviewed.

## Verification

- All 112 kept rows end up `ok`, or are listed explicitly with a reason.
- Hand-check 2–3 OCR outputs against the PDF. Use numbers that are easy to verify, e.g. the Easy E-Receipt cap and period in กฎกระทรวง 397, and the effective date in ป.อ. 459.
- The garbled-PDF finding (pages that passed the 150-character OCR check but were garbage) goes into AI_AUDIT.md as an error catch.
