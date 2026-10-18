# Topic exploration (sparse and dense)

Status: first pass 2026-10-18. Code in `analysis/` (`chunks.py`, `topics.py`, `show.py`); run from the repo root with `uv run python analysis/<script>.py`. Outputs in `analysis/out/` (`emb.npy` is gitignored).

## Setup

- Root `pyproject.toml` (uv, `package = false`) with dependency groups `crawler`, `analysis`, `dev`. `crawler/` is unchanged and keeps its own project; `pytest` finds it through `pythonpath`.
- torch is pinned to the **cu126** index: the driver reports CUDA 12.6 and PyPI's default wheel is cu130 (`torch.cuda.is_available()` was False until pinned). GPU is an RTX 4070 12 GB. The Typhoon OCR vLLM server held ~11.8 GB and was stopped (`~/san/vllm/serve_typhoon.sh stop`); restart it if OCR is needed again.

## Method

1. `chunks.py`: **provisional** chunks. Existing units (FAQ, statute) as-is; documents without units are cut into paragraph windows of at most 1,200 characters. 1,375 chunks; 100 flagged `dup_of` (8-character shingle Jaccard ≥ 0.8 against an earlier chunk in another document), leaving 1,275 for modeling. Token counts use the bge-m3 tokenizer.
2. `topics.py`: sparse = PyThaiNLP newmm, TF-IDF (min_df 3, max_df 0.4), NMF k=16. Dense = bge-m3 embeddings (GPU, 15 s), UMAP 5-d, HDBSCAN (min_cluster_size 12) and KMeans k=16. Dense clusters labelled with class-based TF-IDF.

## Findings

**Length (bge-m3 tokens).** Windows are 260–300 tokens median (p90 about 340, max 465). FAQ items: median 94, p90 234, max 1,787. Statute sections: median 170, p90 1,404, max 2,505. 13 chunks exceed 512 tokens, 25 are under 30.

**Duplicates.** FAQ pages `61081` and `61065` are 98% identical (74 units each); `62149`/`62777` share 18 units; a few amending instruments share text. Flagged, not deleted from `chunks.jsonl`.

**Topics both methods agree on** (all FAQ/article-heavy): dependants (children, parents, disabled), life/health insurance and pension, mortgage interest, RMF/fund investment, donations (including political parties), spouses/filing status, e-filing and passwords, payment and instalments, refunds (PromptPay), expense deduction (flat rate vs actual), dividends and credit.

**Where they differ.** Agreement is moderate (ARI 0.30, NMI 0.50 between NMF and KMeans at k=16). Dense clusters split by *document family* and sub-topic more finely (44 HDBSCAN clusters, 169 noise chunks); the sparse model mixes families around shared vocabulary (for example one NMF topic holds FAQ and กฎกระทรวง chunks about RMF). Dense separated two different insurance sub-topics (health vs life vs pension) and a Host-to-Host filing notice that NMF merged into a generic "ยื่น/ระบบ" topic.

**Coverage and balance.**
- 10 documents hold 44% of chunks. The largest: `61549` (121), `62777` (95), `62149` (75), `61081` (74), `f41021ec0cf8` (53).
- `f41021ec0cf8` is the one titled "ฉบับที่ 380" that holds consolidated ฉบับที่ 126 (see AI_AUDIT.md, mislabelled listings). its 53 chunks (exemption lists, province lists) sit largely in one dense cluster with other กฎกระทรวง chunks (cluster 8, 50 of 51 chunks are กฎกระทรวง).
- **Scope drift:** several legal clusters are not personal income tax: tobacco wholesalers, corporate deductions for insurance agent commissions (ป.115/2545, ป.124/2546), securities-firm withholding, VAT, film actors (this one is PIT-relevant), training deductions for companies. A dozen dense clusters read as corporate or other taxes from their top terms alone (not hand-checked, so the count is a rough estimate). A relevance filter on legal instruments is a decision still to make.
- Thin or absent topics: tax rate schedule and the progressive calculation (a few `article` chunks only), penalties and surcharges, capital gains from securities, and anything after 2568 apart from the few 2566–2568 กฎกระทรวง.

**Text-quality defects that leak into topics.**
- OCR/PDF text still has letter-spaced and split Thai ("ใ ช้", "รหัส ผ่า น", "ถอด อ๋า" as a top term). They produce junk tokens for the sparse model and noise for dense. Related to open item 1.
- Many legal chunks are only a list of provinces, numbered clauses or tables; they cluster by form, not meaning.

## What this implies

- Sample evaluation questions per topic, not per chunk, or the three big Clear Cut pages will dominate.
- Chunk size: windows of about 300 tokens look reasonable for the legal text; FAQ items (median 94) need no splitting but the long tail (up to 1,787) and long statute sections (p90 1,404) do. The token-aware chunker should keep Q+A together and split sections at sub-paragraphs.
- Decide a relevance rule for non-PIT instruments before building the index; otherwise retrieval will return corporate-tax text for PIT questions.
- Drop `61065` as a duplicate of `61081`, and review the 18 shared units between `62149` and `62777`.

## Not done

- No k sweep or coherence score; k=16 was chosen by eye. Topic labels are top terms only, nobody has hand-named or hand-checked them.
- Sparse model has no phrase handling (e.g. "ภ.ง.ด. 90" is split).
- No viewer notebook yet.
