"""UKNest AI: Streamlit chat interface.

Run:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit only puts app/ on the import path; add the project root too
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from app import ui_helpers as ui  # noqa: E402

st.set_page_config(page_title="UKNest", page_icon=":material/home:", layout="centered")

st.markdown("""
<style>
  .block-container {padding-top: 2.6rem; max-width: 780px;}

  /* Header */
  .uk-hero {margin-bottom: 1.1rem;}
  .uk-hero .wordmark {font-size: 2.5rem; font-weight: 700; letter-spacing: -0.02em;
                      line-height: 1.05; color: var(--uk-ink); margin: 0;}
  .uk-hero .wordmark::after {content: ""; display: block; width: 44px; height: 4px;
                             border-radius: 2px; background: #0f766e; margin-top: 0.55rem;}
  .uk-hero .lede {font-size: 1.08rem; color: var(--uk-muted); margin: 0.75rem 0 0;
                  max-width: 66ch; line-height: 1.5;}
  .uk-note {font-size: 0.9rem; line-height: 1.45; color: var(--uk-muted);
            border-left: 3px solid #c58a1c; padding: 0.15rem 0 0.15rem 0.8rem;
            margin: 0 0 1.6rem;}
  .uk-start {font-weight: 700; margin: 0 0 0.4rem;}

  :root {--uk-ink: #17302b; --uk-muted: #52625e;}

  /* Starter topics: calm, squared buttons rather than pills */
  [data-testid="stMain"] div[data-testid="stButton"] button {
      border-radius: 10px; min-height: 3rem; justify-content: flex-start; text-align: left;}

  /* Headings inside answers stay modest */
  [data-testid="stChatMessage"] h1, [data-testid="stChatMessage"] h2,
  [data-testid="stChatMessage"] h3 {font-size: 1.05rem; margin: 0.9rem 0 0.3rem; padding: 0;}

  [data-testid="stChatMessage"] [data-testid="stHeaderActionElements"] {display: none;}

  /* Sidebar */
  section[data-testid="stSidebar"] h3 {font-size: 0.98rem; margin-bottom: 0.2rem;}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ agent
@st.cache_resource(show_spinner="Starting the assistant (first time only)...")
def get_runner():
    from app.runner import AgentRunner
    return AgentRunner()


def get_chat(runner, profile: dict):
    """One LLM conversation per browser session; restart it if the profile changes."""
    if st.session_state.get("chat_profile") != profile or "chat" not in st.session_state:
        st.session_state.chat = runner.new_chat(profile)
        st.session_state.chat_profile = profile
    return st.session_state.chat


def reset_conversation():
    for key in ("messages", "chat", "chat_profile"):
        st.session_state.pop(key, None)


st.session_state.setdefault("messages", [])
kb = ui.knowledge_base_info()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.button("New conversation", icon=":material/add_comment:", use_container_width=True,
              on_click=reset_conversation)

    st.subheader("Your details")
    visa = st.selectbox(
        "Visa or status", ui.VISA_TYPES, index=0,
        help="Optional. Used only to tailor answers. Please don't enter names or document numbers.")
    postcode = st.text_input(
        "Postcode", placeholder="e.g. IG11 7LU",
        help="Optional. Used to find your council and services near you.")
    profile = ui.build_profile(visa, postcode)

    st.subheader("Display")
    show_sources = st.toggle("Show sources", value=True)
    show_trace = st.toggle("Show steps taken", value=True)

    with st.expander("About this assistant"):
        st.markdown(
            f"Answers come from **{kb['pages']} official GOV.UK pages**, last fetched "
            f"{ui.nice_date(kb['fetched'])}. Local services come from OpenStreetMap and "
            "postcode details from postcodes.io.\n\n"
            "This is general information, not legal or immigration advice.")

# ------------------------------------------------------------------ header
st.markdown("""
<div class="uk-hero">
  <p class="wordmark">UKNest</p>
  <p class="lede">Clear answers about living in the UK, from renting and work to council tax
  and the NHS. Every answer links to the official GOV.UK page it came from.</p>
</div>
<p class="uk-note">General information, not legal or immigration advice. For your own
situation, speak to an OISC-regulated adviser or Citizens Advice.</p>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ rendering
AVATARS = {"user": ":material/person:", "assistant": ":material/home:"}

def render_assistant(msg: dict) -> None:
    st.markdown(msg["content"])
    if msg.get("error"):
        return
    if show_sources and msg.get("sources"):
        with st.expander(f"Sources ({len(msg['sources'])})", icon=":material/menu_book:"):
            for s in msg["sources"]:
                st.markdown(f"- [{s['title']} – {s['section']}]({s['url']})  \n"
                            f"  <small>Updated {ui.nice_date(s.get('last_updated'))}</small>",
                            unsafe_allow_html=True)
    if show_trace and msg.get("trace"):
        n = len(msg["trace"])
        with st.expander(f"Steps taken ({n})", icon=":material/route:"):
            for step in msg["trace"]:
                st.markdown(f"{step['step']}. {ui.describe_tool_call(step)}")
    meta = msg.get("meta", {})
    notes = [f"Answered in {meta.get('seconds', 0)} s"]
    if meta.get("referral_added") or meta.get("high_risk"):
        notes.append(":material/shield: safety check applied")
    if meta.get("unsupported_urls"):
        notes.append(":material/warning: a link could not be verified")
    st.caption(",  ".join(notes))


for msg in st.session_state.messages:
    with st.chat_message(msg["role"], avatar=AVATARS[msg["role"]]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_assistant(msg)

# ------------------------------------------------------------------ input
# Quick-start buttons use a callback, so the click is known before the page draws
# and the buttons disappear as soon as a question is asked.
pending = st.session_state.pop("pending_question", None)
if not st.session_state.messages and not pending:
    st.markdown('<p class="uk-start">Start with a common question</p>', unsafe_allow_html=True)
    cols = st.columns(3)
    for i, (label, q) in enumerate(ui.QUICK_QUESTIONS.items()):
        cols[i % 3].button(label, use_container_width=True, on_click=st.session_state.update,
                           kwargs={"pending_question": q})

typed = st.chat_input("Ask a question about living in the UK")
question = typed or pending

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar=AVATARS["user"]):
        st.markdown(question)

    with st.chat_message("assistant", avatar=AVATARS["assistant"]):
        with st.spinner("Checking official guidance"):
            try:
                runner = get_runner()
                result = runner.ask(get_chat(runner, profile), question)
                msg = {
                    "role": "assistant",
                    "content": result.answer,
                    "sources": result.sources,
                    "trace": result.trace,
                    "meta": {"seconds": result.seconds, **result.guardrails},
                }
            except Exception as exc:  # show a friendly message, keep the app alive
                msg = {"role": "assistant", "content": ui.friendly_error(exc),
                       "error": True}
                st.session_state.pop("chat", None)  # start a clean conversation next time
        render_assistant(msg)
    st.session_state.messages.append(msg)
