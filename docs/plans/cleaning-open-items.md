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

**What would settle it:** a hand check of the 14, then an inherit-from-hub rule for the rest.

### 6. Guessed FAQ section headings

**State:** 30 headings guessed (7 in `62149`, 23 in `62777`), flagged `section_guessed`, listed in the notebook (section 4a). All looked right on a first read. A wrong guess leaves one short line in the wrong place and never loses text.

**What would settle it:** a human pass over the 30 rows.

### 7. Publication date on PDF-derived documents

**State:** `gazette_date` found for 21 of 28. Missing for `mr397`, `dn161A`, `dn162A`, `dg457A`, `dg438A`, `dg451A`, `dg459A`: no standalone date line in their text. For the OCR ones the date is probably in a header the OCR did not read, which is unconfirmed.

**What would settle it:** open those PDFs in the viewer (side by side) and see whether a date is printed and where.

### 8. Quote style in amending instruments

**State:** left as found. Source mixes `“ ”`, `"`, and sometimes closes a quote with `“` (`13481.html`). A quote-balance check would test the source, not the cleaning.

**Matters when:** someone parses the replacement clauses of amendments. Not needed before then.

### 9. `extract.py` header regex is narrower than `clean/gazette.py`

**State:** `extract.py` strips only `เล่ม`, a bare `หน้า N` and a bare `ราชกิจจานุเบกษา`. The clean stage covers the out-of-order tone mark and OCR's one-line `หน้า N ราชกิจจานุเบกษา`. Harmless today because the text cache is cleaned downstream, but the cache itself still holds those lines.

**Options:** leave it (cleaned downstream), or share one pattern between the two modules and re-run extraction for the `pdftotext` rows (no OCR needed).

### 10. Repo hygiene

- `notebooks/.ipynb_checkpoints/` is untracked and not ignored.
- `crawler/.playwright/` is untracked and predates this work.

## Decisions

Recorded in `crawler/data/unit_decisions.csv` (one row per dropped document or unit, with what it duplicates). Nothing reads the file yet; the chunker should apply it. Unit ids are positional (`62149#025`), so the file must be re-checked if the FAQ splitter changes.

- **`61065` dropped as a duplicate of `61081`** (2026-10-18). All 74 units are identical once whitespace and U+FFFD are ignored; the only other difference is quote marks around the title. `61065`'s hub (`60578`) suggests tax year 2561, but FAQ years are not treated as reliable.
- **62149 / 62777: keep 62777 for the 20 shared units** (2026-10-18). The overlap is one block of 62149 (`#025`–`#048`, section การหักค่าลดหย่อน) matched to units scattered across 62777's per-deduction sections. Compared after stripping `Q n :` / `A n :` labels (62777 restarts numbering per sub-topic, so labels always differ) and whitespace: 10 identical, 3 differ in wording only, 7 differ in substance. In the substantive ones 62149 is the older revision even though its title says ปี 2563: own health insurance 15,000 (2560) vs 25,000 (2563), RMF 15% with minimum-purchase rules vs 30% without. The other 55 units of 62149 and 93 of 62777 are unique and kept. The 7 substantive pairs are candidates for evaluation questions on outdated limits.

## Resolved

- **U+FFFD in source HTML** (21 characters: 20 in `61065`, 1 in `61117`; already in the raw HTML, missed by the character-class profile because Python counts U+FFFD as printable): mapped to a space in `normalize`, `61ce262`.
- **60061 dropped a paragraph** (bare `<strong>` outside any `<p>` dropped by trafilatura): fixed in `parse._wrap_bare_inline`, `f0223db`.
- **Gazette page headers left in PDF-derived text** (`เลม่ …`, OCR `หน้า N ราชกิจจานุเบกษา`, repeated page dates): fixed in `clean/gazette.py`, `28628f5`.
- **cp1252 quotes left as control characters** in 38 legal files: fixed in `clean/text.py`, `d4907e7`.
