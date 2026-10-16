# Term Project: Domain-Specific Intelligent Q&A System

Course: Natural Language Processing with Deep Learning

Weight: 15% of final grade

Group Size: 3–4 students

Presentation Date: Week 15

Presentation Slot: 10 minutes per group (demo) + 5 minutes (Q&A)

## Overview

You will design, build, and evaluate a domain-specific intelligent Q&A system grounded in the retrieval and evaluation techniques taught in this course. The system must operate on a real-world corpus of your choosing and demonstrate that you understand the pipeline — not just that you can call an API.

Because you are free to use AI tools (Claude Code, Antigravity, ChatGPT, Copilot, or any others), the grading focuses on understanding and decision-making, not lines of code. Every technical choice in your system must be something you can explain, defend, and modify on the spot.

## Theme & Constraints

### Domain (Your Choice)

Pick a real-world domain where a Q&A system would be genuinely useful. Good examples:

- Thai university regulations or student handbooks
- Legal documents (Thai civil code, contracts)
- Medical or clinical guidelines
- Academic papers in a specific subfield
- Company or government policy documents
- Technical product manuals

The corpus must be real (not synthetic), contain **at least 50 documents or equivalent**, and be in a language your team can actually read and evaluate.

## Mandatory Technical Stack

Every group must implement **all** of the following:

| #   | Component                  | Details                                                                                                                           |
| --- | -------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Text corpus & chunking** | Real documents, token-aware chunking with a justified chunk size                                                                  |
| 2   | **Dense retrieval**        | SentenceTransformers embedding model (CPU-compatible)                                                                             |
| 3   | **Evaluation harness**     | At least **2 metrics** from the course: BERTScore, BLEU/ROUGE, LLM-as-Judge, RAGAS Faithfulness, RAGAS Answer Relevance           |
| 4   | **Ablation study**         | Compare at least **2 system variants** (e.g., dense-only vs. hybrid, with/without reranker) and explain the difference in results |

### Optional Extensions (improve your grade)

| Extension                           | Recommended if...                                               |
| ----------------------------------- | --------------------------------------------------------------- |
| BM25 hybrid retrieval + RRF merging | You want stronger retrieval performance                         |
| Cross-encoder reranking             | You want higher precision on top-k results                      |
| LoRA fine-tuning on a small model   | Your team has GPU access and wants to explore domain adaptation |
| GraphRAG or multi-hop retrieval     | Your domain has structured relational data                      |
| Agentic loop (tool-calling)         | Your system needs to handle multi-step queries                  |

You are not required to implement extensions, but a system that only meets the mandatory stack will score in the average range.

## Deliverables

Submit all three items before your Week 15 presentation slot:

### 1. Code Repository

A clean, runnable codebase with:

- A `README.md` explaining how to install dependencies and run the system
- A working demo script or notebook (`demo.ipynb` or `demo.py`)
- Your evaluation script with results saved to a file

### 2. Presentation Slides (10 slides max)

Structure your slides as follows:

| Slide | Content                                                                          |
| ----- | -------------------------------------------------------------------------------- |
| 1     | Title, team members, domain chosen                                               |
| 2     | Problem motivation — why this domain needs a Q&A system                          |
| 3     | System architecture diagram (your full pipeline)                                 |
| 4–5   | Key technical decisions (chunking strategy, embedding model, retrieval approach) |
| 6–7   | Ablation results — your table or chart comparing variants                        |
| 8     | Evaluation results with at least 2 metrics                                       |
| 9     | Failure analysis — what breaks and why                                           |
| 10    | AI Audit highlights (3 most important decisions + 1 error catch)                 |

> **No code dumps on slides.** Architecture diagrams and result tables only.

### 3. AI Audit (`AI_AUDIT.md`)

This is a **separate deliverable** submitted alongside your code. See [AI Audit](./ai-audit-instructions.md) section for the exact format. The audit is graded independently using an automated checker — completeness and technical honesty matter more than polish.

---

## Rubric

| Criterion                     | Points | What Earns Full Credit                                                               |
| ----------------------------- | ------ | ------------------------------------------------------------------------------------ |
| System works on real corpus   | 15     | Live demo runs, corpus is non-trivial, chunking is justified                         |
| Technical depth               | 25     | Pipeline goes beyond single API call; team can explain each component                |
| Ablation quality              | 20     | Results table is correct; interpretation explains the mechanism, not just the number |
| Evaluation rigor              | 15     | ≥2 metrics used correctly; team understands what each metric measures                |
| AI Audit score                | 15     | Audit is specific, honest, and shows real technical engagement                       |
| Presentation & individual Q&A | 10     | Slides are clear; each member answers their individual question correctly            |

**Total: 100 points → 15% of course grade**

> The individual Q&A accounts for a portion of the Presentation score. Each team member will receive one technical question during the presentation. The question is assigned randomly and must be answered individually without group assistance.

## Presentation Format

Total slot: 15 minutes per group (10 min presentation + 5 min Q&A)

### Part 1 — Presentation (10 minutes)

| Time         | Activity                                              |
| ------------ | ----------------------------------------------------- |
| 0:00 – 1:00  | Problem intro & domain motivation                     |
| 1:00 – 4:00  | System walkthrough (architecture + key decisions)     |
| 4:00 – 7:00  | Live demo                                             |
| 7:00 – 10:00 | Ablation results, evaluation scores, failure analysis |

### Part 2 — Individual Q&A (5 minutes)

After the presentation ends, each team member receives one technical question assigned randomly. You answer individually — no group discussion, no AI assistance. Each member has approximately 1 minute to answer.

Questions are drawn from a bank covering: retrieval mechanics, evaluation metrics, system design decisions, and core NLP concepts applied to your specific system. The question will be about your system — not generic trivia. If you built it, you should be able to answer it.

Keep the demo short and focused. A system that works on 3 example queries is better than a broken demo of 10 queries.

---

## Advice

**On choosing your domain:** Pick something at least one team member genuinely cares about. You will spend many hours with this corpus. A motivated team that chose an interesting domain consistently outperforms a team that picked something "easy."

**On the ablation:** Do not run it the night before. The ablation is how you demonstrate that you understand your system. Run early, interpret the results, and prepare to explain them.

**On the AI Audit:** Write it as you build, not at the end. Reconstructing prompts from memory produces vague logs that score poorly.

**On the Q&A:** The question will be about your system specifically — not a generic NLP trivia question. If you built it, you should be able to answer it. If your teammate built it and you cannot explain it, that is a grading signal.
