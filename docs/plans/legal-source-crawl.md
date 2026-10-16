# Plan: collecting statute / legal sources for the PIT RAG

Status as of 2026-10-16. Everything here was found by exploring rd.go.th; nothing in `data/pages.jsonl` was modified.

## What the current corpus covers

- 76 pages: ~45 RD explainer/FAQ pages, ~20 "ข้อหารือ" rulings, and only **ประมวลรัษฎากร ม.38–64 + บัญชีอัตรา** (`5937`, `5938`, `2597`) as statute.
- Not covered: Revenue Code ม.1–37 (ลักษณะ 1, หมวด 1/1 ทวิ/2 — filing, assessment, penalties, appeals), every subordinate instrument, every Act other than the Code.
- Note: `5939` (ม.65–76) is corporate income tax — correctly not crawled.

## Where the law actually lives on rd.go.th

The "รวมกฎหมายภาษี" tree is a hierarchy of listing pages; the leaves are mostly **PDFs** (`/fileadmin/user_upload/kormor/newlaw/*.pdf`) with a few HTML pages.
PIT is mostly implemented *below* the Code, so a Code-only corpus can't answer most deduction/exemption questions:

| Layer | Examples for PIT | Hub page | Items |
|---|---|---|---|
| ประมวลรัษฎากร | ม.40 (8 ประเภทเงินได้), 42 (ยกเว้น), 47 (ลดหย่อน), 48 (หักค่าใช้จ่าย), 50 (หัก ณ ที่จ่าย), 56–57, 59–60 (ยื่นแบบ), ม.27/ม.22 (เงินเพิ่ม/เบี้ยปรับ) | 674 | gap: ลักษณะ 1, หมวด 1, 2 |
| พ.ร.ฎ. (ม.3 เตรส ฯลฯ) | ยกเว้นรัษฎากร: บริจาค, e-Donation, RMF/SSF/Thai ESG, ... | 1603 | 682 |
| กฎกระทรวง | **ฉบับที่ 126 (2509)** (ยกเว้นเงินได้ ~70+ ข้อ), **ฉบับที่ 144 (2526)** (ค่าใช้จ่าย/ลดหย่อน), ช้อปดีมีคืน, ดอกเบี้ยบ้าน | 6160 | 214 |
| ประกาศอธิบดี เกี่ยวกับภาษีเงินได้ | ฉบับที่ 1–471: หลักเกณฑ์ลดหย่อน, หัก ณ ที่จ่าย, แบบ ภ.ง.ด. | 19956 (+27995, 26876, 49231) | ~430 |
| คำสั่งกรมสรรพากร (ป./ท.ป.) | แนวปฏิบัติเจ้าหน้าที่, e.g. ป.161/2566 (เงินได้จากต่างประเทศ) | 1598 | 277 |
| ประกาศ กค. / กรม, คำวินิจฉัย, ระเบียบ | ขยายเวลายื่นแบบ, คำวินิจฉัยคณะกรรมการวินิจฉัยภาษีอากร | 1600, 1597, 1601, 60045 | ~230 |
| พ.ร.บ./พ.ร.ก. แก้ไขประมวลรัษฎากร | ฉบับที่ 1–54, พ.ร.ก. ฉบับที่ 1–19 (e.g. 19/2561 ดิจิทัลฯ) | **62258, 62417** | ~75 |
| พ.ร.บ. อื่นที่ rd.go.th โฮสต์ | ภาษีการรับมรดก 2558, ยกเว้นเบี้ยปรับฯ 2562, กยศ. 2560, พ.ร.ก.แลกเปลี่ยนข้อมูล 2566 (CRS), ภาษีส่วนเพิ่ม 2567 | 61303, 61381, 62015, 63929, 67365 | ~6 |
| คำพิพากษาฎีกา | per-year indexes 2520–2560 | 62653 | ~hundreds |
| ข้อหารือ | per-year/month listings 2540–2569 | 68689 | thousands (already partly crawled) |

The sidebar of `62258.html` is the best map of this section (21 entries); worth adding to `link_decisions.csv` as hubs.

## Statutes **outside** rd.go.th that matter for PIT (candidates)

From domain knowledge — verify titles/years before crawling. Primary source is Council of State (krisdika.go.th) / ราชกิจจานุเบกษา; **both were unreachable/403 from this machine** (krisdika timed out, ratchakitcha returned 403), so use playwright from a browser session, or SEC/SSO/etc. mirrors.

