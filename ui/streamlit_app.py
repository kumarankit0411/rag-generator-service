import requests
import streamlit as st

st.set_page_config(page_title="RAG Generator", page_icon="📄", layout="centered")

UPLOAD_TYPES = ["pdf", "txt", "md"]
NEW_DOCSET = "＋ new docset…"


@st.cache_data(ttl=10, show_spinner=False)
def check_health(base_url: str) -> bool:
    try:
        return requests.get(f"{base_url}/health", timeout=5).status_code == 200
    except requests.RequestException:
        return False


@st.cache_data(ttl=10, show_spinner=False)
def list_docsets(base_url: str) -> list[str]:
    resp = requests.get(f"{base_url}/docsets", timeout=10)
    resp.raise_for_status()
    return resp.json()["docsets"]


def get_threshold(base_url: str, docset_id: str) -> dict:
    resp = requests.get(f"{base_url}/docsets/{docset_id}/threshold", timeout=30)
    resp.raise_for_status()
    return resp.json()


def post_ingest(base_url: str, files: list, docset_id: str) -> dict:
    data = {"docset_id": docset_id} if docset_id else {}
    resp = requests.post(f"{base_url}/ingest", files=files, data=data, timeout=300)
    resp.raise_for_status()
    return resp.json()


def post_ask(base_url: str, question: str, docset_id: str) -> dict:
    resp = requests.post(
        f"{base_url}/ask", json={"question": question, "docset_id": docset_id}, timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def show_threshold(base_url: str, docset_id: str) -> None:
    try:
        t = get_threshold(base_url, docset_id)
    except requests.RequestException:
        return
    label = "calibrated for this docset" if t["source"] == "docset" else "global fallback"
    st.caption(f"threshold {t['threshold']} · {label}")


def citation_caption(c: dict) -> str:
    """Chat-facing citation. chunk_index stays in the API response, not shown here."""
    loc = f"p{c['page']}" if c.get("page") else "—"
    return f"[{c['id']}] {c['source']} · {loc}"


st.title("RAG Generator")
st.caption("Pick a docset, upload documents into it, then chat with grounded answers and citations.")

# Keep the question box anchored where it is declared instead of being docked to the
# viewport, which otherwise floats it over the conversation as history grows.
st.markdown(
    "<style>[data-testid='stChatInput'] { position: static !important; bottom: auto !important; }</style>",
    unsafe_allow_html=True,
)

with st.sidebar:
    # Defaults to the Docker service name so API + UI containers work with no edits.
    # Running the UI on the host instead? Point this at http://localhost:8000.
    base_url = st.text_input("API base URL", value="http://rag-test:8000").rstrip("/")
    healthy = check_health(base_url)
    if healthy:
        st.success("API healthy")
    else:
        st.error(
            f"No API at {base_url}."
            " In Docker the API container must be named `rag-test` on the same network;"
            " running the UI on the host, use http://localhost:8000."
        )

docsets: list[str] = []
if healthy:
    try:
        docsets = list_docsets(base_url)
    except requests.RequestException:
        docsets = []

st.session_state.setdefault("docset_id", "")
if not st.session_state["docset_id"] and docsets:
    st.session_state["docset_id"] = docsets[0]
docset_id = st.session_state["docset_id"]

upload_tab, chat_tab = st.tabs(["Upload", "Chat"])

with upload_tab:
    if healthy:
        override = st.text_input(
            "Upload to a different docset (optional)",
            value="",
            placeholder=docset_id or "docset id",
            key="upload_override",
        ).strip()
        target = override or docset_id
        if target:
            st.caption(f"Documents will be added to **{target}**")
        else:
            st.info("Choose a docset in the Chat tab, or type one above.")

    uploaded = st.file_uploader(
        "Documents (.pdf / .txt / .md)", type=UPLOAD_TYPES, accept_multiple_files=True
    )
    if st.button("Ingest", disabled=not uploaded):
        if not target:
            st.warning("Enter a docset ID first.")
        else:
            files = [("files", (f.name, f.getvalue(), f.type or "application/octet-stream")) for f in uploaded]
            try:
                with st.spinner("Ingesting..."):
                    result = post_ingest(base_url, files, target)
                # survive the rerun below, which would otherwise drop the message
                if result["count"]:
                    st.session_state["flash"] = (
                        f"Ingested {result['count']} chunks into docset `{result['docset_id']}`"
                    )
                else:
                    st.session_state["flash"] = (
                        f"Nothing new to add — docset `{result['docset_id']}` already had all of it"
                    )
                # follow the docset that was just written to, so Chat asks the right one
                st.session_state["docset_id"] = result["docset_id"]
                list_docsets.clear()
                st.rerun()
            except requests.RequestException as e:
                st.error(f"Ingest failed: {e}")

    if flash := st.session_state.pop("flash", None):
        st.success(flash)

with chat_tab:
    if healthy:
        options = sorted(set(docsets) | ({docset_id} if docset_id else set()))
        if not options:
            st.info("No docsets yet — upload something on the Upload tab.")
        # existing docsets first so the default selection is a real one
        picker_options = [*options, NEW_DOCSET]
        choice = st.selectbox(
            "Docset",
            picker_options,
            index=options.index(docset_id) if docset_id in options else 0,
        )
        if choice == NEW_DOCSET:
            docset_id = st.text_input("New docset id", value="", key="new_docset_id").strip()
        else:
            docset_id = choice
        st.session_state["docset_id"] = docset_id
        if docset_id:
            show_threshold(base_url, docset_id)
            if docset_id not in docsets:
                st.warning(f"`{docset_id}` has no documents yet — upload some first.")

    # Question box sits above the conversation, so it stays put as history grows
    # instead of drifting down past the last exchange.
    question = st.chat_input(f"Ask about {docset_id}" if docset_id else "Ask a question")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if st.button("Clear chat"):
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            for c in msg.get("citations", []):
                st.caption(citation_caption(c))

    if question:
        if not docset_id:
            st.warning("Pick or create a docset first.")
        else:
            st.session_state.messages.append({"role": "user", "content": question})
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                try:
                    with st.spinner("Thinking..."):
                        data = post_ask(base_url, question, docset_id)
                    st.markdown(data["answer"])
                    if data["citations"]:
                        st.divider()
                        for c in data["citations"]:
                            st.caption(citation_caption(c))
                    st.session_state.messages.append(
                        {"role": "assistant", "content": data["answer"], "citations": data["citations"]}
                    )
                except requests.RequestException as e:
                    st.error(f"Ask failed: {e}")