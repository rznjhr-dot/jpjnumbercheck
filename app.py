#!/usr/bin/env python3
"""
JPJ Number Checker — Web GUI (Streamlit).

Number input + Search button on the webpage.
Clicking Search spawns a browser window for login + search.
Progress shows on the webpage.
"""

import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))
from jpj_automation import check_number, PRODUCTION_STATES, SESSION_FILE

# ── Page Config ──
st.set_page_config(
    page_title="JPJ Number Checker",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──
st.markdown("""
<style>
    /* ── Fonts ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, #root, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background: #F8F6F3;
    }

    .main .block-container {
        max-width: 960px;
        padding: 2rem 1.5rem !important;
    }

    /* ── Typography ── */
    h1 {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
        color: #1C1917 !important;
    }

    h2 {
        font-size: 1.125rem !important;
        font-weight: 600 !important;
        color: #1C1917 !important;
    }

    h3 {
        font-size: 0.875rem !important;
        font-weight: 600 !important;
        color: #1C1917 !important;
    }

    p {
        font-size: 0.875rem !important;
        color: #78716C !important;
        line-height: 1.5 !important;
    }

    .text-muted {
        color: #A8A29E !important;
        font-size: 0.75rem !important;
    }

    .text-secondary {
        color: #78716C !important;
    }

    .fw-600 { font-weight: 600 !important; }

    /* ── Buttons ── */
    .stButton button {
        height: 44px !important;
        padding: 0 1.25rem !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.875rem !important;
        transition: all 0.15s ease !important;
        letter-spacing: -0.01em !important;
    }
    .stButton button[kind="primary"] {
        background: #2563EB !important;
        border: none !important;
        color: #FFFFFF !important;
        box-shadow: 0 1px 2px rgba(37,99,235,0.3) !important;
    }
    .stButton button[kind="primary"]:hover:not(:disabled) {
        background: #1D4ED8 !important;
        box-shadow: 0 4px 12px rgba(37,99,235,0.35) !important;
        transform: translateY(-1px) !important;
    }
    .stButton button[kind="primary"]:active:not(:disabled) {
        transform: translateY(0) !important;
        box-shadow: 0 1px 2px rgba(37,99,235,0.3) !important;
    }
    .stButton button[kind="primary"]:disabled {
        opacity: 0.4 !important;
        box-shadow: none !important;
        cursor: not-allowed !important;
    }

    /* ── Number Input ── */
    .stNumberInput label {
        font-weight: 600 !important;
        font-size: 0.8125rem !important;
        color: #57534E !important;
        margin-bottom: 0.25rem !important;
    }
    .stNumberInput input {
        height: 44px !important;
        border-radius: 10px !important;
        border: 1.5px solid #E7E5E4 !important;
        font-size: 1rem !important;
        font-weight: 500 !important;
        color: #1C1917 !important;
        padding: 0 0.875rem !important;
        transition: all 0.15s ease !important;
        background: #FFFFFF !important;
    }
    .stNumberInput input:focus {
        border-color: #2563EB !important;
        box-shadow: 0 0 0 3px rgba(37,99,235,0.1) !important;
    }
    .stNumberInput input::placeholder {
        color: #A8A29E !important;
    }
    div[data-testid="stNumberInput"] {
        padding-bottom: 0 !important;
    }

    /* ── Metrics ── */
    div[data-testid="metric-container"] {
        background: #FFFFFF;
        border: 1px solid #E7E5E4;
        border-radius: 12px;
        padding: 1.25rem 1rem !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        transition: box-shadow 0.15s ease;
    }
    div[data-testid="metric-container"]:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.06);
    }
    div[data-testid="metric-container"] label {
        font-size: 0.75rem !important;
        font-weight: 500 !important;
        color: #78716C !important;
        letter-spacing: 0 !important;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        font-size: 1.5rem !important;
        font-weight: 700 !important;
        color: #1C1917 !important;
        line-height: 1.2 !important;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricDelta"] {
        font-size: 0.75rem !important;
    }

    /* ── Progress Bar ── */
    .stProgress > div {
        height: 8px !important;
        border-radius: 99px !important;
        background: #E7E5E4 !important;
    }
    .stProgress > div > div {
        background: #2563EB !important;
        border-radius: 99px !important;
        transition: width 0.3s ease !important;
    }

    /* ── Custom Progress Card ── */
    .progress-card {
        background: #FFFFFF;
        border: 1px solid #E7E5E4;
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        margin-bottom: 1rem;
    }
    .progress-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 1rem;
    }
    .progress-dot {
        width: 10px;
        height: 10px;
        border-radius: 50%;
        flex-shrink: 0;
    }
    .progress-dot.running {
        background: #2563EB;
        animation: pulse 1.5s ease-in-out infinite;
    }
    .progress-dot.complete {
        background: #16A34A;
    }
    .progress-dot.error {
        background: #DC2626;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; transform: scale(1); }
        50% { opacity: 0.5; transform: scale(0.85); }
    }
    .progress-title {
        font-size: 0.875rem;
        font-weight: 600;
        color: #1C1917;
        flex: 1;
    }
    .progress-timer {
        font-size: 0.75rem;
        font-weight: 500;
        color: #A8A29E;
        font-variant-numeric: tabular-nums;
    }
    /* ── DataFrames / Tables ── */
    div[data-testid="stDataFrameResizable"] {
        border: 1px solid #E7E5E4 !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }
    div[data-testid="stDataFrameResizable"] thead tr th {
        background: #FAFAF9 !important;
        font-weight: 600 !important;
        font-size: 0.6875rem !important;
        color: #78716C !important;
        text-transform: uppercase !important;
        letter-spacing: 0.04em !important;
        padding: 0.75rem 1rem !important;
        border-bottom: 1px solid #E7E5E4 !important;
    }
    div[data-testid="stDataFrameResizable"] tbody tr td {
        padding: 0.625rem 1rem !important;
        font-size: 0.8125rem !important;
        color: #44403C !important;
        border-bottom: 1px solid #F5F5F4 !important;
    }
    div[data-testid="stDataFrameResizable"] tbody tr:last-child td {
        border-bottom: none !important;
    }
    div[data-testid="stDataFrameResizable"] tbody tr:hover {
        background: #FAFAF9 !important;
    }

    /* ── Status Badge ── */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.375rem;
        padding: 0.25rem 0.625rem;
        border-radius: 99px;
        font-size: 0.6875rem;
        font-weight: 600;
        letter-spacing: 0.01em;
    }
    .status-badge.active {
        background: #F0FDF4;
        color: #16A34A;
        border: 1px solid #BBF7D0;
    }
    .status-badge.inactive {
        background: #FEF2F2;
        color: #DC2626;
        border: 1px solid #FECACA;
    }
    .status-badge .dot {
        width: 6px;
        height: 6px;
        border-radius: 50%;
    }
    .status-badge.active .dot {
        background: #16A34A;
    }
    .status-badge.inactive .dot {
        background: #DC2626;
    }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {
        background: #FFFFFF !important;
        border-right: 1px solid #E7E5E4 !important;
    }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        font-size: 0.6875rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        color: #A8A29E !important;
        margin-bottom: 0.5rem !important;
    }
    section[data-testid="stSidebar"] .stMarkdown p {
        font-size: 0.8125rem !important;
        color: #78716C !important;
        line-height: 1.5 !important;
    }

    /* ── Dividers ── */
    hr {
        border-color: #E7E5E4 !important;
        margin: 1.5rem 0 !important;
        border-width: 0 0 1px 0 !important;
    }

    /* ── Alerts ── */
    .stAlert {
        border-radius: 10px !important;
        border: none !important;
        padding: 0.75rem 1rem !important;
    }
    .stAlert.st-info {
        background: #EFF6FF !important;
        color: #1E40AF !important;
    }
    .stAlert.st-warning {
        background: #FFFBEB !important;
        color: #92400E !important;
    }
    .stAlert.st-error {
        background: #FEF2F2 !important;
        color: #991B1B !important;
    }
    .stAlert.st-success {
        background: #F0FDF4 !important;
        color: #166534 !important;
    }

    /* ── Download Button ── */
    .stDownloadButton button {
        height: 40px !important;
        padding: 0 1.25rem !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.8125rem !important;
        border: 1.5px solid #E7E5E4 !important;
        background: #FFFFFF !important;
        color: #57534E !important;
        transition: all 0.15s ease !important;
    }
    .stDownloadButton button:hover {
        border-color: #D6D3D1 !important;
        background: #FAFAF9 !important;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04) !important;
    }

    /* ── Expander ── */
    .streamlit-expanderHeader {
        font-size: 0.8125rem !important;
        font-weight: 600 !important;
        color: #57534E !important;
        background: transparent !important;
        border: none !important;
        padding: 0.5rem 0 !important;
    }
    .streamlit-expanderContent {
        border: none !important;
        padding: 0.5rem 0 0 0 !important;
    }

    /* ── Checkbox ── */
    .stCheckbox label {
        font-size: 0.8125rem !important;
        font-weight: 500 !important;
        color: #57534E !important;
        gap: 0.5rem !important;
    }
    .stCheckbox label > div:first-child {
        border-radius: 4px !important;
    }

    /* ── Subheader spacing ── */
    .stSubheader {
        margin-top: 0 !important;
    }

    /* ── Hide Streamlit default elements ── */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stDeployButton {display: none;}
    div[data-testid="stToolbar"] {display: none;}
    div[data-testid="stDecoration"] {display: none;}
    div[data-testid="stStatusWidget"] {display: none;}

    /* ── Footer ── */
    .footer {
        margin-top: 2rem;
        padding-top: 1rem;
        border-top: 1px solid #E7E5E4;
        text-align: center;
        font-size: 0.75rem;
        color: #A8A29E;
    }
    .footer a {
        color: #A8A29E;
        text-decoration: none;
    }
    .footer a:hover {
        color: #78716C;
    }

    /* ── Responsive: small screens ── */
    @media (max-width: 820px) {
        .main .block-container {
            padding: 1rem 1rem !important;
        }
        h1 { font-size: 1.25rem !important; }
        div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
            font-size: 1.25rem !important;
        }
        .stButton button { height: 40px !important; font-size: 0.8125rem !important; }
        .stNumberInput input { height: 40px !important; font-size: 0.875rem !important; }
        .header-wrapper { flex-direction: column !important; align-items: stretch !important; }
        div[data-testid="stColumn"] { min-width: 0 !important; }
    }

    @media (max-width: 480px) {
        .main .block-container {
            padding: 0.75rem 0.75rem !important;
        }
        h1 { font-size: 1.125rem !important; }
        div[data-testid="stFormSubmitButton"] button { white-space: nowrap !important; font-size: 0.75rem !important; padding: 0 0.75rem !important; }
        .result-card { padding: 0.875rem !important; min-height: 100px !important; }
        .result-card .plate { font-size: 1.125rem !important; }
        .result-card .meta { flex-direction: column !important; gap: 0.25rem !important; }
        .status-badge { font-size: 0.625rem !important; padding: 0.2rem 0.5rem !important; }
    }

    /* ── Results grid (responsive) ── */
    .results-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 0.75rem;
    }
    .result-card {
        background: #FAFAF9;
        border: 1px solid #E7E5E4;
        border-radius: 14px;
        padding: 1.25rem;
        min-height: 130px;
    }
    .result-card .plate {
        font-size: 1.5rem;
        font-weight: 800;
        color: #0F172A;
        letter-spacing: 0.03em;
    }
    .result-card .state {
        font-size: 0.875rem;
        color: #64748B;
        margin-top: 0.5rem;
    }
    .result-card .meta {
        display: flex;
        gap: 1.25rem;
        margin-top: 0.625rem;
        font-size: 0.8125rem;
        color: #78716C;
    }
    .result-card .price {
        font-weight: 700;
        color: #0F172A;
    }
    @media (max-width: 768px) {
        .results-grid {
            grid-template-columns: 1fr;
        }
        .result-card .plate { font-size: 1.25rem; }
    }
</style>
""", unsafe_allow_html=True)

# ── Helpers ──
def _session_badge():
    """Return HTML for session status badge."""
    ok = SESSION_FILE.exists()
    cls = "active" if ok else "inactive"
    label = "Session Active" if ok else "No Session"
    return f'<span class="status-badge {cls}"><span class="dot"></span>{label}</span>'

def _progress_html(label, timer, progress_events=None, state="running"):
    """Return HTML for the custom progress card with available/not-available split."""
    dot_cls = state

    # Split events by availability
    avail_html = ""
    nope_html = ""
    if progress_events:
        avail = [e for e in progress_events if e.get("available")]
        nope = [e for e in progress_events if not e.get("available")]
        def _badge(e):
            p = f"{e['awalan']}{e.get('nombor','?')}".strip()
            return f"<span style='display:inline-flex; align-items:center; gap:4px; padding:3px 10px; border-radius:6px; font-size:0.75rem; font-weight:500; white-space:nowrap'>{p}</span>"
        if avail:
            avail_html = "<div style='margin-bottom:6px'><span style='font-size:0.75rem; font-weight:600; color:#166534'>Tersedia</span><div style='display:flex; flex-wrap:wrap; gap:4px; margin-top:4px'>" + \
                "".join(f"<span style='background:#F0FDF4; color:#166534; border:1px solid #BBF7D0; padding:3px 10px; border-radius:6px; font-size:0.75rem; font-weight:500'>{e['state']}</span>" for e in avail) + \
                "</div></div>"
        if nope:
            nope_html = "<div><span style='font-size:0.75rem; font-weight:600; color:#78716C'>Tidak Tersedia</span><div style='display:flex; flex-wrap:wrap; gap:4px; margin-top:4px'>" + \
                "".join(f"<span style='background:#F5F5F4; color:#78716C; border:1px solid #E7E5E4; padding:3px 10px; border-radius:6px; font-size:0.75rem; font-weight:400'>{e['state']}</span>" for e in nope) + \
                "</div></div>"

    info_text = ""
    if state == "running" and not progress_events:
        info_text = '<div style="font-size:0.8rem; color:#64748B; margin-top:4px">A browser window has opened. Log in to JPJ mySIKAP, then the scan will start automatically.</div>'

    log_section = ""
    if avail_html or nope_html:
        log_section = f'<div style="margin-top:8px">{avail_html}{nope_html}</div>'

    return f"""<div style="background:#FAFAF9; border:1px solid #E7E5E4; border-radius:10px; padding:12px 16px; margin-bottom:8px">
    <div style="display:flex; align-items:center; justify-content:space-between">
        <div style="display:flex; align-items:center; gap:8px">
            <span class="progress-dot {dot_cls}"></span>
            <span style="font-size:0.9rem; font-weight:600; color:#0F172A">{label}</span>
        </div>
        <span style="font-size:0.8rem; color:#78716C">{timer}</span>
    </div>
    {info_text}
    {log_section}
</div>"""


# ── Init session state ──
for key in ("results", "progress_log", "start_time", "_last_number", "stop_event", "stop_requested"):
    if key not in st.session_state:
        if key == "stop_event":
            st.session_state[key] = threading.Event()
        elif key == "progress_log":
            st.session_state[key] = []
        else:
            st.session_state[key] = None

# ── Header ──
st.markdown(
    f"<div class='header-wrapper' style='display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:0.75rem'>"
    f"<span style='font-size:1.375rem; font-weight:700; letter-spacing:-0.02em; color:#0F172A; white-space:nowrap'>JPJ Number Checker</span>"
    f"{_session_badge()}</div>",
    unsafe_allow_html=True,
)

with st.form("search_form", clear_on_submit=False):
    sub_cols = st.columns([2, 0.5], gap="small")
    with sub_cols[0]:
        number = st.number_input(
            "Number",
            min_value=1,
            max_value=9999,
            value=5275,
            label_visibility="collapsed",
            placeholder="Enter number 1–9999",
        )
    with sub_cols[1]:
        check_btn = st.form_submit_button(
            "Cari",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.get("running", False),
        )

st.markdown(
    "<p style='margin-top:-0.25rem; margin-bottom:0.5rem; font-size:0.8rem; color:#64748B'>"
    "A browser window will open for JPJ mySIKAP login. After you log in, all 32 states will be scanned automatically.</p>",
    unsafe_allow_html=True,
)

# ── Stop button (shown during scan) ──
if st.session_state.get("running", False):
    if st.button("\u23f9  Stop Scan", use_container_width=True):
        st.session_state.stop_requested = True
        st.rerun()

# ── Handle stop request from previous run ──
stop_ev = st.session_state.get("stop_event")
if st.session_state.get("stop_requested") and stop_ev is not None:
    stop_ev.set()
    st.session_state.stop_requested = False


# ── Scan Flow ──
if check_btn:
    st.session_state.results = None
    st.session_state.progress_log = []
    st.session_state.start_time = time.time()
    st.session_state.running = True
    st.session_state._last_number = number
    st.session_state.stop_event = threading.Event()

    # Containers for dynamic content
    progress_container = st.empty()
    progress_bar_container = st.empty()
    results_container = st.empty()

    progress_events = []
    progress_lock = threading.Lock()

    def on_progress(rd):
        with progress_lock:
            progress_events.append(rd)

    check_result = [None]
    check_error = [None]

    # Capture values before thread (st.session_state not safe in threads)
    _stop_ev = st.session_state.stop_event
    _debug = st.session_state.get("debug", False)

    def run_check():
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
            r = check_number(
                number,
                headless=False,
                debug=_debug,
                on_progress=on_progress,
                stop_event=_stop_ev,
                username=username or None,
                password=password or None,
            )
            check_result[0] = r
        except Exception as e:
            check_error[0] = e

    thread = threading.Thread(target=run_check, daemon=True)
    thread.start()

    last_count = 0
    while thread.is_alive() or len(progress_events) > last_count:
        # Check for STOP requested from module-level button
        if st.session_state.stop_event.is_set():
            break

        time.sleep(0.3)
        with progress_lock:
            current_count = len(progress_events)
            new_events = progress_events[last_count:]
            last_count = current_count

        elapsed = time.time() - st.session_state.start_time
        timer_str = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"

        if current_count == 0:
            progress_container.markdown(
                _progress_html(
                    "Waiting for login\u2026",
                    timer_str,
                    state="running",
                ),
                unsafe_allow_html=True,
            )
            progress_bar_container.progress(0, text="")
        else:
            total = len(PRODUCTION_STATES)
            done = current_count
            pct = min(done / total, 1.0)
            avail_count = sum(
                1 for e in progress_events[:current_count]
                if e.get("available")
            )

            progress_container.markdown(
                _progress_html(
                    f"Scanning\u2026  {done}/{total} states  \u2022  {avail_count} available",
                    timer_str,
                    progress_events=progress_events,
                    state="running",
                ),
                unsafe_allow_html=True,
            )
            progress_bar_container.progress(pct, text="")

    thread.join(timeout=5)

    elapsed = time.time() - st.session_state.start_time
    timer_str = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
    results = check_result[0]
    stopped = st.session_state.stop_event.is_set()

    # ── Completion ──
    if stopped:
        progress_container.markdown(
            _progress_html(
                "Stopped",
                timer_str,
                progress_events=progress_events,
                state="complete",
            ),
            unsafe_allow_html=True,
        )
        progress_bar_container.empty()
        if results:
            st.session_state.results = results
        st.info("Scan stopped by user.")
    elif check_error[0]:
        progress_container.markdown(
            _progress_html(
                "Error",
                timer_str,
                progress_events=progress_events,
                state="error",
            ),
            unsafe_allow_html=True,
        )
        progress_bar_container.empty()
        st.error(f"Error: {check_error[0]}")
    elif results is None or len(results) == 0:
        progress_container.markdown(
            _progress_html(
                "No results \u2014 login may have failed",
                timer_str,
                progress_events=progress_events,
                state="error",
            ),
            unsafe_allow_html=True,
        )
        progress_bar_container.empty()
        st.warning("Login failed or session expired. Try again.")
    else:
        avail_count = sum(1 for v in results.values() if v.get("available"))
        progress_container.markdown(
            _progress_html(
                f"Complete  \u2022  {len(results)} states checked  \u2022  {avail_count} available",
                timer_str,
                progress_events=progress_events,
                state="complete",
            ),
            unsafe_allow_html=True,
        )
        progress_bar_container.empty()
        st.session_state.results = results

        # Results section — only show available numbers
        with results_container:
            available = {
                k: v for k, v in results.items() if v.get("available")
            }

            if not available:
                st.markdown(
                    f"<div style='padding:2rem 1rem; text-align:center'>"
                    f"<div style='font-size:2rem; margin-bottom:0.75rem'>😕</div>"
                    f"<div style='font-size:1rem; font-weight:600; color:#78716C'>Tiada nombor tersedia</div>"
                    f"<div style='font-size:0.875rem; color:#A8A29E; margin-top:0.25rem'>"
                    f"Nombor #{number} tidak tersedia di mana-mana negeri</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(f"<div style='font-size:1.25rem; font-weight:700; margin-bottom:1rem'>#{number} tersedia di {len(available)} lokasi</div>", unsafe_allow_html=True)
                cards = []
                for k, v in available.items():
                    plate = f"{v['awalan']}{number}{v['akhiran']}".strip()
                    cards.append(
                        f"<div class='result-card'>"
                        f"<div class='plate'>{plate}</div>"
                        f"<div class='state'>{v['state']}</div>"
                        f"<div class='meta'>"
                        f"<span>Akhiran: @{v.get('akhiran', '-')}</span>"
                        f"<span class='price'>RM {v.get('harga', '300.00')}</span>"
                        f"</div></div>"
                    )
                st.markdown(
                    f"<div class='results-grid'>{''.join(cards)}</div>",
                    unsafe_allow_html=True,
                )

    st.session_state.running = False

# ── Idle: show last results ──
elif (
    st.session_state.results
    and not st.session_state.get("running", False)
):
    results = st.session_state.results
    num = st.session_state.get("_last_number", "?")
    available = {
        k: v for k, v in results.items() if v.get("available")
    }
    if not available:
        st.markdown(
            f"<div style='padding:2rem 1rem; text-align:center'>"
            f"<div style='font-size:2rem; margin-bottom:0.75rem'>😕</div>"
            f"<div style='font-size:1rem; font-weight:600; color:#78716C'>Tiada nombor tersedia</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f"<div style='font-size:1.25rem; font-weight:700; margin-bottom:1rem; margin-top:1rem'>#{num} tersedia di {len(available)} lokasi</div>", unsafe_allow_html=True)
        cards = []
        for k, v in available.items():
            plate = f"{v['awalan']}{num}{v['akhiran']}".strip()
            cards.append(
                f"<div class='result-card'>"
                f"<div class='plate'>{plate}</div>"
                f"<div class='state'>{v['state']}</div>"
                f"<div class='meta'>"
                f"<span>Akhiran: @{v.get('akhiran', '-')}</span>"
                f"<span class='price'>RM {v.get('harga', '300.00')}</span>"
                f"</div></div>"
            )
        st.markdown(
            f"<div class='results-grid'>{''.join(cards)}</div>",
            unsafe_allow_html=True,
        )

# ── Sidebar ──
with st.sidebar:
    st.markdown("### Login JPJ")
    username = st.text_input(
        "No. IC / Username",
        value=st.session_state.get("_jpj_user", ""),
        placeholder="000101-01-0000",
        label_visibility="collapsed",
    )
    password = st.text_input(
        "Password",
        type="password",
        value=st.session_state.get("_jpj_pass", ""),
        placeholder="••••••••",
        label_visibility="collapsed",
    )
    if username:
        st.session_state["_jpj_user"] = username
    if password:
        st.session_state["_jpj_pass"] = password
    st.caption("Fields will be pre-filled in the browser — you only need to enter the CAPTCHA.")

    st.divider()

    st.markdown("### Settings")
    debug = st.checkbox(
        "Debug mode",
        value=False,
        help="Save screenshots & log form state",
    )
    st.session_state["debug"] = debug

    st.divider()

    st.markdown("### About")
    st.markdown(
        "Checks JPJ mySIKAP for vehicle registration number availability "
        "across all 32 Malaysian states and districts."
    )

    st.divider()

    st.markdown("### Session")
    status = "Active" if SESSION_FILE.exists() else "Inactive"
    cls = "active" if SESSION_FILE.exists() else "inactive"
    st.markdown(
        f"<span class='status-badge {cls}'><span class='dot'></span>{status}</span>",
        unsafe_allow_html=True,
    )
    if SESSION_FILE.exists():
        st.markdown(
            f"<p class='text-muted' style='margin-top:0.5rem'>"
            f"Last saved: {datetime.fromtimestamp(SESSION_FILE.stat().st_mtime).strftime('%H:%M, %d %b %Y')}"
            f"</p>",
            unsafe_allow_html=True,
        )

    st.divider()

    if st.button("Clear Cache", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    # ── Footer ──
    st.markdown(
        "<div class='footer'>"
        "JPJ Number Checker &middot; v1.0"
        "</div>",
        unsafe_allow_html=True,
    )
