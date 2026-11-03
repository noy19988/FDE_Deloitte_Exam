"""
The chat UI (Streamlit), laid out like ChatGPT / Gemini:
- left sidebar: "New chat" button + the list of past chats
- main area: the conversation, and one chat box at the bottom
  (type a question, or press the microphone in the same box to speak -
  the recording becomes text in the box, and the user sends it)

The UI has no logic of its own - it only talks to the backend API.
Streamlit re-runs this whole file from top to bottom on every click,
so anything we need to remember between runs goes into st.session_state.

Run from the project root:
    streamlit run frontend/app.py
"""

import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

# How the backend's automatic number check starts its warning (always English).
WARNING_START = "⚠️ **Automatic check:**"

# Shown in an empty chat: what this agent is for (no ready-made questions).
WELCOME = """
I help investment analysts find **US airports where expansion would be most profitable**.

I can rank and compare airports by capacity pressure, demand growth, congestion,
market size and pricing power - and explain every score with real public data
from the US Department of Transportation and the FAA.
"""


# --- Talking to the backend ---

def api(method, path, **kwargs):
    """Call the backend. Shows an error in the UI and stops if it fails."""
    try:
        response = requests.request(method, f"{BACKEND_URL}{path}", timeout=180, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.HTTPError as error:
        if error.response.status_code == 503:  # the AI model (Gemini) is busy or unreachable
            st.error("The AI model is busy right now. Please try again in a minute.", icon="⏳")
        else:
            st.error(f"Backend error: {error.response.text}")
        st.stop()
    except requests.RequestException as error:  # backend is down, or took too long
        st.error(f"Cannot reach the backend: {error}")
        st.stop()


def ask(question):
    """Send a question to the agent and remember which tools it used."""
    result = api("POST", "/chat", json={"session_id": st.session_state.session_id, "message": question})
    st.session_state.last_tools = result["tools_used"]


def to_text(audio_bytes):
    """Voice recording -> text (the backend asks Gemini to transcribe it)."""
    files = {"audio": ("question.wav", audio_bytes, "audio/wav")}
    return api("POST", "/transcribe", files=files)["text"]


def start_new_chat():
    st.session_state.session_id = api("POST", "/sessions")["session_id"]
    st.session_state.last_tools = []


@st.dialog("Delete chat?")
def confirm_delete(chat):
    """A small window that asks before deleting - deleting cannot be undone."""
    with text_box(chat["title"], key="delete_title"):
        st.markdown(f"**{chat['title']}**")
    st.caption("This chat and all its messages will be deleted. This cannot be undone.")
    if st.button("Delete", type="primary"):
        api("DELETE", f"/sessions/{chat['session_id']}")
        if chat["session_id"] == st.session_state.session_id:
            start_new_chat()  # we deleted the open chat, so open an empty one
        st.rerun()


def short(title, length=32):
    """Cut long chat titles so each one fits on one line in the sidebar."""
    return title if len(title) <= length else title[:length].rstrip() + "…"


def is_rtl(text):
    """True if the text is mostly Hebrew (or Arabic), so it should read right-to-left."""
    rtl_letters = sum("֐" <= ch <= "ۿ" for ch in text)  # Hebrew + Arabic letters
    ltr_letters = sum(ch.isascii() and ch.isalpha() for ch in text)  # English letters
    return rtl_letters > ltr_letters


def text_box(text, key):
    """
    A box to show text in. Hebrew text gets a box named "rtl_...",
    and the style at the top of the page makes those boxes right-to-left.
    """
    return st.container(key=f"rtl_{key}" if is_rtl(text) else None)


def show_message(text, key):
    """
    Show one chat message in its language's direction.
    The automatic number check (backend/agent/verification.py) adds an English
    warning at the end - it gets its own box, so it stays left-to-right
    even under a Hebrew answer.
    """
    answer, found, warning = text.partition(WARNING_START)
    with text_box(answer, key):
        st.markdown(answer)
    if found:
        st.markdown(WARNING_START + warning)


# --- Page setup ---

st.set_page_config(page_title="Airport Investment Agent", page_icon="✈️")

# Small style fixes:
# 1. Sidebar rows ("New chat" and the chats) are flat, like in ChatGPT / Gemini:
#    text starts at the edge, grey on hover, the open chat has a grey background,
#    and each chat shows a delete icon on hover.
# 2. Boxes named "rtl_..." (Hebrew text, see text_box) read right-to-left,
#    fill the whole row (so short messages sit at the right edge), and flip the avatar to the right.
# 3. In the chat box, each line follows its own language (Hebrew -> right, English -> left).
# 4. The app name sits at the very top of the sidebar, in one row with the « button.
st.markdown("""
<style>
/* One grid for the sidebar: all text and icons start (or end) 0.6rem inside the
   rows' edges - the same inset as the buttons' own padding - and the app name
   is centered on the same line as the « button. */
[data-testid="stSidebarUserContent"] { margin-top: -3.875rem; }
[data-testid="stSidebarHeader"] { position: relative; z-index: 1; }  /* keep « clickable */
[data-testid="stSidebarCollapseButton"] { margin-right: 0.6rem; }
[data-testid="stSidebarUserContent"] [data-testid="stElementContainer"]:has(h3) {  /* app name row */
    height: 2rem; display: flex; align-items: center;
}
[data-testid="stSidebarUserContent"] [data-testid="stElementContainer"]:has(h3) [data-testid="stMarkdownContainer"] {
    margin: 0;  /* Streamlit gives headings a negative bottom margin, which breaks the centering */
}
[data-testid="stSidebarUserContent"] h3 { padding: 0 0 0 0.6rem; font-size: 1.05rem; }
[data-testid="stSidebarUserContent"] [data-testid="stCaptionContainer"] { padding-left: 0.6rem; }  /* "Recent" */
[data-testid="stSidebarUserContent"] [data-testid="stVerticalBlock"] { gap: 0.1rem; }
[data-testid="stSidebarUserContent"] button {
    border: none; border-radius: 0.5rem; padding: 0.4rem 0.6rem; color: inherit;
}
[data-testid="stSidebarUserContent"] button > div { justify-content: flex-start; text-align: start; }
[data-testid="stSidebarUserContent"] button:hover { background: rgba(49, 51, 63, 0.08); color: inherit; }
/* Chat rows (title + delete icon): the whole row is grey on hover and when it is the open chat;
   the delete icon only appears on hover. */
[class*="st-key-chat_"] { border-radius: 0.5rem; }
[class*="st-key-chat_"]:hover, [class*="st-key-chat_open_"] { background: rgba(49, 51, 63, 0.08); }
[class*="st-key-chat_"] button:hover { background: transparent; }
[class*="st-key-chat_"] > :first-child { flex: 1; min-width: 0; }  /* the title takes the free space */
[class*="st-key-chat_"] button, [class*="st-key-chat_"] button > div { min-width: 0; overflow: hidden; }
[class*="st-key-chat_"] button p { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }  /* one line, cut with … */
[class*="st-key-delete_"] { visibility: hidden; }
[class*="st-key-chat_"]:hover [class*="st-key-delete_"] { visibility: visible; }
[class*="st-key-rtl_"] { direction: rtl; width: 100%; }
[class*="st-key-rtl_"], [class*="st-key-rtl_"] * { text-align: start; }  /* "start" = right in a right-to-left box */
/* A Hebrew message also puts its avatar on the right, like the text */
[data-testid="stChatMessage"]:has([class*="st-key-rtl_"]) { flex-direction: row-reverse; }
[data-testid="stChatInputTextArea"] { unicode-bidi: plaintext; text-align: start; }
/* While a recording becomes text, the chat box is disabled and shows a small spinner at its start */
[data-testid="stChatInput"]:has(textarea:disabled) { position: relative; }
[data-testid="stChatInput"]:has(textarea:disabled)::before {
    content: ""; position: absolute; left: 1rem; top: 50%; z-index: 1;
    width: 1rem; height: 1rem; margin-top: -0.5rem; border-radius: 50%;
    border: 2px solid rgba(49, 51, 63, 0.2); border-top-color: rgba(49, 51, 63, 0.7);
    animation: chat-box-spin 0.8s linear infinite;
}
[data-testid="stChatInput"] textarea:disabled { padding-left: 2.25rem; }  /* room for the spinner */
@keyframes chat-box-spin { to { transform: rotate(360deg); } }
</style>
""", unsafe_allow_html=True)

if "session_id" not in st.session_state:
    start_new_chat()


# --- Sidebar: new chat + past chats ---

with st.sidebar:
    st.markdown("### ✈️ Airport Investment Agent")
    chats = api("GET", "/sessions")

    # Its own row at the top: icon + "New chat". Below it: "Recent" and the chats.
    if st.button("New chat", icon=":material/edit_square:", type="tertiary", width="stretch"):
        start_new_chat()
        st.rerun()

    if chats:
        st.space("small")
        st.caption("Recent")

    for chat in chats:
        is_current = chat["session_id"] == st.session_state.session_id
        # One row per chat: the title (opens it) and a delete icon (shown on hover).
        # The row's name says if it is the open chat - the style above makes that row grey.
        row_name = f"chat_open_{chat['session_id']}" if is_current else f"chat_{chat['session_id']}"
        with st.container(key=row_name, horizontal=True, vertical_alignment="center", gap=None):
            with text_box(chat["title"], key=chat["session_id"]):
                if st.button(short(chat["title"]), key=chat["session_id"], type="tertiary", width="stretch"):
                    st.session_state.session_id = chat["session_id"]
                    st.session_state.last_tools = []
                    st.rerun()
            if st.button("", icon=":material/delete:", key=f"delete_{chat['session_id']}",
                         type="tertiary", help="Delete chat"):
                confirm_delete(chat)


# --- The conversation ---

messages = api("GET", f"/sessions/{st.session_state.session_id}")["messages"]

# A recording was turned into text on the last run: put the text in the chat box
# (not sent), so the user can read it, fix it and press send - like in ChatGPT.
if "draft" in st.session_state:
    st.session_state.chat_box = st.session_state.pop("draft")

# While a recording is being turned into text, the chat box itself shows it:
# it is disabled, says so in its placeholder, and shows a small spinner (see the style above).
transcribing = "recording" in st.session_state

# The chat box is always drawn at the bottom of the page, but we read it first,
# so the welcome text disappears as soon as the first question is sent.
sent = st.chat_input(
    "Turning your recording into text..." if transcribing else "Ask about US airports...",
    accept_audio=True, key="chat_box", disabled=transcribing,
)

# A recording (the microphone inside the chat box): keep it and re-run at once,
# so the chat box can show the waiting state while we transcribe (end of the page).
if sent and sent.audio:
    st.session_state.recording = (sent.text, sent.audio.getvalue())
    st.rerun()

if not messages and not sent:
    # One container, so the first question replaces the whole welcome at once.
    with st.container():
        st.space("large")  # some space above, like other AI chats
        st.header("What would you like to know?", text_alignment="center", anchor=False)
        st.markdown(WELCOME, text_alignment="center")

for number, message in enumerate(messages):
    with st.chat_message(message["role"]):
        show_message(message["text"], key=f"message_{number}")

# Under the latest answer: which tools the agent used (transparency).
if st.session_state.get("last_tools"):
    names = ", ".join(tool["tool"] for tool in st.session_state.last_tools)
    st.caption(f"🔧 Tools used: {names}")


# --- A new question (typed, or a recording the user checked and sent) ---

if sent:
    question = sent.text
    with st.chat_message("user"):
        show_message(question, key="new_question")

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            ask(question)
    st.rerun()  # reload the chat from the backend, now with the new answer


# --- A recording waiting to become text (the page above is already drawn) ---

if transcribing:
    typed, audio = st.session_state.pop("recording")
    spoken = to_text(audio)
    # Next run: the text goes into the chat box (top of this section). Nothing is sent yet.
    st.session_state.draft = f"{typed} {spoken}".strip()  # keep anything already typed
    st.rerun()
