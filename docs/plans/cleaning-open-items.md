# Cleaning and chunking: open items

Status: started 2026-10-17. Tracks details that did not resolve while building `crawler/src/crawler/clean/` (cleaning, FAQ/statute units, Gazette headers). Each item says what is known, what is not, and what would settle it. Evidence comes from `crawler/notebooks/clean_review.ipynb` unless stated. Move an item to **Resolved** with a commit hash when it closes.

## Open

### 1. Line breaks in PDF-derived and flat-HTML legal text

**State:** not normalised. The cleaned text keeps whatever line structure extraction produced.

**What is known**
- OCR (Typhoon) breaks lines where the printed page does, around 80–95 characters. `pdftotext` is wrapped the same way. Flat HTML legal text has the opposite problem: whole documents collapsed onto very long lines (median 143 characters per line, p90 560; `2502.html` is 61K characters in a few lines).
- By a rough start-of-line marker heuristic (`ข้อ N`, `(N)`, `หมายเหตุ`, …), 42% of OCR lines, 76% of `pdftotext` lines and 53% of HTML lines are continuations rather than paragraph starts. Median line length: OCR 84, `pdftotext` 73. Treat these numbers as rough.
- In a sample of 10 OCR line breaks (`mr401A`, `mr396`) every break fell at a word boundary, none mid-word.
- Typhoon OCR writes ASCII digits whatever the print form (0 Thai digits in the 11 OCR files), so digits need no handling there.

**What is not known**
- The join rule when unwrapping. Thai has no mark at a wrap: `ใน⏎การซ่อมแซม` should join with no space, `พ.ศ. 2496⏎รัฐมนตรี` needs one, and the text does not say which. A candidate rule is "a space only next to a digit, Latin letter or punctuation, nothing between two Thai characters". It is untested, so it is a hypothesis.
- Whether unwrapping matters for retrieval at all, or only for readability and for finding `ข้อ` boundaries.

**What would settle it:** ground truth. Find instruments that exist both as flat HTML (authoritative flow, no wraps) and as PDF/OCR, unwrap the PDF text with each candidate rule, and count character differences against the HTML. Without an overlap, hand-check a sample of breaks in 2–3 OCR documents.

**Blocks:** the instrument/ruling/article splitters, which need paragraph structure first.

**Update 2026-10-18 (`4fc4156`):** split *words* (not wrapped lines) are now rejoined by `clean/rejoin.py`, and three tone-mark misorders are repaired in pdftotext text. Line unwrapping itself is still not done. Findings from that pass:

- **pdftotext Thai is damaged beyond line breaks.** Out-of-dictionary newmm tokens per 1k Thai tokens, median per legal document: pdftotext 37.4 (17 docs), HTML 13.4 (82), OCR 6.5 (11). Besides split words it has tone marks out of order (`หนา้`, `ชือ่`), a vowel one consonant too late (`หกั`, `ทงั้`) and dropped tone marks (`เงินได`). The rules repair only the never-valid tone positions (37 repairs); the rest stays. **Settled 2026-10-18:** the 17 documents were re-OCR'd with Typhoon and compared (word-level diffs, similarity 0.94–0.998). OCR had lower OOV on 16 of 17, and 8 of the 17 pdftotext texts had lost sara am entirely (`กาหนด`, `คานวณ`), which OOV cannot see because the pieces are valid words. PDFs now use OCR by default; the tone-mark rules stay in `rejoin.py` but no document uses them. OCR trades these defects for possible hallucination (next point).
- **OCR hallucination in `mr401A`** (`bf11914513ac`, กฎกระทรวง ฉบับที่ 401): `อ๋าถอด` appears 74 times where the printed text says `อำเภอ`, in the province/district lists (e.g. `อ๋าถอดแม่แจ่ม`). Not a line-break problem; nothing repairs it. Re-OCR that page or patch it by hand; check other OCR documents for similar repeated junk with the same OOV count.
- **The first join rule over-merged.** Joining whenever newmm finds a word across the break proposed ~800 joins, most of them real phrase spaces in clean HTML (`แล้ว จะ` -> `วจะ`, `นาย ก` -> `นายก`). The committed rule joins only at a non-word fragment or a mark that cannot start a syllable: 132 joins in pdftotext, 5 in HTML, 0 in OCR. Known miss: `รหัส ผ่า น` (`8d6b68bf1ac8`) stays split because `ผ่า` is itself a word.

