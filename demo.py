"""Demo: a chat app for Thai personal income tax questions, with the sources under each answer.

Run:  uv run --group rag streamlit run demo.py
Follow-up questions keep the earlier turns; "New conversation" in the sidebar starts over.
Generator, retrieval mode and k are set in the sidebar (generators are the profiles in rag/models.toml).
"""

import streamlit as st

from rag import llm
from rag.answer import answer, citations, year_label
from rag.retrieve import MODES, Retriever

st.set_page_config(page_title="ภาษีเงินได้บุคคลธรรมดา", page_icon="🧾")


@st.cache_resource(show_spinner="loading retriever…")
def load_retriever() -> Retriever:
    return Retriever()


@st.cache_resource
def load_profile(name: str) -> llm.Profile:
    return llm.profile(name)


def show_sources(hits: list[dict], text: str, show_context: bool) -> None:
    cited, bad = citations(text, hits)
    with st.expander(f"แหล่งอ้างอิง ({len(cited)} cited of {len(hits)})"):
        for n, h in enumerate(hits, 1):
            mark = "✅" if h["chunk_id"] in cited else "▫️"
            st.markdown(f"{mark} **[{n}]** [{h['header'][:90]}]({h['url']}) ({year_label(h)})")
            if show_context:
                st.caption(h["text"][:400])
        if bad:
            st.warning(f"Cited numbers with no source: {bad}")


with st.sidebar:
    st.header("Settings")
    gen_name = st.selectbox("Generator", list(llm.read_config().get("models", {})), index=None, placeholder="gpt-mini")
    gen_name = gen_name or "gpt-mini"
    mode = st.selectbox("Retrieval mode", MODES, index=MODES.index("hybrid"))
    k = st.slider("Sources (k)", 1, 20, 5)
    cap = st.number_input("Max hits per document (0 = no cap)", 0, 20, 0)
    retries = st.number_input("Script retries (ask again if the answer has Chinese/Japanese/Korean)", 0, 5, 0)
    show_context = st.toggle("Show retrieved text", value=False)
    if st.button("New conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

st.title("🧾 ถามเรื่องภาษีเงินได้บุคคลธรรมดา")
st.caption(f"{gen_name} · {mode} · k={k}" + (f" · cap {cap}" if cap else ""))

try:
    gen, retriever = load_profile(gen_name), load_retriever()
except SystemExit as e:  # llm.profile reports a missing key or model id this way
    st.error(str(e))
    st.stop()

# each message: {"role", "content"} plus "hits" on assistant messages
messages: list[dict] = st.session_state.setdefault("messages", [])

for m in messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("hits"):
            show_sources(m["hits"], m["content"], show_context)

if question := st.chat_input("พิมพ์คำถาม เช่น ลดหย่อนบิดามารดาได้เท่าไร"):
    with st.chat_message("user"):
        st.markdown(question)
    turns = [(u["content"], a["content"]) for u, a in zip(messages[::2], messages[1::2])]
    with st.chat_message("assistant"):
        with st.spinner("searching and answering…"):
            query = "\n".join([q for q, _ in turns] + [question])  # same multi-turn rule as rag.answer
            hits = retriever.search(query, mode, k, cap or None)
            text = answer(gen, question, hits, turns, retries)[0]
        st.markdown(text)
        show_sources(hits, text, show_context)
    messages += [{"role": "user", "content": question}, {"role": "assistant", "content": text, "hits": hits}]
