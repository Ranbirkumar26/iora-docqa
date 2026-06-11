"""Streamlit UI: login, upload, ask, summarize. Talks to the FastAPI backend."""
import os

import requests
import streamlit as st

API = os.getenv("DOCQA_API", "http://localhost:8000")

st.set_page_config(page_title="DocQA", page_icon="📄")


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def call(method, path, *, auth=True, **kw):
    """Safe API call. Returns (data, error_message). Never raises on bad responses."""
    headers = kw.pop("headers", {})
    if auth:
        headers.update(auth_headers())
    try:
        r = requests.request(method, f"{API}{path}", headers=headers, timeout=180, **kw)
    except requests.RequestException as e:
        return None, f"Cannot reach the API server: {e}"

    if auth and r.status_code == 401:
        st.session_state.token = None
        st.warning("Session expired — please log in again.")
        st.stop()

    if not r.ok:
        try:
            return None, r.json().get("detail", r.text)
        except ValueError:
            return None, r.text or f"Server error (HTTP {r.status_code})"

    try:
        return r.json(), None
    except ValueError:
        return None, f"Unexpected non-JSON response (HTTP {r.status_code})"


# ---------- login / signup ----------
def login_view():
    st.title("📄 DocQA — Login")
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        email = st.text_input("Email", key="li_email")
        pw = st.text_input("Password", type="password", key="li_pw")
        if st.button("Log in"):
            data, err = call("POST", "/auth/login", auth=False,
                             json={"email": email, "password": pw})
            if err:
                st.error(err)
            else:
                st.session_state.token = data["access_token"]
                st.rerun()

    with tab_signup:
        email = st.text_input("Email", key="su_email")
        pw = st.text_input("Password", type="password", key="su_pw")
        if st.button("Create account"):
            data, err = call("POST", "/auth/signup", auth=False,
                             json={"email": email, "password": pw})
            if err:
                st.error(err)
            else:
                st.success("Account created. Switch to the Log in tab.")


# ---------- main app ----------
def main_view():
    st.sidebar.title("📄 DocQA")

    s, err = call("GET", "/status")
    if err:
        st.sidebar.error(f"Status unavailable: {err}")
        if st.sidebar.button("Retry"):
            st.rerun()
        s = {"total_files": "—", "total_tokens": 0, "mode": "—"}

    st.sidebar.metric("Files", s["total_files"])
    tok = s["total_tokens"]
    st.sidebar.metric("Tokens (est.)", f"{tok:,}" if isinstance(tok, int) else tok)
    st.sidebar.caption(f"Mode: **{s['mode']}**  (direct = full context, rag = retrieval)")
    if st.sidebar.button("Log out"):
        st.session_state.token = None
        st.rerun()

    # upload
    st.sidebar.divider()
    st.sidebar.subheader("Upload")
    ups = st.sidebar.file_uploader(
        "txt / csv / xlsx", type=["txt", "csv", "xlsx"], accept_multiple_files=True
    )
    if st.sidebar.button("Upload") and ups:
        files = [("files", (f.name, f.getvalue())) for f in ups]
        with st.spinner("Uploading + indexing..."):
            data, err = call("POST", "/upload", files=files)
        if err:
            st.sidebar.error(err)
        else:
            st.sidebar.success(f"Added {len(data['uploaded'])} file(s)")
            if data["skipped"]:
                st.sidebar.warning(f"Skipped: {data['skipped']}")
            st.rerun()

    # file list
    st.sidebar.divider()
    flist, err = call("GET", "/files")
    files_rows = flist["files"] if not err else []
    st.sidebar.subheader(f"Your files ({len(files_rows)})")
    for f in files_rows:
        c1, c2 = st.sidebar.columns([4, 1])
        c1.caption(f"{f['filename']} ({f['char_count']} chars)")
        if c2.button("🗑", key=f"del_{f['id']}"):
            call("DELETE", f"/files/{f['id']}")
            st.rerun()

    # main tabs
    tab_ask, tab_sum = st.tabs(["Ask a question", "Summarize"])

    with tab_ask:
        q = st.text_input("Your question")
        if st.button("Ask") and q:
            with st.spinner("Thinking..."):
                data, err = call("POST", "/ask", json={"question": q})
            if err:
                st.error(err)
            else:
                st.markdown(data["answer"])
                st.caption(f"Mode: {data.get('mode')}  |  Sources: {data.get('sources') or '—'}")

    with tab_sum:
        if st.button("Generate summary"):
            with st.spinner("Summarizing..."):
                data, err = call("POST", "/summarize")
            if err:
                st.error(err)
            else:
                st.caption(f"Mode: {data.get('mode')}")
                st.markdown(data["summary"])


if "token" not in st.session_state:
    st.session_state.token = None

if st.session_state.token:
    main_view()
else:
    login_view()
