"""Demo: ask Thai personal income tax questions and see the answer with its sources.

One question:  uv run python demo.py "ลดหย่อนบิดามารดาได้เท่าไร"
Conversation:  uv run python demo.py            (follow-up questions keep the earlier turns; /new starts over, /quit ends)
Options:       --gen gpt-mini  --mode dense|sparse|hybrid  -k 5  --show-context
"""

import argparse

from rag import llm
from rag.answer import answer, citations, year_label
from rag.retrieve import MODES, Retriever


def show(question: str, hits: list[dict], text: str, show_context: bool) -> None:
    cited, bad = citations(text, hits)
    print(f"\n{text}\n")
    print("แหล่งอ้างอิง")
    for n, h in enumerate(hits, 1):
        mark = "*" if h["chunk_id"] in cited else " "
        print(f" {mark}[{n}] {h['header'][:90]} ({year_label(h)})\n       {h['url']}")
        if show_context:
            print("       " + h["text"][:400].replace("\n", "\n       "))
    if bad:
        print(f"  ! cited numbers with no source: {bad}")
    print("  (* = cited in the answer)\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="?")
    ap.add_argument("--gen", default="gpt-mini", help="generator profile in rag/models.toml")
    ap.add_argument("--mode", choices=MODES, default="hybrid")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--show-context", action="store_true", help="print the retrieved text under each source")
    a = ap.parse_args()

    gen = llm.profile(a.gen)
    print(f"loading retriever ({a.mode}, k={a.k}); generator {gen.model} via {gen.backend}")
    retriever = Retriever()
    turns: list[tuple[str, str]] = []

    def ask(question: str) -> None:
        query = "\n".join([q for q, _ in turns] + [question])  # same multi-turn rule as rag.answer
        hits = retriever.search(query, a.mode, a.k)
        text, _ = answer(gen, question, hits, turns)
        show(question, hits, text, a.show_context)
        turns.append((question, text))

    if a.question:
        ask(a.question)
        return
    print("พิมพ์คำถาม (/new เริ่มบทสนทนาใหม่, /quit ออก)")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q in ("/quit", "/exit"):
            break
        if q == "/new":
            turns.clear()
            print("เริ่มบทสนทนาใหม่")
        elif q:
            ask(q)


if __name__ == "__main__":
    main()
