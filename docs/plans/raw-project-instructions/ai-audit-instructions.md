# AI Policy

You **may** use any AI tool for any part of this project. This is intentional. The constraint is that you must be able to:

1. Explain every component of your system to a technical audience
2. Trace every design decision (chunk size, embedding model, metric choice) to a reason
3. Answer an individual technical question during the presentation without AI assistance

Using AI to generate boilerplate code is fine. Using AI to make decisions you cannot explain is a grading risk — the Q&A will expose it.

---

## AI Audit Instructions

Create a file named `AI_AUDIT.md` in your repository root. Fill it out honestly using the structure below. Vague or generic answers score zero — the checker looks for specific technical language tied to your actual system.

---

```md
# AI Audit — [Your Project Title]

**Team:** [Names]
**AI Tools Used:** [List all tools]

---

## 1. Tool Inventory

| AI Tool           | Primary Use in This Project                                 |
| ----------------- | ----------------------------------------------------------- |
| e.g., Claude Code | Generated BM25 retrieval class, debugged RRF merge function |
| e.g., ChatGPT     | Explained cross-encoder vs. bi-encoder tradeoff             |

---

## 2. Prompt Log (minimum 5 entries) |

For each significant AI interaction, record the actual prompt and what you did with the output.

### Entry 1

**Prompt sent:**

> [paste the exact prompt you gave the AI]

**What AI generated:**
[Summarize or paste the key output]

**What you changed or rejected:**
[Be specific — did you change variable names, fix an incorrect API call, restructure the logic, reject a suggested approach?]

---

[Repeat for entries 2–5+]

---

## 3. Decision Journal (minimum 5 decisions)

For each key design decision, record who made it and why.
Use: [Human] / [AI-suggested, Human-approved] / [AI-decided]

| #   | Decision                | Owner | Reason (in your own words)                                                  |
| --- | ----------------------- | ----- | --------------------------------------------------------------------------- |
| 1   | Chunk size = 512 tokens | Human | Longer chunks lost precision in our legal domain; tested 256 vs 512 vs 1024 |
| 2   | ...                     | ...   | ...                                                                         |

---

## 4. Error Catch Log (minimum 2 entries)

Describe cases where the AI was technically wrong.

### Error 1

**What the AI said:**
[Quote or summarize the incorrect suggestion]

**Why it was wrong:**
[Cite the course concept or technical reason — e.g., "AI used dot product without normalization, which is incorrect for cosine similarity retrieval"]

**How you fixed it:**
[What you actually did]

---

[Repeat for error 2+]

---

## 5. Contribution Map

| Team Member | Human Contribution                     | AI Tools Used  |
| ----------- | -------------------------------------- | -------------- |
| [Name 1]    | Corpus collection, chunking strategy   | Claude Code    |
| [Name 2]    | BM25 + RRF implementation              | GitHub Copilot |
| [Name 3]    | Evaluation harness, BERTScore analysis | ChatGPT        |
| [Name 4]    | Presentation, ablation design          | Antigravity    |

---

## 6. What Would Break? (Answer WITHOUT using AI)

Answer all three questions in your own words.

**a)** If you removed the reranker (or your second retrieval stage) from your pipeline, what specifically changes in output quality and why?

**b)** Why did you chunk your documents at [X] tokens? What would happen to retrieval quality if you used 2× or ½ that size?

**c)** Your ablation compares two system variants. Pick the result that surprised you most and explain the mechanism behind it — not just "variant A scored higher" but why technically.
```

---

## Standardized AI Audit Generation Prompt

Everyone must use this exact prompt to generate their `AI_AUDIT.md` skeleton. Copy it into Claude Code, Antigravity, or any AI tool, fill in the `[BRACKETS]` with your project details, then run it. The AI will produce a pre-structured skeleton — you then go through every `[FILL IN: ...]` placeholder and replace it with your real content.

Using this shared prompt ensures all audits have the same format and can be checked consistently.

```
You are helping me create an AI Audit document for my NLP course term project.

My project details:

- Project title: [TITLE]
- Team members: [NAME 1], [NAME 2], [NAME 3], [NAME 4]
- Domain: [e.g., Thai university regulations / legal documents / medical guidelines]
- AI tools we used: [list all tools and their primary role]
- Corpus: [describe your documents what they are, how many, what language]
- Embedding model chosen: [e.g., sentence-transformers/paraphrase-multilingual-mpnet-base-v2]
- Chunk size and overlap: [e.g., 512 tokens with 50-token overlap]
- Retrieval approach: [e.g., dense-only / BM25 + dense hybrid with RRF / + cross-encoder reranker]
- System variants compared in ablation: [e.g., Variant A: dense-only vs. Variant B: dense + BM25 hybrid]
- Evaluation metrics used: [e.g., BERTScore + LLM-as-Judge]
- Optional extensions implemented: [e.g., none / LoRA fine-tuning / GraphRAG]

Generate a complete AI_AUDIT.md file in GitHub-flavored Markdown with these exact six sections:

1. Tool Inventory — a table listing each AI tool and its primary role in this project
2. Prompt Log — 5 entries, each with subsections: "Prompt sent", "What AI generated", "What you changed or rejected". Pre-fill the project context in the headers but leave the actual prompts and outputs as [FILL IN: paste the real prompt you sent] and [FILL IN: summarize what the AI produced]
3. Decision Journal — a table of 5 rows for key design decisions with columns: #, Decision, Owner ([Human] / [AI-suggested, Human-approved] / [AI-decided]), Reason. Pre-fill the Decision column with the actual decisions from my project details above (chunk size, embedding model, retrieval approach, evaluation metrics, ablation design). Leave Owner and Reason as [FILL IN: ...]
4. Error Catch Log — 2 entries with subsections: "What the AI said", "Why it was wrong", "How you fixed it". Leave all content as [FILL IN: ...] — do NOT invent errors
5. Contribution Map — a table with columns: Team Member, Human Contribution, AI Tools Used. Pre-fill the team member names. Leave contributions as [FILL IN: ...]
6. What Would Break? — three questions pre-filled with our specific system details:
    a) Refer to our actual second retrieval stage or reranker if we have one, or dense retrieval if not
    b) Reference our actual chunk size of [X] tokens
    c) Reference our actual two ablation variants by name

#### IMPORTANT RULES:

- Do NOT fabricate or invent any prompt content, error descriptions, or decisions
- Every piece of real content must be a [FILL IN: ...] placeholder
- Use our actual project details (model name, chunk size, domain, etc.) wherever the structure allows
- Output ONLY the markdown file — no explanations before or after
```

After running this prompt, you will have a skeleton file. Replace every `[FILL IN: ...]` with real content from your project. The final submitted `AI_AUDIT.md` must have no remaining placeholders — any unfilled section scores zero.