### 2. Splitters for instruments, rulings, คำวินิจฉัย and articles

**State:** not started; deferred on purpose. Only FAQ items and statute sections have unit boundaries.

**What is known:** `ข้อ N` is a clean `1..N` sequence in 64 of 110 legal documents (กฎกระทรวง, คำสั่ง and most ประกาศอธิบดี). พ.ร.ฎ. use `มาตรา` instead (17 of 19 clean). คำวินิจฉัย (10) have no markers. 10 of 32 ประกาศอธิบดี are noisy (amendments quoting other instruments, annexes). Rulings carry a header table (เลขที่หนังสือ, วันที่, เรื่อง, ข้อกฎหมาย, ข้อหารือ). Articles are heterogeneous.

**What is not known:** how to split the noisy ประกาศอธิบดี and the marker-less documents, and whether most of them are short enough (median 2–7K characters by kind) to stay one unit.

**Depends on:** item 1.

### 3. Token-aware chunk size

**State:** deferred until there is an embedding model and the length distributions are reviewed.

**What is known:** character-length distributions per kind and per unit type are in the notebook (section 3): FAQ units median 347 characters, p90 862, max 6,244; statute sections median 634, p90 5,008, max 8,771.

**What would settle it:** token counts with the chosen embedding model's tokenizer on those same units and documents, then a justified size. The assignment requires the choice to be justified.

### 4. Include rule for hub, thin and TOC pages

**State:** rule-based default, not a decision. 14 first-pass pages have `include = false`: 11 hubs, 2 thin, and the statute table of contents `2597`.

**What is known:** a few look like real content, for example `56243` (118 characters: refunds go only to PromptPay linked with the national ID) and `1779` (170 characters, "calculating tax by method 2"). The list is in the notebook (section 5) and the viewer.

**What would settle it:** a keep/exclude call per page by a human. The marimo review notebooks already have decision UIs if a CSV is wanted.

### 5. Tax year metadata

**State:** heuristic, unvalidated. It takes the first `ปี/ปีภาษี 25xx` in the heading, then the title, then the body.

**What is known:** 14 of 18 FAQ pages get a year. The other four (`66379`, `61081`, `63908`, `61065`) get `None`. Three of them are linked from a hub page whose heading carries a year (`28`: 2566, `63417`: 2565, `60578`: 2561), so inheriting from the parent is possible. `61081`'s parent (`37343`) has none. Correctness of the 14 years is unchecked.

**Image documents:** `65908_0_lodyon68_update` (the 2568 allowance poster) has `tax_year=None` on purpose. Its heading `ลดหย่อนภาษี 2568` does not match the heuristic (`ภาษี 2568` has no `ปี`), and the body's `ปี พ.ศ.2561` (the child-birth year) would give a wrong 2561 if the body fallback ran. Set it by hand when the rule is settled.

**What would settle it:** a hand check of the 14, then an inherit-from-hub rule for the rest.

### 6. Guessed FAQ section headings

**State:** 30 headings guessed (7 in `62149`, 23 in `62777`), flagged `section_guessed`, listed in the notebook (section 4a). All looked right on a first read. A wrong guess leaves one short line in the wrong place and never loses text.

**What would settle it:** a human pass over the 30 rows.

### 7. Publication date on PDF-derived documents

