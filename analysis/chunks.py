"""Provisional chunk table for corpus exploration (topic modeling). NOT the final chunker.

Existing structural units (FAQ items, statute sections) are used as they are. Documents without units are cut
into paragraph windows of at most WINDOW_CHARS characters, only so that every part of the corpus has pieces of a
comparable size. Documents and units with include=false (hub pages, hand-recorded duplicate drops) are left out.
Remaining near-duplicates are flagged in `dup_of` and left in the table; consumers decide whether to drop.

Input : crawler/data/clean/{documents,units}.jsonl
Output: analysis/out/chunks.jsonl
Run   : uv run python analysis/chunks.py
"""

import json
from pathlib import Path

CLEAN = Path("crawler/data/clean")
OUT = Path("analysis/out")
WINDOW_CHARS = 1200
TOKENIZER = "BAAI/bge-m3"  # tokens are counted with the tokenizer of the embedding model used for exploration
DUP_JACCARD = 0.8


def read(name: str) -> list[dict]:
    return [json.loads(line) for line in (CLEAN / name).open(encoding="utf-8")]


def windows(text: str, limit: int = WINDOW_CHARS) -> list[str]:
    """Greedy paragraph packing. A paragraph longer than `limit` (flat HTML has whole documents on one line)
    is cut at spaces, which in Thai separate clauses."""
    pieces: list[str] = []
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) <= limit:
            pieces.append(para)
            continue
        cur = ""
        for part in para.split(" "):
            if cur and len(cur) + len(part) + 1 > limit:
                pieces.append(cur)
                cur = part
            else:
                cur = f"{cur} {part}".strip()
        pieces.append(cur)
    out: list[str] = []
    cur = ""
    for p in pieces:
        if cur and len(cur) + len(p) + 1 > limit:
            out.append(cur)
            cur = p
        else:
            cur = f"{cur}\n{p}" if cur else p
    if cur:
        out.append(cur)
    return out


def shingles(text: str, n: int = 8) -> set[str]:
    t = "".join(text.split())
    return {t[i : i + n] for i in range(max(len(t) - n + 1, 1))}


def build() -> list[dict]:
    docs = [d for d in read("documents.jsonl") if d["include"]]
    units_of: dict[str, list[dict]] = {}
    for u in read("units.jsonl"):
        units_of.setdefault(u["doc_id"], []).append(u)

    rows: list[dict] = []
    for d in docs:
        base = dict(doc_id=d["doc_id"], source=d["source"], kind=d["kind"], title=d["title"], tax_year=d["tax_year"] or d.get("year"))
        if d["doc_id"] in units_of:
            for u in units_of[d["doc_id"]]:
                if not u["include"]:
                    continue
                rows.append(base | dict(chunk_id=u["unit_id"], origin=u["type"], section=u["section"], text=u["text"]))
        else:
            for i, w in enumerate(windows(d["text"]), 1):
                rows.append(base | dict(chunk_id=f"{d['doc_id']}~{i:03d}", origin="window", section=None, text=w))

    sh = [shingles(r["text"]) for r in rows]
    for i, r in enumerate(rows):
        r["dup_of"] = None
        if len(sh[i]) < 40:
            continue
        for j in range(i):
            if rows[j]["doc_id"] != r["doc_id"] and rows[j]["dup_of"] is None and len(sh[j] & sh[i]) / len(sh[j] | sh[i]) >= DUP_JACCARD:
                r["dup_of"] = rows[j]["chunk_id"]
                break
    return rows


def add_tokens(rows: list[dict]) -> None:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(TOKENIZER)
    for r, ids in zip(rows, tok([r["text"] for r in rows], add_special_tokens=False)["input_ids"]):
        r["n_tokens"] = len(ids)


if __name__ == "__main__":
    rows = build()
    add_tokens(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "chunks.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} chunks, {sum(r['dup_of'] is not None for r in rows)} flagged duplicate")
