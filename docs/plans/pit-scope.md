# PIT scope of legal documents

Status: rule drafted 2026-10-18, **not yet agreed**; no document labelled. The core legal set is "every document the Code cites from ม.38–64" (`crawler/data/legal_core.csv`). A citation from a PIT section does not make a document about personal income tax: withholding instruments under ม.50 and similar sections also cover corporate payers, and the first topic pass found clusters on tobacco wholesalers, insurance-agent commissions for companies, securities-firm withholding and VAT (`docs/plans/topic-exploration.md`). This file holds the rule each label is made against.

## Rule

<!-- the legal review notebook shows this section above the scope panel; keep it short -->

Label a document by what it lets a reader answer about **personal income tax** (ภาษีเงินได้บุคคลธรรมดา).

- **pit**: it sets or explains how a taxpayer under ม.56 (a natural person, ห้างหุ้นส่วนสามัญ / คณะบุคคล that is not a juristic person, กองมรดกที่ยังไม่ได้แบ่ง) computes income, expenses, deductions or exemptions, files (ภ.ง.ด.90/91/94) or pays. Withholding on income paid **to natural persons** counts (ภ.ง.ด.1/2/3, 50 ทวิ certificates): it is the taxpayer's credit.
- **non_pit**: it only concerns corporate income tax (นิติบุคคล, ภ.ง.ด.50/51), withholding on payments to juristic persons (ภ.ง.ด.53/54), VAT, specific business tax, stamp duty or excise, or a deduction only a company can claim.
- **mixed**: some clauses are PIT and some are not. Keep it and list the PIT clauses (`ข้อ 1–3, 5`) so the unit splitter can filter later.

When unsure, label **mixed** with a note rather than guess: mixed keeps the text in the index.

## How labels are used

- Recorded in `crawler/data/legal_scope.csv` (`url, scope, pit_clauses, note, decided_at`) from the scope panel in `crawler/notebooks/legal_review.py`. The file is hand-maintained; no script regenerates it.
- `crawler.clean.build` copies `scope` and `pit_clauses` onto each legal document. `non_pit` sets `include = false` (still visible in the clean viewer); `mixed` and unlabelled documents stay in.
- "Scope filter on / off" is a ready ablation: build the index with and without the `non_pit` exclusion.

## Where to start

Documents with more corporate than PIT keyword hits (`corp` > `pit` in the notebook's catalogue table), then the documents in the dense topic clusters that read as non-PIT (`analysis/topic_viewer.py`). There is no need to read all 110.
