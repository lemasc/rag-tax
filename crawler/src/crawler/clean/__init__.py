"""Stage 3: clean extracted text and mark structural boundaries (statute sections, FAQ items).

Input : data/pages.jsonl, data/text/legal/*.md (+ data/legal_core.csv, data/legal_text.csv)
Output: data/clean/documents.jsonl, data/clean/units.jsonl     Run: uv run python -m crawler.clean.build
"""
