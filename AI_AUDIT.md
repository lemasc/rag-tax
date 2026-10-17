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