**State:** `gazette_date` found for 25 of 28 PDF-derived documents. Missing: `dn161A`, `dn162A` (กรมสรรพากร orders ป. 161/2566 and 162/2566, probably not Gazette-published, so no date is expected) and `dg457A`. Typhoon often writes the volume line and the date as one line (`เล่ม 133 … ราชกิจจานุเบกษา 8 สิงหาคม 2559`); `extract.normalise` used to delete those lines whole, which is why the date looked "not read by the OCR". Fixed in the commit that closes the page-anchor work; `dg457A` is unchecked.

**What would settle it:** open `dg457A` and the two orders in the viewer and see whether a publication date is printed.

### 8. Quote style in amending instruments

**State:** left as found. Source mixes `“ ”`, `"`, and sometimes closes a quote with `“` (`13481.html`). A quote-balance check would test the source, not the cleaning.

**Matters when:** someone parses the replacement clauses of amendments. Not needed before then.

### 9. `extract.py` header regex is narrower than `clean/gazette.py`

**State:** `extract.py` strips only `เล่ม`, a bare `หน้า N` and a bare `ราชกิจจานุเบกษา`, and now leaves a volume line that carries the date for the clean stage. The clean stage covers the out-of-order tone mark, OCR's one-line `หน้า N ราชกิจจานุเบกษา` and the dated volume line. Harmless today because the text cache is cleaned downstream, but the cache itself still holds those lines.

**Options:** leave it (cleaned downstream), or share one pattern between the two modules and re-run extraction (OCR is cached, so no server is needed).

### 11. Verify the hand-corrected `65908` poster text

**State:** the poster is an infographic with non-standard tables, and Typhoon misread its layout: `ส่วนตัว 60,000 บาท` lost its amount, the CCTV row got an invented `100,000 บาท` (the poster gives only `เพิ่ม 1 เท่าตามที่จ่ายจริง`), `สถานพยาบาลของรัฐ` was duplicated with an invented `ตามที่จ่ายจริง`, and the brace label `ตามจริงไม่เกิน` was dropped. The text in `data/text/image/65908_0_lodyon68_update.md` was transcribed from the image (zoomed crops) by Claude and is recorded as `source = manual`, `verified` empty in `data/image_decisions.csv`. The built document carries the flag `unverified`.

