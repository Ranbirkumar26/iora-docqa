"""Streamlit UI: login, upload, ask, summarize. Talks to the FastAPI backend."""
import os

import requests
import streamlit as st

API = os.getenv("DOCQA_API", "http://localhost:8000")

st.set_page_config(page_title="DocQA", page_icon="📄")


def auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


# ---------- login / signup ----------
def login_view():
    st.title("📄 DocQA — Login")
    tab_login, tab_signup = st.tabs(["Log in", "Sign up"])

    with tab_login:
        email = st.text_input("Email", key="li_email")
        pw = st.text_input("Password", type="password", key="li_pw")
        if st.button("Log in"):
            r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw})
            if r.ok:
                st.session_state.token = r.json()["access_token"]
                st.rerun()
            else:
                st.error(r.json().get("detail", "Login failed"))

    with tab_signup:
        email = st.text_input("Email", key="su_email")
        pw = st.text_input("Password", type="password", key="su_pw")
        if st.button("Create account"):
            r = requests.post(f"{API}/auth/signup", json={"email": email, "password": pw})
            if r.ok:
                st.success("Account created. Switch to Log in.")
            else:
                st.error(r.json().get("detail", "Signup failed"))


# ---------- main app ----------
def main_view():
    st.sidebar.title("📄 DocQA")

    status = requests.get(f"{API}/status", headers=auth_headers())
    if status.status_code == 401:
        st.session_state.token = None
        st.rerun()
    s = status.json()
    st.sidebar.metric("Files", s["total_files"])
    st.sidebar.metric("Tokens (est.)", f"{s['total_tokens']:,}")
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
            r = requests.post(f"{API}/upload", files=files, headers=auth_headers())
        if r.ok:
            d = r.json()
            st.sidebar.success(f"Added {len(d['uploaded'])} file(s)")
            if d["skipped"]:
                st.sidebar.warning(f"Skipped: {d['skipped']}")
            st.rerun()
        else:
            st.sidebar.error(r.text)

    # file list
    st.sidebar.divider()
    flist = requests.get(f"{API}/files", headers=auth_headers()).json()["files"]
    st.sidebar.subheader(f"Your files ({len(flist)})")
    for f in flist:
        c1, c2 = st.sidebar.columns([4, 1])
        c1.caption(f"{f['filename']} ({f['char_count']} chars)")
        if c2.button("🗑", key=f"del_{f['id']}"):
            requests.delete(f"{API}/files/{f['id']}", headers=auth_headers())
            st.rerun()

    # main tabs
    tab_ask, tab_sum = st.tabs(["Ask a question", "Summarize"])

    with tab_ask:
        q = st.text_input("Your question")
        if st.button("Ask") and q:
            with st.spinner("Thinking..."):
                r = requests.post(f"{API}/ask", json={"question": q}, headers=auth_headers())
            d = r.json()
            st.markdown(d["answer"])
            st.caption(f"Mode: {d.get('mode')}  |  Sources: {d.get('sources') or '—'}")

    with tab_sum:
        if st.button("Generate summary"):
            with st.spinner("Summarizing..."):
                r = requests.post(f"{API}/summarize", headers=auth_headers())
            d = r.json()
            st.caption(f"Mode: {d.get('mode')}")
            st.markdown(d["summary"])


if "token" not in st.session_state:
    st.session_state.token = None

if st.session_state.token:
    main_view()
else:
    login_view()
