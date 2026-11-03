"""Login gate for the Staff and Doctor pages (reuses ocr.auth). The patient kiosk never imports this.
Roles: staff can view the red-flag board; only a doctor can edit and save summaries."""
import time
from pathlib import Path

import streamlit as st

from ocr import auth
from ocr.config import load_settings

ss = st.session_state


def can_edit(role: str | None) -> bool:
    return role == "doctor"


@st.cache_resource
def _authenticator(users_file: str, max_failures: int, lockout_s: int):  # one per process: lockout survives reruns
    return auth.Authenticator(Path(users_file), max_failures, lockout_s)


def require_login(allowed: tuple[str, ...] = ("staff", "doctor")) -> dict:
    """Render the sign-in form and st.stop() unless a valid, non-idle login with an allowed role exists.
    Returns {"username", "role", "last_seen"}."""
    S = load_settings()
    cur = ss.get("auth")
    if cur and auth.idle_expired(cur["last_seen"], S.auth_idle_s):
        ss.auth, cur = None, None
        ss.login_notice = "Logged out after inactivity."
    if not cur:
        st.title("Sign in")
        if notice := ss.pop("login_notice", None):
            st.info(notice)
        if not auth.has_users(S.users_file):
            st.error("No users exist yet. Create one: `.venv/bin/python scripts/create_user.py <username> <doctor|staff>`")
            st.stop()
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary"):
                user, msg = _authenticator(str(S.users_file), S.max_login_failures, S.lockout_s).login(u, p)
                if user:
                    ss.auth = {**user, "last_seen": time.time()}
                    st.rerun()
                st.error(msg)
        st.stop()
    cur["last_seen"] = time.time()
    with st.sidebar:
        st.write(f"Signed in: **{cur['username']}** ({cur['role']})")
        if st.button("Sign out", key="signout"):
            ss.auth = None
            st.rerun()
    if cur["role"] not in allowed:
        st.error("Your role is not allowed on this page.")
        st.stop()
    return cur