High relevance (a deduction/exemption in the Code refers to them):
- พ.ร.บ.กองทุนสำรองเลี้ยงชีพ พ.ศ. 2530 (+ กฎกระทรวง) — PVD deduction; SEC hosts text (`sec.or.th`)
- พ.ร.บ.กองทุนบำเหน็จบำนาญข้าราชการ พ.ศ. 2539 (กบข.)
- พ.ร.บ.ประกันสังคม พ.ศ. 2533 — social security deduction
- พ.ร.บ.กองทุนการออมแห่งชาติ พ.ศ. 2554 (กอช.)
- พ.ร.บ.ส่งเสริมและพัฒนาคุณภาพชีวิตคนพิการ พ.ศ. 2550 — disability deductions
- พ.ร.บ.คุ้มครองแรงงาน พ.ศ. 2541 — ค่าชดเชย (ยกเว้นเงินได้)
- พ.ร.ป.ว่าด้วยพรรคการเมือง พ.ศ. 2560 — political donation deduction (page `40534` already crawled)
- พ.ร.ก.การประกอบธุรกิจสินทรัพย์ดิจิทัล พ.ศ. 2561 (+ พ.ร.บ.2562?) — crypto income
Medium: พ.ร.บ.การจัดตั้งศาลภาษีอากรฯ พ.ศ. 2528 (disputes); พ.ร.บ.หลักทรัพย์ฯ 2535 (RMF/SSF/ESG funds); อนุสัญญาภาษีซ้อน (DTAs, for foreign income).
Likely out of scope (different tax): ปิโตรเลียม, ทรัพย์สิน/ที่ดิน, ภาษีการรับมรดก (borderline — it is "gift/inheritance", and the user already has the gift-tax explainer), VAT/SBT/stamp.

## Selection method (semantic, not by hub)

1. **Catalogue** (done): parsed 8 listing hubs → `data/legal_catalog.csv` (2,170 unique documents; columns `url, kind, tier, title, hub`). Tier by title keywords: **A** = explicit PIT signal (บุคคลธรรมดา, ลดหย่อน, ม.40–64, ภ.ง.ด., หัก ณ ที่จ่าย, บริจาค, กองทุน…), **B** = generic ภาษีเงินได้/ยกเว้นรัษฎากร, **C** = other taxes or administrative. This is a recall-oriented first filter; titles alone are noisy (e.g. a decree titled only "การยกเว้นภาษี…" is PIT-relevant but scores no signal in its body).
2. **Download** (done): all A+B (1,037) to `data/raw/legal/` (name = sha1(url)[:12] + ext). C is not downloaded.
3. **Full-text scan** (done): `pdftotext` → `data/legal_scan.csv` with counts of PIT vs corporate/VAT/stamp terms. Result across A+B (991 files):
   - 143 are **image-only PDFs (<150 chars) → need Typhoon OCR** (82 A, 61 B). These are mostly the older instruments.
   - Born-digital PDFs extract fine (Thai digits, some letter-spacing artifacts; both fixable in normalisation).
   - Proposed rule: keep all A; keep B only if `pit>0` and `corp <= 2×pit` (213 B), eyeball the 59 corp-heavy B; drop B with no PIT signal (146).
4. **Reference closure**: follow the 108 "ดู…" links from ม.38–64 (80 already `defer`/`อ้างอิงจากประมวล`). These are the instruments the Code itself says implement PIT, so they should all be in, regardless of tier.
5. **Dedupe against corpus**: same document appears under several hubs (e.g. ประกาศอธิบดี under 27995 and 19956).

## Currency / validity metadata (important for answer quality)

Most of these instruments are amended or repealed ("ยกเลิกโดย…", "แก้ไขเพิ่มเติม ฉบับที่ …" appear in titles). Store `kind`, `number`, `year (BE)`, `amends`, `repealed_by` in the record so retrieval can prefer current law and the generator can cite the in-force version. Sunset measures (e.g. ช้อปดีมีคืน 2566, Easy e-Receipt) should carry an applicable-tax-year field.

## Suggested next steps (in order)

1. Add hub pages (sidebar of 62258) and the Revenue Code gaps (ม.1–37 via 2600, 2591, 2599, 2598, 21456 and their per-section pages `59xx`) to `link_decisions.csv`.
2. Run the OCR pipeline (`~/san/ocr/README-typhoon.md`) on the 143 image-only PDFs; re-run `scan.py` equivalent.
3. Hand-review the proposed keep list; sample ~30 for PIT relevance before ingest.
4. Pull the outside-rd.go.th Acts above via a browser session (krisdika) or SEC/SSO mirrors.
5. Decide on ข้อหารือ/ฎีกา scope: thousands of items, mostly VAT/corporate — filter by title `ภาษีเงินได้บุคคลธรรมดา`/`มาตรา 40–64`; this is likely the best answer-bearing source for edge-case questions.
6. Extend `crawler/fetch.py`/`parse.py` to PDFs (text path via `pdftotext`, OCR fallback), writing the same record shape (`url, title, kind, number, year, text`).

## Reproducing

Scripts used live in the Claude session scratchpad, not in the repo; they are small (hub parsing with lxml, keyword scoring, `pdftotext` scan). I can move them into `crawler/src/crawler/` if you want them kept.

## Update: re-tiering after the recall check (`uv run python -m crawler.legal`)

Check: of the instruments the Code cites for ม.38–64, A+B recall was 55/75 (title rules v1) → 73/75 (new rules, same docs) and 99/113 including 38 old HTML pages the hubs don't list. The rules were tuned on this same set, so treat these as optimistic. Changes: income-tax hubs (19956/26876/49231) and คำวินิจฉัย floor at B; added title terms (ณ ที่จ่าย, ยื่นแบบ, มาตรา 17, หนังสือรับรอง); empty-title คำสั่ง take their title from the document's `เรื่อง` line; tier C documents with PIT-heavy body text are promoted to B; documents cited by the Code are tier A. Tier B grew (≈500 → ≈960), so precision now depends on the notebook's body-scan groups and manual review.
