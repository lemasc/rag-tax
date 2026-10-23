# AI Audit — Thai Personal Income Tax Q&A (rag-tax)

**Team:** Saidtach Thanasodsai, Pitsinee Vongsuppatham, Yavitta Thongkliang, Amonwan Kaewsa-rd, 
**AI Tools Used:** Claude Code (as the coding assistant). Inside the system: Typhoon OCR, `typhoon-v2.5-30b-a3b-instruct` (generator), gpt-6-sol, gpt-6-luna, Claude Haiku 5.5 and DeepSeek V4.1 Flash (judges).

**Project at a glance**

- **Domain and corpus:** Thai personal income tax. 173 documents (Revenue Department FAQ pages, Royal Gazette instruments, rulings, filing guides), cleaned and frozen as **2,070 chunks** (`rag/chunks_freeze.json`, enforced by a test). 369 questions in 20 categories, no reference answers.
- **Chunking:** one structural unit per chunk when it fits (FAQ item, มาตรา, ข้อ / `(N)` item, guide section or table), cap **512 bge-m3 tokens** including the header; windows of articles and rulings target 384. No merging of short units.
- **Embedding model:** `BAAI/bge-m3`, cosine, local. Sparse side: BM25 over `newmm` Thai words.
- **Retrieval variants:** dense, sparse, hybrid (RRF, k = 60), dense top 50 + cross-encoder `BAAI/bge-reranker-v2-m3` (the optional extension).
- **Ablations:** E1 dense vs sparse vs hybrid (retrieval only, pooled grading); E1b dense vs dense + reranker; E2 neighbouring clauses (tested, rejected); E3 end-to-end on 130 questions: dense k = 5 (baseline), dense k = 10, no retrieval (a dense + reranker run is not generated yet).
- **Metrics:** retrieval: hit@5, precision@5, MRR@10, nDCG@10, recall@10 against LLM-panel chunk grades. Answers: RAGAS faithfulness, RAGAS answer relevance, a rubric LLM-as-Judge (grounded, correct, useful, behaviour). BERTScore and BLEU/ROUGE are out because there are no reference answers.
- **Judge panel:** luna, Haiku 5.5 and DeepSeek V4.1 Flash, median score (E1 and E2 were graded with gpt-6-sol in luna's seat). None is in the generator's family.

---

## 1. Tool Inventory

| AI Tool | Primary Use in This Project |
| --- | --- |
| Claude Code | Wrote most of the codebase of `crawler/` (extraction, cleaning, unit splitting) and `rag/` (chunker, dense/sparse/hybrid retrieval, answer generation, evaluation, panel, pooled grading, E2/E3 scripts). |
| Gemini | Data spot check and transcribe images (`65908`, `558_0_web`) |
| Typhoon OCR | Text of every Royal Gazette PDF. |
| Typhoon `typhoon-v2.5-30b-a3b-instruct` | The generator for E3 (chosen after a smoke test of five Thai-capable models on 8 dev questions). |
| gpt-6-luna (and gpt-6-sol for E1, E2) | LLM judge: grades (question, chunk) pairs 0/1/2 and scores answers on the rubric. luna also served as the dev-run generator before the panel existed. |
| Claude Haiku 5.5, DeepSeek V4.1 Flash | The other two judges in the panel. |

---

## 2. Prompt Log

The "Prompt sent" lines are left for you: paste the exact text from your own sessions (Claude Code keeps them under `~/.claude/projects/`). The other two fields are written from `docs/` and the findings log in the appendix.

### Entry 1: splitting FAQ pages and legal instruments into units

**Prompt sent:**

> เนื้อหาตอนนี้มีหน้า FAQ ที่ถามตอบยาวหลายหน้า ลองแบ่งเป็นข้อๆ หน่อย

**What AI generated:**
A splitter that assumed every FAQ page numbers its section headings and every answer starts with `คำตอบ` at line start; and exploratory regexes that reported 9 of 18 FAQ pages with mismatched question/answer counts.

**What you changed or rejected:**
Rejected the profile: its three claimed defects (count mismatches, a numbering gap in `60062`, a missing title in `60061`) were false. The splitter now accepts the marker variants that exist in the source (`3..ชื่อเรื่อง`, `1. .ชื่อเรื่อง`, answers glued to the question, and so on), numbered-heading mode only applies when the page's first heading is numbered, and a property test checks no text is lost or added. Tests name the real pages that show each variant.

### Entry 2: transcribing the 2568 allowance poster

**Prompt sent:**

> มีข้อมูลโปสเตอร์การเสียภาษีประจำปีแต่เป็นรูปภาพ ช่วยแปลงเป็นข้อความให้หน่อย

**What AI generated:**
A Markdown transcription of the poster, the only source of the current allowance amounts.

**What you changed or rejected:**
The OCR text and the first transcription both had errors: a missing `60,000 บาท`, one amount serving two rows, a lost brace label, a duplicated donation row, and invented values (a `100,000 บาท` limit for the CCTV row, a `ตามที่จ่ายจริง` for the public-hospital donation). A person compared the text with the image and set it `verified` (`3bf2869`). The same control was applied to `558_0_web` (`3239afb`).

### Entry 5: the top-50 diagnostic and its second round

**Prompt sent:**

> อยากรู้ว่าตอนนี้แต่ละ chunk ให้คะแนนผลลัพธ์ดีไม่ดียังไง มีหน้าให้ดูง่ายๆ มั้ย

**What AI generated:**
A pooled-grading design (dense top 50 ∪ sparse top 50, three-judge panel), a human check showing at most three chunks per miss question, and, for round 2, eight chunks picked by keyword search.

**What you changed or rejected:**
Round 1's verdict ("mostly the corpus", D = 9 of 13) was withdrawn: it only showed that the first three panel picks did not answer. Round 2 added the chunks found by search; the verdict became **mixed** (D 5, B 7, A 1), which moved the work toward ranking (a reranker, k = 10). The round-2 picks were chosen by Claude, so the selection is not blind; only the grades are the reviewers'.

---

## 3. Decision Journal

Owners are for you to fill in by hand. The "Docs say" note under each reason is what the repo records, not a claim about who decided.

| # | Decision | Owner | Reason (in your own words) |
| --- | --- | --- | --- |
| 1 | Chunk = one structural unit, cap 512 bge-m3 tokens, no merging of short units | [AI-suggested, Human-approved] | The cap comes from the corpus's units (1,587 of 1,661 stay whole at 512; a bigger cap only merges whole units, a smaller one splits clauses mid-sentence); a 60-token clause answers its question exactly.|
| 2 | Embedding model `BAAI/bge-m3` (dense, local) | [AI-decided] | It runs locally, so retrieval needs no API, and it takes 8,192 tokens, so the chunk cap is set by the corpus's units, not by the model. |
| 3 | Dense as the E3 baseline instead of hybrid | [Human] | E1: dense ≥ hybrid (nDCG@10 .695 vs .664, recall@10 .686 vs .608 outside the interval; hit@5 inside). RRF puts every both-lists chunk above every one-list chunk, and BM25 misses colloquial wording. |
| 4 | Add the cross-encoder reranker (`bge-reranker-v2-m3`, dense top 50 → top 10) | [AI-decided] | E1b: hit@5 .687 → .794 (+.106 [+.062, +.153]), nDCG@10 +.096. It reads question and chunk together, so it lifts the chunk that states the rule over lookalikes. 7 of 13 dev misses had an answer at ranks 6 to 50.|
| 5 | Metrics: RAGAS faithfulness, RAGAS answer relevance and a rubric LLM-as-Judge (BERTScore and BLEU/ROUGE not used) | [Human] | There are no reference answers, so every answer metric needs an LLM judge; the assignment lists the RAGAS metrics; the plan leaves open whether to use the `ragas` library or a direct implementation (about 100 lines, easier to explain in the Q&A).|
| 6 | Judge panel of three different families, median score | [Human] | A single judge already agreed with people as well as people agree with each other (57 to 66% exact), so the panel is for independence from the generator's family, not noise reduction.|
| 7 | Replace gpt-6-sol with gpt-6-luna in the panel from E1b | [Human] | sol was about 70% of the judge bill; luna is a twentieth of the price. Pass rules fixed before the run; luna agreed with sol .804, the highest of any pair, and the mode ranking did not change.|
| 8 | Drop neighbouring clauses from E3 | [AI-suggested, Human-approved] | E2: gain +.06 [+.02, +.10] on clauses, below the pre-agreed 10 points; later parts +.00; noise floor about 10%.|
| 9 | Typhoon OCR as the default for Gazette PDFs | [Human] | `pdftotext` had lost `ำ` in 8 of 17 documents and the dictionary metric did not show it.|
| 10 | Typhoon as the E3 generator; luna kept as judge only | [Human] | A Qwen3-based model from a family none of the judges is in, so no judge grades its own family; the smoke test kept it, and removed two models that accepted a false premise (Q0366).|

---

## 4. Error Catch Log

Seven errors, strongest first. Each is also in the appendix with files and tests. In the appendix "I" means the AI assistant.

### Error 1: judge scores from one rubric version compared with human labels from another

**What the AI said:**
After running `--compare` it reported the judge's agreement with the humans (grounded 68%, correct 56%, useful 70%) and a conclusion built on it.

**Why it was wrong:**
The saved scores came from judge rubric v1 and the human labels from v2, and the comparison also pooled 21 labels made before v2 (81 pairs, not 60). `scores_config.json` said `judge_version: "v1"` and was never read. An agreement figure between two different measuring instruments says nothing about judge validity (the core of LLM-as-Judge evaluation). Re-scoring under v2 changed 7 of 40 grounded, 10 of 40 correct and 1 of 40 useful scores; the real agreement is grounded 72%, correct 67%, useful 70%.

**How you fixed it:**
`--compare` uses only labels made under the current rubric and stops when the scores' judge version differs from the labels'; `rag/panel.py` refuses to combine judges scored under different versions. The same discussion withdrew the claim that a panel "reduces noise".

### Error 2: a "mostly the corpus" verdict drawn from the first three chunks

**What the AI said:**
Round 1 of the top-50 diagnostic gave D = 9 of 13 (exactly the pre-registered threshold), and it told the user the result "mostly points at the corpus" and that the reranker ablation was worth much less.

**Why it was wrong:**
The human check showed at most three panel-picked chunks per miss question. A question was class D when none of those three was graded 2, which means "the first three picks don't answer", not "nothing answers": the panel had given a 2 to between 2 and 17 chunks on those questions, never read by a person. A keyword search found several (Q0329 `5937#042` at rank 27, Q0301 `552~001` at rank 31). The judged pool is also relative: recall measured on it cannot see chunks outside it.

**How you fixed it:**
Round 2 graded the chunks found by the search; the verdict became mixed (D 5, B 7, A 1) and the reranker went ahead. E1b later confirmed it (+.106 hit@5).

### Error 3: OCR text that lost and invented amounts

**What the AI said:**
The OCR text of the 2568 allowance poster looked complete and was kept; the AI's own first transcription was then presented as a faithful copy.

**Why it was wrong:**
The transcript lost `ส่วนตัว 60,000 บาท`, reused one amount for two rows, dropped a brace label, duplicated a row, and invented a `100,000 บาท` limit and a `ตามที่จ่ายจริง` the poster does not state. In a tax corpus an invented amount is a faithfulness failure by construction: the generator would cite it as the source. No automatic check can see a missing or invented row, and the model that transcribed is not independent of the one that misread.

**How you fixed it:**
Stored as `source = manual`, flagged `unverified` until a person compared it with the image (`verified`, `3bf2869`); regression test `test_65908_text_is_the_corrected_one`.

### Error 4: a dictionary metric said the PDF text was clean

**What the AI said:**
Judged `pdftotext` by out-of-dictionary tokens per 1k (median 37.4 against OCR 6.5), and repaired tone-mark order with rules.

**Why it was wrong:**
In 8 of the 17 pdftotext documents the text layer has no `ำ` at all (`กาหนด`, `คานวณ`, `สาหรับ`). The pieces are valid words, so `e9c223c3262b` and `0735ac19649b` scored OOV 0.0. The metric measures "is each token a word", not "is this the word the author wrote". Wrong text here makes both BM25 tokens and bge-m3 embeddings wrong.

**How you fixed it:**
Re-OCR'd 5 documents and read the word-level diff, then counted `ำ` in all 17; PDFs now use Typhoon OCR by default. The rule-based repairs stay in `rejoin.py` but no document uses them.

### Error 5: HTML text extracted without its line structure

**What the AI said:**
`extract.html_text` took `text_content()`, dropping every tag, and the AI described the resulting flat lines as "a property of the source", the opposite problem to OCR's short lines.

**Why it was wrong:**
An amending กฎกระทรวง keeps its items in one `<p>` split by `<br>`, so everything came out as one line. The clause splitter matches at line starts, so 77 documents got no clause units: all 388 of their chunks were windows (80% of the 483 legal chunks), cut at arbitrary phrase breaks. 79 of the 200 chunks retrieved in one dev run were such windows. Chunk boundaries should be boundaries of the source; here they were not.

**How you fixed it:**
`5f7de65` breaks lines at `<br>` and block elements (lines 1,020 → 4,839; text identical apart from whitespace), chunks rebuilt and frozen (`2059934`), and `rag/chunk_version.py` guards runs made on earlier chunks. Not known: whether the old windows cost recall; earlier dev runs were not repeated.

### Error 6: trafilatura dropped a paragraph from an FAQ answer, and the first write-up was wrong too

**What the AI said:**
First: page-level checks were "fine". Then: trafilatura "cut the tail of the first answer", caused by a `<strong>` inside a `<p>`.

**Why it was wrong:**
The loss was a whole last paragraph of item 4 (`60061`; the spouse's social-security deduction under ม.47(1)(ฌ)), and the cause is a bare `<strong>` that is a direct child of a `<div>`. The extracted answer read as if only the taxpayer's own contributions count, which is a wrong answer from a correct retrieval.

**How you fixed it:**
`parse._wrap_bare_inline` wraps such nodes in `<p>`; re-extracting all 76 pages changes exactly one record (`60061`, +244 characters). A test on the real page fails without the fix. A synthetic-HTML test passed even with the fix disabled, so it was dropped.

### Error 7: the generator leaks Chinese into Thai answers

**What the AI said:**
Typhoon (Qwen3-based) produced Thai answers that contain 申报 ("file a return"), 免税, 导致 and similar, in 10 of 131 answers at k = 5, 9 at k = 10 and 38 without retrieval.

**Why it was wrong:**
It is random per question, not a call fault: 9 single-turn cases leaked in 14 of 27 retries, 12 clean questions in 0 of 24, and a "Thai script only" prompt rule still leaked on 4 of 9. Typhoon is also not deterministic at temperature 0, so runs reproduce only through the cache. An uncontrolled script switch changes what the judges read.

**How you fixed it:**
The raw runs stay as the record. The scored runs (`-sr3`) retry an answer up to 3 times until it has no CJK script; records keep `tries` and `foreign_script`, and the report states the answers were selected this way. 5 still leak at k = 5, 4 at k = 10 and 14 without retrieval, so the no-retrieval gap must be re-checked without them.

---

## 5. Contribution Map

Git history cannot split the work: every commit uses one shared account, and several people used the machine over SSH. Fill in each row by hand.

| Team Member | Human Contribution | AI Tools Used |
| --- | --- | --- |
| Sakditach | corpus collection and crawl, text extraction, cleaning |  |
| Pitsinee | chunking, dense/sparse/hybrid retrieval, reranker |  |
| Amonwan | generation, evaluation harness, judge panel, human labelling |  |
| Yavitta | ablation design, failure analysis, slides |  |

---

## 6. What Would Break? (Answer WITHOUT using AI)

These are for you to answer in your own words, without an assistant. The system details are filled in so the question is specific.

**a)** If you removed the reranker (`BAAI/bge-reranker-v2-m3`, applied to dense's top 50 to give the top 10) from your pipeline and kept plain bge-m3 dense retrieval, what specifically changes in output quality and why?

ถ้าตัด reranker ออกแล้วใช้ bge-m3 dense ล้วน คุณภาพจะแย่ลงแบบวัดได้
หลายๆ คำถามที่เดิมมี chunk ตอบถูกอยู่ใน top 5 จะไม่มีแล้ว
สาเหตุเพราะ bi-encoder มองคำถามกับ chunk แยกกัน
- bge-m3 สร้างเวกเตอร์ของ chunk โดยไม่รู้คำถาม แล้ววัดแค่ระยะห่างของสองเวกเตอร์ chunk ที่หัวข้อตรงแต่กฎผิด จึงอยู่ใกล้พอๆ กับ chunk ที่ตอบจริง ในคลังภาษีมีตัวอย่างที่เป็นปัญหาคือตัวอย่างการคำนวณ และกฎลดหย่อนข้างเคียง
- cross-encoder อ่านคำถามกับ chunk พร้อมกัน bge-reranker-v2-m3 จึงแยกได้ว่า chunk ไหน ระบุกฎที่ถูกถาม แทนที่จะแค่พูดเรื่องเดียวกัน
- จากการตรวจ human review คำตอบมักอยู่ใน rank 11–50 อยู่แล้ว (7 จาก 13 คำถามที่พลาดมี chunk ตอบอยู่ใน rank 6–50) ซึ่ง reranker ดึงขึ้นมาได้

**b)** Why did you cap chunks at 512 bge-m3 tokens (windows target 384)? What would happen to retrieval quality if you used 1,024 tokens, or 256?

ดูจาก distribution ของความยาวเอกสาร เดิมทีมีความยาวที่น่ากังวล และมีปัญหาตัดคำกลางประโยคค่อนข้างบ่อย
แต่หลังจากทำ semantic chunking จนมั่นใจแล้วดู distribution ใหม่ พบว่าความยาว 512 สามารถจัดเก็บ chunk ได้มากพอ

ตัวเลขจากข้อมูล:
- FAQ อยู่ครบ 522 จาก 530
- ข้อของกฎหมายอยู่ครบ 863 จาก 885
- หัวข้อคู่มือกรอกอยู่ครบ 155 จาก 189
- มาตราของกฎหมายอยู่ครบ 36 จาก 43

หากขยับมากขึ้นเช่นเป็น 1,024 จำนวน chunk จะน้อยลง คาดว่า recall ไม่เพิ่ม และ precision น่าจะลดลง เพราะรวมกันทำให้ข้อกฎหมายหรือปรากาศที่ไม่เกี่ยวข้องติดมาด้วย
หรือหากน้อยเกินไปเป็น 256 จะทำให้เกิดเคสตัดกลางคำดังที่เคยเจอมา
เงื่อนไขที่ต้องใช้เพื่อตอบคำถาม ก็จะไม่ครบถ้วน เสียหายกับข้ออื่น ๆ ด้วย

**c)** Your ablation compares dense, hybrid (dense + BM25 with RRF k = 60) and dense + reranker. Pick the result that surprised you most and explain the mechanism behind it, not just "variant A scored higher" but why technically.

hybrid ไม่ชนะ dense เพราะเป็นผลที่ขัดกับความคาดหวังทั่วไปมากที่สุด
ตอนแรกคิดว่าเกิดจากข้อมูลไม่เพียงพอ แต่หลังจากพิจารณาคู่กับชุดคำถามที่มีแล้วยังสรุปไม่ได้
RRF ทำให้กรณีที่อยู่ทั้งสองลิสต์ชนะอันดับสูงเสมอ แต่ส่วนที่ตัดกันเต็มไปด้วย chunk ที่ดูคล้ายแต่ผิดกฎ
นอกจากนี้ คำถามส่วนใหญ่เป็นภาษาพูด แต่ chunk ที่เป็นภาษากฎหมายจับตรงๆ ไม่ได้
แม้จะทดสอบในหลายกรณีก็ยังไม่สามารถสรุปได้ชัดว่าสาเหตุมาจากสิ่งใด