"""Persistent offline-proof badge, rendered above the page on every screen. Refreshes every 30 s without blocking the UI:
the public-host probe runs in a background thread (intake.offline) and the badge only reads its cached result."""
import streamlit as st

from intake import offline

COLORS = {"ok": ("#e8f5e9", "#1b5e20"), "warn": ("#fff3e0", "#e65100"), "pending": ("#eceff1", "#37474f")}


def _body() -> None:
    st_ = offline.status()
    level, text = offline.headline(st_)
    bg, fg = COLORS[level]
    st.markdown(f"<div style='background:{bg};color:{fg};padding:4px 10px;border-radius:6px;font-size:0.85rem;display:inline-block'>"
                f"{'🔒' if level == 'ok' else '⚠️' if level == 'warn' else '…'} {text}</div>", unsafe_allow_html=True)
    with st.expander("Network details", expanded=False):
        m = st_["local_model"]
        st.write(f"Allowed outbound target: **{m['host']}:{m['port']}** (local model server) · "
                 + ("reachable" if m["reachable"] else f"not reachable ({m['error']})"))
        for s in st_["services"]:
            st.caption(f"• {s['name']}: {s['target']}")
        p = offline.probe_config()
        if st_["strict"]:
            st.caption("OFFLINE_STRICT is on: any non-localhost connection raises an error and is logged. The public probe is not run.")
        else:
            n = st_["internet"]
            st.caption(f"Public probe: {p.host}:{p.port}, timeout {p.timeout_s:g} s, every {p.interval_s} s · "
                       + ("not finished yet" if n is None else f"{'reachable' if n['reachable'] else 'unreachable'} ({n['took_s']} s)")
                       + ". This is only a check; the app does not use the internet.")


@st.fragment(run_every=offline.probe_config().interval_s)
def _fragment() -> None:
    _body()


def render() -> None:
    offline.install_if_strict()
    _fragment()
