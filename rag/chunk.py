"""Token-aware chunker: the clean corpus -> retrieval chunks.

Structural units (FAQ items, statute sections) stay whole when they fit, so a question stays with its answer and a
section with its clauses. Units that do not fit, and documents without units, are packed paragraph by paragraph up
to the token limit. Every chunk carries a header (document title, section, unit label) that is embedded and indexed
with it, so a piece cut from the middle of a document still says what it belongs to.

Sizes are counted with the embedding model's tokenizer (bge-m3), header included:
- MAX_TOKENS 512: hard cap. Keeps 597 of 605 FAQ units (median 98 tokens, p90 239) and 36 of 43 statute sections
  whole; bge-m3 accepts 8,192, so the cap is about retrieval granularity, not the model.
- WINDOW_TOKENS 384: target for unstructured text (articles, rulings, legal instruments without a splitter yet).
  Smaller than the cap so a window holds one or two clauses rather than a whole instrument. Provisional; an
  ablation candidate.
No overlap between windows in this baseline.

Input : crawler/data/clean/{documents,units}.jsonl (include=false documents and units are skipped)
Output: rag/out/chunks.jsonl
Run   : uv run python -m rag.chunk
"""

import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path

CLEAN = Path("crawler/data/clean")
OUT = Path("rag/out")
TOKENIZER = "BAAI/bge-m3"
MAX_TOKENS = 512
WINDOW_TOKENS = 384
QUESTION_CHARS = 200  # the question repeated in the header of a split FAQ item's later parts
QUESTION = re.compile(r"^\s*(?:Q\s*\d+|คำถาม)\s*:")  # Clear Cut "Q1 :", ร้อยเรื่องลดหย่อน "คำถาม :"

Count = Callable[[str], int]


def token_counter(name: str = TOKENIZER) -> Count:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(name)
    tok.model_max_length = 10**9  # only counting: silence the warning for texts longer than the model's context
    return lambda text: len(tok(text, add_special_tokens=False)["input_ids"])


def hard_cut(text: str, limit: int, count: Count) -> list[str]:
    """Cut text with no usable break into the longest prefixes that fit (binary search on characters)."""
    out = []
    while count(text) > limit:
        lo, hi = 1, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            lo, hi = (mid, hi) if count(text[:mid]) <= limit else (lo, mid - 1)
        out.append(text[:lo])
        text = text[lo:]
    return out + [text] if text else out


def pack(parts: list[str], limit: int, count: Count, sep: str, heads: list[str] | None = None) -> list[str]:
    """Greedy packing: join consecutive parts with `sep` while the joined text fits. Parts must each fit.

    `heads` (parallel to parts, "" for none) is the header of the markdown table a part is a row of: a part that opens
    a new chunk gets it in front, so a table cut between rows keeps its column names in every piece."""
    out, cur = [], ""
    for i, p in enumerate(parts):
        if cur and count(cur + sep + p) <= limit:
            cur = cur + sep + p
        else:
            if cur:
                out.append(cur)
            head = heads[i] if heads else ""
            cur = head + sep + p if head and count(head + sep + p) <= limit else p
    return out + [cur] if cur else out


TABLE_SEPARATOR = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+$")  # `| --- | :-: |`


def table_heads(lines: list[str]) -> tuple[list[str], list[str]]:
    """Mark the markdown tables in `lines` (one row per line): -> (lines, heads), where a table's header row and its
    separator line become one line (they must never be parted) and each later row of the table has that pair as head."""
    out, heads, head = [], [], ""
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and TABLE_SEPARATOR.match(lines[i + 1]):
            head = ln + "\n" + lines[i + 1]
            out.append(head)
            heads.append("")
            i += 2
            continue
        out.append(ln)
        heads.append(head if ln.startswith("|") else "")
        if not ln.startswith("|"):
            head = ""
        i += 1
    return out, heads