**What would settle it:** a person compares every row and amount with `data/raw/img/65908_0_lodyon68_update.jpg` and sets `verified` to the date (the notebook's checkbox does it). Until then, the document should not be the only support for an allowance amount.

**General rule (2026-10-18):** images that defeat OCR are corrected by hand, not by tuning OCR; `source = manual` files are never overwritten by `images.export_kept`, and `verified` says whether a person has compared text and image.

### 12. Markdown tables that trafilatura wrote on web pages were never reviewed

**State:** not checked, not fixed. trafilatura converted the HTML tables of the web pages to markdown rows (`| แนววินิจฉัย | ... |` in the rulings, the summary tables of `59674`, `60579` and `59668`) and nobody compared them with the pages. The OCR tables of the guides and images are different: each of those now has an explicit decision in `crawler/data/table_decisions.csv` (convert, manual or keep; `clean/tables.py`), because a blanket conversion would mangle colspan/rowspan tables without notice. Web pages have no such list.

**What is known** (built corpus, `source = page`): 32 documents have lines that start with `|`, 342 lines in about 39 tables, all of them included documents: 19 articles, 10 rulings, 2 FAQ pages and the index page `67335`. The longest are `6052` (48 lines), `59674` (28), `67335` (28), `5938` (28), `59668` (27), `67032` (22) and `62149` (21); `60579` has 14. Whether a table lost a merged cell, a header row or a cell's line breaks in the conversion is not known; the chunker now repeats a table's header row and separator when it cuts a table between rows, but only if the markdown has a header and separator line.

**What would settle it:** list the 39 tables with their page, look each one up on rd.go.th, and give it the same decision as the OCR tables (fine as converted, hand-written, or fix the extraction).

### 10. Repo hygiene

- `notebooks/.ipynb_checkpoints/` is untracked and not ignored.
- `crawler/.playwright/` is untracked and predates this work.

## Decisions

Recorded in `crawler/data/unit_decisions.csv` (one row per dropped document or unit, with what it duplicates). `crawler.clean.build` applies it (2026-10-19): a dropped document or unit gets `include = false` and `duplicate_of`, and every unit carries `include`. Unit ids are positional (`62149#025`); the build fails if a decision names an id that no longer exists, and since 2026-10-22 also if the record's text no longer matches the decision's `text_hash` (whitespace collapsed), so a splitter or cleaning change that shifts an id onto other text stops the build instead of dropping the wrong unit.

- **`61065` dropped as a duplicate of `61081`** (2026-10-18). All 74 units are identical once whitespace and U+FFFD are ignored; the only other difference is quote marks around the title. `61065`'s hub (`60578`) suggests tax year 2561, but FAQ years are not treated as reliable.
- **Duplicate candidates are found by `crawler.dups`** (2026-10-22), which writes `data/dup_candidates.csv`: every pair of included units (and unit-less documents) with character 6-gram Jaccard ≥ 0.5 or containment ≥ 0.8, sorted into cases. Only one case is settled by dropping. On the corpus of `feat/corpus-update-1` (1,320 pairs): `guide_copy` 173, `legal_version` 69, `legal_shared` 538, `quotation` 417, `same_doc` 95, `other` 28. `quotation` (a guide, FAQ or article quoting a clause) stays: the sources differ in authority and context. `legal_shared` stays: mostly parallel rules (ประกาศ 165/166/167 on housing-loan interest share their criteria) and boilerplate (the commencement มาตรา of every พ.ร.ฎ.). An earlier read that `af50cc814dee` / `eda74e6fd349` are duplicates was wrong: they are คำวินิจฉัย 20/2533 and 21/2533 from one meeting, sharing a paragraph.
- **Filling guides: cut at the guide's numbering, keep Ins90 for the shared sections** (2026-10-22). The OCR marks headings differently in each guide (Ins90 has `11.1` as a heading, Ins91 as a plain line or a bold run-in; `ตารางที่ 1` is a heading in Ins91 only), so the units did not line up and a unit-to-unit comparison missed copies: Ins91 `#026` held eight Ins90 units. `split_guide` now also cuts at an unmarked item line whose number counts up (guides only, not web pages) and at `ตารางที่ N`, which makes each printed table a unit named after its title; a table is never joined to a short section before it. Guide units: Ins90 116, Ins91 72, Ins94 63. 62 units dropped, 49 of `Ins91_241268` and 13 of `Ins94_050668`, each matching an Ins90 unit at Jaccard ≥ 0.95 (31 identical after markup), with every difference read by hand: item numbers (ภ.ง.ด.94 numbers 10.x as 8.x), the form name, the page footer, OCR slips, a few words. Three are tables: Ins91's tax-rate form and party list, Ins94's expense-rate table. Pairs under 0.95 stay, because that is where the forms differ in substance: Ins94's filing period (1 กรกฎาคม–30 กันยายน), a start date of 2565 where Ins90 has 2563 (`Ins94_050668#030`), Ins94's tax-rate table with its own note on the 150,000-baht exemption. A 6-gram score alone cannot find these: a changed month or year is a few characters. Some kept Ins90 units have OCR slips the dropped copy does not (มูลค้ำ for มูลค่า); recorded per row, not repaired. A question about ภ.ง.ด.91 now gets a chunk headed ภ.ง.ด.90 for these sections.
- **Old instruments stay, with what amended or repealed them** (2026-10-22). Text similarity cannot tell a version from a parallel rule, so relations come from the instruments' own `ให้ยกเลิก` / `ให้เพิ่ม` clauses: `crawler.legal_relations` proposes them (`data/legal_relation_candidates.csv`), and the checked rows are in `data/legal_relations.csv` (46: 14 with the target in the corpus, all read against the clause). The build sets `amends` on the newer document and `amended_by` plus an `amended` or `repealed` flag on the older one; chunks carry the flags. Repealed in the corpus: ประกาศ 58 (`6247e649e635`) and 438 (`cff6edd5a5c3`) by 451, พ.ร.ฎ. 301 (`d9d4d315a4e1`) by 664, กฎกระทรวง 134 (`8876d625648a`) by 350. Amended: กฎกระทรวง 126, พ.ร.ฎ. 11, ประกาศ 86. Using the flag (prefer the newest source, or show it to the generator) is the tax-year ablation in `generation-and-eval.md`, not a cleaning step.
- **Instrument numbers come from the text's heading, not the listing title** (2026-10-22). rd.go.th lists a consolidated ประกาศ under its latest amendment: `eb7a43a23f0b` "ฉบับที่ 224" holds ประกาศ 165 as amended. 13 ประกาศอธิบดี are listed this way, and so is 2502.html (listed as กฎกระทรวง 380, holds 126 as amended). One is mislabelled outright (dg457A, listed as 459, holds 457). `legal_relations.own_number` reads the heading. Titles in `documents.jsonl` are unchanged, so a chunk header can still show the amendment's number.
- **62149 / 62777: keep 62777 for the 20 shared units** (2026-10-18). The overlap is one block of 62149 (`#025`–`#048`, section การหักค่าลดหย่อน) matched to units scattered across 62777's per-deduction sections. Compared after stripping `Q n :` / `A n :` labels (62777 restarts numbering per sub-topic, so labels always differ) and whitespace: 10 identical, 3 differ in wording only, 7 differ in substance. In the substantive ones 62149 is the older revision even though its title says ปี 2563: own health insurance 15,000 (2560) vs 25,000 (2563), RMF 15% with minimum-purchase rules vs 30% without. The other 55 units of 62149 and 93 of 62777 are unique and kept. The 7 substantive pairs are candidates for evaluation questions on outdated limits.

## Resolved

- **pdftotext against OCR for the 17 pdftotext documents:** PDFs now use OCR by default, `b3087dd`. See the update under item 1.
- **Page anchors (`<!-- page N -->`) stripped by `extract.normalise`:** kept in `data/text/legal/` and turned into `pages` offsets by `clean/pages.py` (`documents.jsonl`: `[[pdf page, start offset], ...]`, null for HTML). The number is the PDF page index, not the printed Gazette page. A word split across a page boundary is not rejoined. Open: nothing reads `pages` yet (the legal splitters, item 2, will). Typhoon's markdown (`**bold**`, `<table>`) is left in the text, as it already was for the first 11 OCR documents.
- **Image-only content in HTML pages:** `crawler/images.py` finds, fetches and OCRs the images; `data/image_decisions.csv` decides which become documents (`source = "image"`), reviewed in `notebooks/image_review.py`. First decisions 2026-10-18: `65908` kept, `558` dropped (the page text covers the steps), banners and headings dropped; the Clear Cut infographics, the Q&A and refund tables and `61549`'s `image002` wait for the overlap check.
- **Gazette date lost on OCR documents with a one-line volume+date header:** `gazette.py` and `extract.HEADER`; 4 more documents have a `gazette_date` (25 of 28).
- **U+FFFD in source HTML** (21 characters: 20 in `61065`, 1 in `61117`; already in the raw HTML, missed by the character-class profile because Python counts U+FFFD as printable): mapped to a space in `normalize`, `61ce262`.
- **60061 dropped a paragraph** (bare `<strong>` outside any `<p>` dropped by trafilatura): fixed in `parse._wrap_bare_inline`, `f0223db`.
- **Gazette page headers left in PDF-derived text** (`เลม่ …`, OCR `หน้า N ราชกิจจานุเบกษา`, repeated page dates): fixed in `clean/gazette.py`, `28628f5`.
- **cp1252 quotes left as control characters** in 38 legal files: fixed in `clean/text.py`, `d4907e7`.
