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

st.set_page_config(
    page_title="JPJ Number Checker",
    page_icon="🚗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Init session state ──
for key in ("results", "progress_log", "start_time", "_last_number"):
    if key not in st.session_state:
        st.session_state[key] = None if key in ("results", "start_time", "_last_number") else []

# ── Sidebar ──
with st.sidebar:
    st.markdown("### ⚙️ Settings")
    debug = st.checkbox("Debug mode", value=False,
                        help="Save screenshots & log form state")
    st.divider()
    st.markdown("### ℹ️ About")
    st.markdown(
        "Checks JPJ mySIKAP for available registration numbers. "
        "Scans all 32 states/districts automatically."
    )

# ── Main ──
st.title("🚗 JPJ Number Plate Checker")
st.markdown("Check if a registration number is available across **all 32 Malaysian states & districts**.")

col1, col2 = st.columns([2, 1])
with col1:
    number = st.number_input(
        "Number to check", min_value=1, max_value=9999, value=5275,
        help="Enter a number between 1 and 9999",
    )
with col2:
    st.write("")
    st.write("")
    check_btn = st.button(
        "🔍 Check Number", type="primary", use_container_width=True,
        disabled=st.session_state.get("running", False),
    )

if check_btn:
    st.session_state.results = None
    st.session_state.progress_log = []
    st.session_state.start_time = time.time()
    st.session_state.running = True
    st.session_state._last_number = number

    status_box = st.status("Starting...", expanded=True)
    progress_text = status_box.empty()
    progress_bar = st.progress(0, text="")
    results_area = st.container()

    progress_events = []
    progress_lock = threading.Lock()

    def on_progress(rd):
        with progress_lock:
            progress_events.append(rd)

    check_result = [None]
    check_error = [None]

    def run_check():
        try:
            # Delete saved session so it forces login every time
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
            r = check_number(
                number,
                headless=False,
                debug=debug,
                on_progress=on_progress,
            )
            check_result[0] = r
        except Exception as e:
            check_error[0] = e

    thread = threading.Thread(target=run_check, daemon=True)
    thread.start()

    last_count = 0
    while thread.is_alive() or len(progress_events) > last_count:
        time.sleep(0.3)
        with progress_lock:
            current_count = len(progress_events)
            new_events = progress_events[last_count:]
            last_count = current_count

        elapsed = time.time() - st.session_state.start_time

        if current_count == 0:
            # Waiting for login
            status_box.update(
                label=f"⏳ Browser opened — please log into JPJ... ({elapsed:.0f}s)",
                state="running",
            )
            progress_text.info(
                "A browser window has opened. Log into JPJ mySIKAP, "
                "then the scan will start automatically."
            )
            progress_bar.progress(0, text="Waiting for login...")
        else:
            for rd in new_events:
                icon = "✅" if rd.get("available") else "❌"
                nombor = rd.get("nombor", "?")
                status = rd.get("status_text", "?")
                state = rd.get("state", "?")
                st.session_state.progress_log.append(
                    f"{icon} {state:30s} {nombor:15s} {status}"
                )

            total = len(PRODUCTION_STATES)
            done = current_count
            pct = min(done / total, 1.0)
            avail_count = sum(
                1 for e in progress_events[:current_count]
                if e.get("available")
            )

            status_box.update(
                label=(
                    f"Scanning... {done}/{total} states  |  "
                    f"✅ {avail_count} available  |  ⏱️ {elapsed:.0f}s"
                ),
                state="running",
            )
            log_text = "\n".join(st.session_state.progress_log[-15:])
            progress_text.code(log_text, language="")
            progress_bar.progress(pct, text=f"{pct:.0%}")

    thread.join(timeout=5)
    elapsed = time.time() - st.session_state.start_time
    results = check_result[0]

    if check_error[0]:
        status_box.update(label="❌ Error", state="error")
        st.error(f"Error: {check_error[0]}")
    elif results is None or len(results) == 0:
        status_box.update(
            label="❌ No results — login may have failed", state="error"
        )
        st.warning("Login failed or session expired. Try again.")
    else:
        status_box.update(
            label=f"✅ Done — {len(results)} states in {elapsed:.0f}s",
            state="complete",
        )
        progress_bar.empty()
        st.session_state.results = results

        available = {
            k: v for k, v in results.items() if v.get("available")
        }
        unavailable = {
            k: v for k, v in results.items() if not v.get("available")
        }

        with results_area:
            st.subheader(f"📊 Results for **{number}**")
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("States Checked", len(results))
            mc2.metric("✅ Available", len(available))
            mc3.metric("❌ Unavailable", len(unavailable))
            mc4.metric("⏱️ Time", f"{elapsed:.0f}s")

            if available:
                st.success(
                    f"🎉 Available in **{len(available)}** locations!"
                )
                avail_rows = [
                    {
                        "Plate Number":
                            f"{v['awalan']}{number}{v['akhiran']}".strip(),
                        "State": v["state"],
                        "Price (RM)": v.get("harga", "300.00"),
                    }
                    for k, v in available.items()
                ]
                st.dataframe(
                    avail_rows, use_container_width=True, hide_index=True
                )
            else:
                st.error(f"❌ Not available in any state.")

            with st.expander(
                "📋 View full results by state", expanded=False
            ):
                all_rows = [
                    {
                        "Plate":
                            f"{v['awalan']}{number}{v['akhiran']}".strip(),
                        "State": v["state"],
                        "Status":
                            "✅ Available" if v["available"] else "❌ Taken",
                        "Price": v.get("harga", "300.00"),
                    }
                    for k, v in results.items()
                ]
                st.dataframe(
                    all_rows, use_container_width=True, hide_index=True
                )

            output = {
                "timestamp": datetime.now().isoformat(),
                "number": number,
                "elapsed_seconds": round(elapsed, 1),
                "summary": {
                    "checked": len(results),
                    "available": len(available),
                    "unavailable": len(unavailable),
                },
                "results": results,
            }
            st.download_button(
                "💾 Download JSON",
                data=json.dumps(output, indent=2, ensure_ascii=False),
                file_name=(
                    f"jpj_{number}_"
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                ),
                mime="application/json",
                use_container_width=True,
            )

    st.session_state.running = False

# ── Idle: show last results ──
if (
    st.session_state.results
    and not st.session_state.get("running", False)
):
    results = st.session_state.results
    num = st.session_state.get("_last_number", "?")
    available = {
        k: v for k, v in results.items() if v.get("available")
    }
    st.subheader("📊 Last Results")
    mc1, mc2 = st.columns(2)
    mc1.metric("States Checked", len(results))
    mc2.metric("✅ Available", len(available))
    if available:
        rows = [
            {
                "Plate": f"{v['awalan']}{num}{v['akhiran']}".strip(),
                "State": v["state"],
            }
            for k, v in available.items()
        ]
        st.dataframe(rows, use_container_width=True, hide_index=True)