def split(text: str, limit: int, count: Count) -> list[str]:
    """Paragraphs packed up to `limit`. A paragraph that is too long is split at spaces (in Thai they separate
    clauses and phrases), and a space-free run that is still too long is cut by tokens. A markdown table is cut between
    its rows (one row per line) and each later part starts with the table's header row and separator line."""
    lines, line_heads = table_heads([p.strip() for p in text.split("\n") if p.strip()])
    paras, heads = [], []
    for para, head in zip(lines, line_heads):
        if count(para) <= limit:
            paras.append(para)
            heads.append(head)
            continue
        words = [w for p in para.split(" ") if p for w in hard_cut(p, limit, count)]
        pieces = pack(words, limit, count, " ")
        paras += pieces
        heads += [""] * len(pieces)
    return pack(paras, limit, count, "\n", heads)


def header_of(*parts: str | None) -> str:
    seen = []
    for p in parts:
        p = " ".join((p or "").split())
        if p and p not in seen:
            seen.append(p)
    return " | ".join(seen)


def make_chunks(docs: list[dict], units: list[dict], count: Count) -> Iterator[dict]:
    units_of: dict[str, list[dict]] = {}
    for u in units:
        units_of.setdefault(u["doc_id"], []).append(u)

    for d in docs:
        if not d["include"]:
            continue
        meta = dict(doc_id=d["doc_id"], source=d["source"], kind=d["kind"], title=d["title"], url=d["url"],
                    tax_year=d["tax_year"], year=d.get("year"), flags=d["flags"])
        # (id stem, unit or None, header, text, header for later parts of a split unit)
        pieces: list[tuple[str, dict | None, str, str, str]] = []
        if d["doc_id"] in units_of:
            if d["preamble"].strip():
                h = header_of(d["title"])
                pieces.append((f"{d['doc_id']}~pre", None, h, d["preamble"], h))
            for u in units_of[d["doc_id"]]:
                if not u["include"]:
                    continue
                h = header_of(d["title"], u["section"], u["title"] or u["label"])
                cont = h
                if u["type"] == "faq":
                    lines = [ln for ln in u["text"].split("\n") if ln.strip()]
                    question = next((ln for ln in lines if QUESTION.match(ln)), lines[0] if lines else "")[:QUESTION_CHARS]
                    cont = header_of(h, question)
                pieces.append((u["unit_id"], u, h, u["text"], cont))
        else:
            h = header_of(d["title"])
            pieces.append((d["doc_id"], None, h, d["text"], h))

        for stem, u, h, text, cont in pieces:
            if u is not None and count(h + "\n" + text.strip()) <= MAX_TOKENS:
                bodies = [text.strip()]
            else:  # budget for the longest header the parts can carry, plus the newline
                bodies = split(text, (MAX_TOKENS if u is not None else WINDOW_TOKENS) - count(cont) - 1, count)
            for i, body in enumerate(bodies, 1):
                header = h if i == 1 else cont
                yield meta | dict(
                    chunk_id=stem if len(bodies) == 1 and u is not None else f"{stem}~{i:03d}",
                    unit_id=u["unit_id"] if u else None, origin=u["type"] if u else "window",
                    section=u["section"] if u else None, label=u["label"] if u else None,
                    part=i, n_parts=len(bodies), header=header, text=body, n_tokens=count(header + "\n" + body),
                )


def passage(chunk: dict) -> str:
    """What gets embedded and indexed: header line + body."""
    return chunk["header"] + "\n" + chunk["text"]


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.open(encoding="utf-8")]


def main() -> None:
    docs, units = read_jsonl(CLEAN / "documents.jsonl"), read_jsonl(CLEAN / "units.jsonl")
    chunks = list(make_chunks(docs, units, token_counter()))
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "chunks.jsonl").open("w", encoding="utf-8") as f:
        f.writelines(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks)
    n = sorted(c["n_tokens"] for c in chunks)
    print(f"{len(chunks)} chunks from {len({c['doc_id'] for c in chunks})} documents -> {OUT / 'chunks.jsonl'}")
    print(f"tokens: median {n[len(n) // 2]}, p90 {n[int(len(n) * 0.9)]}, max {n[-1]}; split units: "
          f"{len({c['unit_id'] for c in chunks if c['unit_id'] and c['n_parts'] > 1})}")


if __name__ == "__main__":
    main()
