#!/usr/bin/env python3
"""
JPJ Vehicle Number Plate Checker — check if a specific number is available
across all states/series.

Every scan opens a fresh browser window: you log in once (password +
CAPTCHA typed by you), the window MINIMIZES itself and the scan of all
32 states/series runs in the background. Verbose progress is reported
through the on_status/on_progress callbacks. No session is persisted —
a new number means a new window and a fresh login.

Usage:
  python3 jpj_automation.py --number 888
  python3 jpj_automation.py --number 1234 --states 10 14
  python3 jpj_automation.py --number 777 --output result.json
  python3 jpj_automation.py --number 888 --visible   # keep window un-minimized
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, TimeoutError as PwTimeout,
)

PROD_BASE = "https://public.jpj.gov.my/public/"
LOGIN_URL = PROD_BASE

BASE_DIR = Path(__file__).parent
SESSION_DIR = BASE_DIR / "sessions"  # legacy debug artifacts only
OUTPUT_DIR = BASE_DIR / "output"

# JPJ Production state mappings — real JPJ combobox text per state.
# Sabah/Sarawak have district-level options instead of single state.
# EXCLUDED: Putrajaya (F prefix, code 16) & Labuan (L prefix, code 15) —
#   plates can only be used in those territories, not transferable.
#   Labuan also doesn't appear in the JPJ dropdown at all.
PRODUCTION_STATES = [
    ("01", "JOHOR", "JOHOR"),
    ("02", "KEDAH", "KEDAH"),
    ("03", "KELANTAN", "KELANTAN"),
    ("04", "MELAKA", "MELAKA"),
    ("05", "NEGERI SEMBILAN", "NEGERI SEMBILAN"),
    ("06", "PAHANG", "PAHANG"),
    ("07", "PULAU PINANG", "PULAU PINANG"),
    ("08", "PERAK", "PERAK"),
    ("09", "PERLIS", "PERLIS"),
    ("10", "SELANGOR", "SELANGOR"),
    ("11", "TERENGGANU", "TERENGGANU"),
    ("12", "SABAH (BEAUFORT)", "BEAUFORT"),
    ("12", "SABAH (KENINGAU)", "KENINGAU"),
    ("12", "SABAH (KOTA KINABALU)", "KOTA KINABALU"),
    ("12", "SABAH (KUDAT)", "KUDAT"),
    ("12", "SABAH (LAHAD DATU)", "LAHAD DATU"),
    ("12", "SABAH (SANDAKAN)", "SANDAKAN"),
    ("12", "SABAH (TAWAU)", "TAWAU"),
    ("13", "SARAWAK (BETONG)", "BETONG"),
    ("13", "SARAWAK (BINTULU)", "BINTULU"),
    ("13", "SARAWAK (KAPIT)", "KAPIT"),
    ("13", "SARAWAK (KOTA SAMARAHAN)", "KOTA SAMARAHAN"),
    ("13", "SARAWAK (KUCHING)", "KUCHING"),
    ("13", "SARAWAK (LIMBANG)", "LIMBANG"),
    ("13", "SARAWAK (LAWAS)", "LAWAS"),
    ("13", "SARAWAK (MIRI)", "MIRI"),
    ("13", "SARAWAK (SARIKEI)", "SARIKEI"),
    ("13", "SARAWAK (SIBU)", "SIBU"),  # SIBU & MUKAH share series QS — satu carian cukup
    ("13", "SARAWAK (SRI AMAN)", "SRI AMAN"),
    ("14", "KUALA LUMPUR", "WILAYAH PERSEKUTUAN KUALA LUMPUR"),
]


def _ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)  # kept for debug artifacts


def _is_login_page(page) -> bool:
    """Check if current page is a login page (not post-login dashboard)."""
    try:
        url = page.url.lower()
        if 'login.zul' in url or 'login' in url and 'jpj' in url:
            return True
        username_visible = page.evaluate(
            """() => {
                const u = document.getElementById('txtusername');
                return u && u.offsetParent !== null;
            }"""
        )
        return username_visible
    except Exception:
        return False


def _is_logged_in(page) -> bool:
    """Check if user is logged in (post-login page with tabs/nav)."""
    try:
        result = page.evaluate("""() => {
            // "Log Keluar" anywhere = definitive logged-in
            const allEls = document.querySelectorAll('a, span, button, div');
            for (const el of allEls) {
                if (el.textContent.includes('Log Keluar')) return true;
            }
            // Post-login popup (baseModLanding) with "Ok" button = logged in
            const popup = document.querySelector('.z-messagebox-window, .z-messagebox');
            if (popup && popup.offsetParent !== null) {
                const btn = popup.querySelector('button');
                if (btn && btn.textContent.trim().toLowerCase() === 'ok') return true;
            }
            // Must have main tabs (z-tabbox) visible
            const tb = document.querySelector('.z-tabbox');
            if (!tb || tb.offsetParent === null) return false;
            // Must NOT have visible login form
            const u = document.getElementById('txtusername');
            if (u && u.offsetParent !== null) return false;
            // Check wrap for user name
            const wrap = document.getElementById('wrap');
            if (wrap && wrap.offsetParent !== null &&
                /[A-Z]+/.test(wrap.textContent)) return true;
            // tabbox without login form is sufficient
            return true;
        }""")
        return bool(result)
    except Exception:
        return False


class LoginFailed(Exception):
    """Raised when the user could not complete manual login."""


def _minimize_window(page):
    """Minimize the browser window via CDP; the page keeps running."""
    try:
        cdp = page.context.new_cdp_session(page)
        # Resolve the REAL windowId for this page's target
        win = cdp.send("Browser.getWindowForTarget")
        cdp.send("Browser.setWindowBounds", {
            "windowId": win["windowId"],
            "bounds": {"windowState": "minimized"},
        })
        cdp.detach()
        return True
    except Exception:
        return False


# Menu labels that open the reserve-number search page
_MENU_EXACT = [
    "Semak No. Pendaftaran Semasa",
    "Pembelian Nombor Pendaftaran Semasa",
    "Tempahan No. Pendaftaran",
]
_MENU_PATTERNS = [
    r"semak\s+no\.?\s*pendaftaran",
    r"pembelian\s+nombor\s+pendaftaran",
    r"tempahan\s+no\.?\s*pendaftaran",
]


def _click_visible_text(page, pattern, exclude_anchors=True):
    """Click the first visible element matching a text pattern.
    Anchors (<a>) are skipped by default so we never navigate away
    (external manual/info links match the same words)."""
    try:
        matches = page.locator(f"text=/{pattern}/i" if isinstance(pattern, str) and any(c in pattern for c in r"\+?(") else f"text={pattern}")
    except Exception:
        return False
    try:
        n = matches.count()
    except Exception:
        return False
    for i in range(min(n, 12)):
        try:
            el = matches.nth(i)
            ok = el.evaluate(
                "e => e.tagName !== 'A' && e.offsetParent !== null"
            )
            if ok:
                el.click(timeout=2000)
                return True
        except Exception:
            continue
    return False


def _open_reserve_page_via_menu(page):
    """Open the reserve-number page by clicking the REAL mySIKAP menu,
    exactly like a user would. Tries exact menu labels first, then loose
    patterns; skips anchor links to avoid navigating off-site."""
    candidates = [re.escape(t) for t in _MENU_EXACT] + _MENU_PATTERNS
    # Direct attempt
    for pat in candidates:
        if _click_visible_text(page, pat):
            return True
    # May be inside the Kenderaan dropdown — open it, retry
    if _click_visible_text(page, r"kenderaan"):
        page.wait_for_timeout(800)
        for pat in candidates:
            if _click_visible_text(page, pat):
                return True
    return False


def _back_to_search_form(page):
    """After a successful result, JPJ switches to the result tab
    (Senarai Nombor / Maklumat Nombor Tempahan) — click 'Kembali'
    and/or the search tab to return to the search form."""
    # The search tab is always clickable (searchNoTabId in captured traffic)
    try:
        tab = page.locator(".z-tab-hm").filter(
            has_text="Carian No. Pendaftaran"
        ).first
        if tab.is_visible(timeout=1000):
            tab.click()
            page.wait_for_timeout(600)
    except Exception:
        pass
    # Kembali buttons (backToSearchButtonId / backToButtonId)
    for sel in ("#backToSearchButtonId", "#backToButtonId"):
        try:
            btn = page.locator(sel)
            if btn.count() and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(800)
                return True
        except Exception:
            continue
    try:
        btn = page.locator("button").filter(
            has_text=re.compile(r"kembali", re.I)
        ).first
        if btn.is_visible(timeout=600):
            btn.click()
            page.wait_for_timeout(800)
            return True
    except Exception:
        pass
    return False


def _ensure_search_form(page):
    """Re-establish the search form before EVERY search.

    The JPJ server removes and re-renders the whole reserve-number window
    after each Cari: Kategori resets to '-- Sila Pilih --', the search
    form is hidden again, and all combobox widgets get NEW UUIDs. After a
    successful result the result tab stays open — 'Kembali' must be
    clicked first. Without re-establishing, every state after the first
    search fails silently.

    Cheap when the form is intact: the kategori select fast-path skips
    both AU round-trips if the value is already correct.
    """
    # If we're sitting on a result tab, go back to the search form first
    try:
        result_visible = page.locator("#searchTableId").first.is_visible()
    except Exception:
        result_visible = False
    if not result_visible:
        _back_to_search_form(page)

    _zk_api_select_option(
        page,
        "#seriesCategoryTableId .z-combobox-rounded-inp",
        "Nombor Pendaftaran Semasa",
    )
    try:
        page.wait_for_selector("#searchTableId", state="visible", timeout=15_000)
        return True
    except Exception:
        # One more attempt: back + kategori again
        _back_to_search_form(page)
        try:
            _zk_api_select_option(
                page,
                "#seriesCategoryTableId .z-combobox-rounded-inp",
                "Nombor Pendaftaran Semasa",
            )
            page.wait_for_selector("#searchTableId", state="visible", timeout=10_000)
            return True
        except Exception:
            return False


def _resolve_combo_ids(page):
    """Resolve FRESH combobox widget ids (the server assigns new UUIDs
    to every combobox when it re-renders the form after a search)."""
    return page.evaluate("""() => {
        const inputs = document.querySelectorAll(
            '#searchTableId .z-combobox-inp.z-combobox-readonly');
        return {
            negeri: inputs.length > 0 ? inputs[0].id.replace('-real','') : null,
            awalan: inputs.length > 1 ? inputs[1].id.replace('-real','') : null,
            akhiran: inputs.length > 2 ? inputs[2].id.replace('-real','') : null,
            mode: inputs.length > 3 ? inputs[3].id.replace('-real','') : null,
        };
    }""")


def _interactive_login(page, timeout=300, on_status=None) -> bool:
    """Wait for the user to log in manually in the VISIBLE browser window
    (username, password and CAPTCHA typed by the user). Detection is
    automatic. Returns True on success."""
    def say(msg):
        if on_status:
            on_status(msg)
    print("\n" + "=" * 54)
    print("              LOGIN JPJ mySIKAP DIPERLUKAN               ")
    print("=" * 54)
    print(" 1. Masukkan username & password                        ")
    print(" 2. Taip CAPTCHA yang dipaparkan                        ")
    print(" 3. Klik 'Log Masuk'                                    ")
    print(" Tetingkap akan minimize sendiri selepas login.         ")
    print("=" * 54 + "\n")
    say("Sila login di tetingkap JPJ yang terbuka (password + CAPTCHA)...")
    try:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if _is_logged_in(page):
                page.wait_for_load_state("networkidle", timeout=15_000)
                print("  Login berjaya dikesan!")
                say("Login berjaya — tetingkap JPJ akan minimize, scan bermula...")
                return True
            time.sleep(1)
        print("  Tamat masa login (5 minit). Cuba lagi.")
        say("Tamat masa login (5 minit).")
        return False
    except Exception as e:
        print(f"  Ralat tunggu login: {e}")
        return False


# ── ZK Helpers (production mode) ──


def _zk_open_popup(page, input_el, pp_id):
    """Open a ZK combobox popup by clicking the input or trigger button.
    Tries natural opening first, then force-shows via JS as last resort.
    Returns True if popup is visible (natural or forced)."""
    # Click the input to focus and trigger ZK AU to load items
    try:
        input_el.click(timeout=5000)
    except Exception:
        pass
    page.wait_for_load_state("networkidle", timeout=5000)
    page.wait_for_timeout(500)

    # Try clicking the dropdown button if it exists
    try:
        btn_sel = f"#{pp_id.replace('-pp', '')}-btn, #z-combobox-btn"
        btn = page.locator(btn_sel).first
        if btn.is_visible(timeout=1000):
            btn.click(timeout=3000)
            page.wait_for_timeout(500)
            page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass

    # Wait for popup to appear naturally (ZK AU may need to fetch items)
    for _ in range(15):
        vis = page.evaluate(
            "(ppId) => { const e = document.getElementById(ppId); return e && e.offsetParent !== null && e.style.display !== 'none' }",
            pp_id
        )
        if vis:
            return True
        page.wait_for_timeout(200)

    # Fallback: try keyboard Alt+ArrowDown
    try:
        page.keyboard.press("Alt+ArrowDown")
        page.wait_for_timeout(500)
        page.wait_for_load_state("networkidle", timeout=5000)
        for _ in range(10):
            vis = page.evaluate(
                "(ppId) => { const e = document.getElementById(ppId); return e && e.offsetParent !== null && e.style.display !== 'none' }",
                pp_id
            )
            if vis:
                return True
            page.wait_for_timeout(200)
    except Exception:
        pass

    # Force-show via JS as last resort — items will have bounding boxes
    page.evaluate("""(ppId) => {
        const pp = document.getElementById(ppId);
        if (!pp) return;
        pp.style.removeProperty('display');
        pp.style.removeProperty('visibility');
        pp.style.display = 'block';
        pp.style.visibility = 'visible';
    }""", pp_id)
    page.wait_for_timeout(300)

    # Verify popup is visible now
    vis = page.evaluate(
        "(ppId) => { const e = document.getElementById(ppId); return e && e.offsetParent !== null && e.style.display !== 'none' }",
        pp_id
    )
    return vis



def _zk_dismiss_popups(page):
    """Dismiss any ZK error/info popups and modal masks.
    Tries clicking OK/Tutup buttons first, then removes overlays."""
    # First try clicking OK/Tutup buttons to properly dismiss
    for _ in range(3):
        clicked = False
        try:
            btn = page.locator("button.z-button-os").filter(
                has_text=re.compile(r"(ok|tutup|close|ya)", re.I)
            ).first
            if btn.count() > 0:
                btn.click(force=True, timeout=2000)
                page.wait_for_timeout(400)
                clicked = True
                continue
        except Exception:
            pass
        if not clicked:
            break

    # Then remove any remaining overlays via JS
    page.evaluate("""() => {
        document.querySelectorAll('.z-modal-mask').forEach(el => el.remove());
        document.querySelectorAll('.z-modal').forEach(el => el.style.display = 'none');
        document.querySelectorAll('.z-messagebox, .z-messagebox-window, .z-errorbox')
            .forEach(el => el.remove());
    }""")
    page.wait_for_timeout(200)


HARGA_SEMASA = "310.00"


def _zk_parse_result(page, awalan, nombor, akhiran=""):
    """Parse result from Senarai Nombor listbox after clicking Cari.
    Checks the result listbox FIRST (the common case) — the error popup
    only gets a short wait when no result is present."""
    num_str = str(nombor)
    awalan = awalan.strip()
    akhiran = akhiran.strip() if akhiran else ""
    try:
        page.wait_for_timeout(300)

        # Common path: a result listbox containing prefix + number
        try:
            body = page.locator(".z-listbox-body").filter(
                has_text=awalan
            ).filter(
                has_text=num_str
            ).first
            text = body.text_content(timeout=2500).strip()
        except Exception:
            text = ""

        if text:
            import re as _re
            num_pat = _re.compile(rf"(?<!\d){_re.escape(num_str)}(?!\d)")
            if awalan in text and num_pat.search(text.replace(",", "")):
                idx = text.find(awalan)
                harga = text[:idx].strip()
                return {
                    "available": True,
                    "status_text": "Tersedia",
                    "harga": HARGA_SEMASA,
                }

        # No result — check for the "No. Tempahan Tidak Wujud" popup
        try:
            error_box = page.locator(".z-messagebox-window, .z-messagebox").filter(
                has_text="Tidak Wujud"
            ).first
            if error_box.is_visible(timeout=700):
                close_btn = error_box.locator("button").filter(
                    has_text=re.compile(r"tutup|ok|close", re.I)
                ).first
                if close_btn.is_visible(timeout=800):
                    close_btn.click()
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(600)
                return {"available": False, "status_text": "No. Tempahan Tidak Wujud"}
        except Exception:
            pass

        _zk_dismiss_popups(page)
        return {"available": False, "status_text": "Tidak Tersedia"}
    except Exception:
        return {"available": False, "status_text": "Tidak Tersedia"}


# ── ZK Direct API Helpers (bypass DOM/CSS issues) ──


def _zk_api_fire(page, widget_id, event_name, data):
    """Fire a ZK event to the server via widget JS API.
    Returns True if widget was found and event fired."""
    return page.evaluate(
        """(args) => {
            const [wid, evt, d] = args;
            try {
                const wgt = zk.Widget.$(wid);
                if (!wgt) return false;
                wgt.fire(evt, d, {toServer: true});
                return true;
            } catch(e) { return false; }
        }""",
        [widget_id, event_name, data]
    )


def _zk_api_strip_real(widget_id):
    """Strip ZK's -real suffix from input element IDs to get widget UUID."""
    if widget_id and widget_id.endswith('-real'):
        return widget_id[:-5]
    return widget_id


def _zk_api_get_widget_id(page, css_selector):
    """Get ZK widget UUID from a CSS selector matching the DOM element."""
    try:
        el = page.locator(css_selector).first
        el_id = el.get_attribute("id", timeout=5000)
        return _zk_api_strip_real(el_id)
    except Exception:
        return None


def _zk_api_get_items(page, combo_widget_id):
    """Get all Comboitem labels and UUIDs from a combobox widget.
    ZK 5.0.7 stores items as child widgets (firstChild/nextSibling),
    NOT in _items or getItems().
    Returns list of {uuid, label, label_raw} where label is trimmed
    and label_raw preserves original spacing/padding."""
    wid = _zk_api_strip_real(combo_widget_id)
    return page.evaluate(
        """(wid) => {
            try {
                const wgt = zk.Widget.$(wid);
                if (!wgt) return [];
                const result = [];
                let child = wgt.firstChild;
                while (child) {
                    const raw = child.getLabel ? child.getLabel() : child._label || '';
                    if (raw !== undefined && raw !== null) {
                        result.push({
                            uuid: child.uuid,
                            label: raw.trim(),
                            label_raw: raw,
                        });
                    }
                    child = child.nextSibling;
                }
                return result;
            } catch(e) { return []; }
        }""",
        wid
    )


def _zk_api_select_option(page, css_selector, option_label, item_uuid=None):
    """Select a combobox option by label using ZK JS API.

    Replicates the EXACT real-browser event sequence (from captured traffic):
      req 1: onChange(value) + onSelect(items:[uuid], reference:uuid)  — batched
      resp 1: server re-renders dependent widgets
      req 2: duplicate onChange(value) — triggers dependent-list refresh

    The duplicate onChange is required: without it the server does not
    populate dependent comboboxes (awalan/akhiran) for some states.

    Fast-path: if the combobox already holds this value, nothing is fired
    (server state is already correct — saves two AU round-trips).
    item_uuid: pre-resolved option UUID, skips the items fetch.
    """
    page.wait_for_timeout(80)

    if css_selector.startswith('#') and ' ' not in css_selector and '.' not in css_selector:
        widget_id = _zk_api_strip_real(css_selector[1:])
    else:
        widget_id = _zk_api_get_widget_id(page, css_selector)
    if not widget_id:
        raise Exception(f"Cannot find widget for: {css_selector}")

    # Fast-path: already selected?
    already = page.evaluate(
        """(args) => {
            const [wid, label] = args;
            try {
                const wgt = zk.Widget.$(wid);
                if (wgt && wgt.getValue) {
                    return (wgt.getValue() || '').trim() === label.trim();
                }
                const inp = document.getElementById(wid + '-real');
                if (inp) return inp.value.trim() === label.trim();
                return false;
            } catch(e) { return false; }
        }""",
        [widget_id, option_label]
    )
    if already:
        return option_label

    # Resolve the item UUID for onSelect (use caller's if provided)
    target_uuid = item_uuid
    if not target_uuid:
        items = _zk_api_get_items(page, widget_id)
        for item in items:
            if item["label"].replace('\xa0', ' ').strip() == option_label.strip():
                target_uuid = item["uuid"]
                break

    # Batch 1: onChange + onSelect in the same AU request (like the browser)
    fired = page.evaluate(
        """(args) => {
            const [wid, label, uuid] = args;
            try {
                const wgt = zk.Widget.$(wid);
                if (!wgt) return false;
                wgt.fire('onChange', {value: label, start: 0}, {toServer: true});
                if (uuid) {
                    wgt.fire('onSelect', {items: [uuid], reference: uuid},
                             {toServer: true});
                }
                return true;
            } catch(e) { return false; }
        }""",
        [widget_id, option_label, target_uuid]
    )
    if not fired:
        raise Exception(f"Cannot fire onChange on {widget_id}")

    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass
    page.wait_for_timeout(120)

    # Batch 2: duplicate onChange — the real browser sends this after the
    # re-render; it triggers the dependent dropdown refresh server-side.
    page.evaluate(
        """(args) => {
            const [wid, label] = args;
            try {
                const wgt = zk.Widget.$(wid);
                if (wgt) wgt.fire('onChange', {value: label, start: 0},
                                  {toServer: true});
            } catch(e) {}
        }""",
        [widget_id, option_label]
    )
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass
    page.wait_for_timeout(80)
    return option_label


def _zk_api_fill_number(page, number_str):
    """Fill the number input and immediately click Cari.
    Both events fire in the same ZK AU batch request (like real browser)."""
    num_widget_id = _zk_api_get_widget_id(page, "#searchTableId .z-intbox")
    if not num_widget_id:
        raise Exception("Cannot find number input widget")

    # Find Cari button widget ID
    cari_widget_id = page.evaluate("""() => {
        const btns = document.querySelectorAll('button.z-button-os');
        for (const btn of btns) {
            if (btn.textContent.trim().toLowerCase() === 'cari') {
                const wgt = zk.Widget.$(btn.id);
                return wgt ? wgt.uuid : btn.id;
            }
        }
        const inp = document.querySelector('#searchTableId .z-intbox');
        if (!inp) return null;
        const tbl = inp.closest('table');
        if (!tbl) return null;
        const allBtns = tbl.querySelectorAll('button');
        for (const btn of allBtns) {
            if (btn.textContent.trim().toLowerCase() === 'cari') {
                const wgt = zk.Widget.$(btn.id);
                return wgt ? wgt.uuid : btn.id;
            }
        }
        return null;
    }""")

    if not cari_widget_id:
        raise Exception("Cannot find Cari button widget")

    # Fire number onChange + Cari onClick in ONE evaluate (batched AU)
    page.evaluate(
        """(args) => {
            const [numId, numVal, cariId] = args;
            try {
                const nw = zk.Widget.$(numId);
                if (nw) {
                    nw.setValue(numVal);
                    nw.fire('onChange', {value: parseInt(numVal), start: numVal.length},
                            {toServer: true});
                }
                const inp = document.getElementById(numId + '-real');
                if (inp) inp.value = numVal;
            } catch(e) {}
            try {
                const cw = zk.Widget.$(cariId);
                if (cw) {
                    cw.fire('onClick', {pageX: 0, pageY: 0, which: 1, x: 0, y: 0},
                            {toServer: true});
                } else {
                    const btn = document.getElementById(cariId);
                    if (btn) btn.click();
                }
            } catch(e) {}
        }""",
        [num_widget_id, number_str, cari_widget_id]
    )

    # Wait for result
    page.wait_for_timeout(100)
    page.wait_for_load_state("networkidle", timeout=15_000)
    page.wait_for_timeout(50)


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------
_DEBUG = False

def _zk_debug_enable(enable=True):
    global _DEBUG
    _DEBUG = enable


# ── Per-state check (extracted for reuse in parallel mode) ──


def _check_single_state(page, code, state_name, jpj_state, num_str, stop_event=None,
                        on_status=None, prefix_cache=None):
    """Check availability for one state/district.
    Returns a result dict ('Dilangkau …' statuses for skips) or
    '__SESSION_LOST__' if disconnected."""
    def say(msg):
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    def skip(reason):
        return {
            "state": state_name,
            "awalan": "", "akhiran": "", "finale": "",
            "nombor": f"??? {num_str}",
            "available": False,
            "status_text": f"Dilangkau ({reason})",
            "harga": "",
        }

    try:
        page.evaluate("1+1")
    except Exception:
        return "__SESSION_LOST__"

    try:
        _zk_dismiss_popups(page)
    except Exception:
        pass

    # The server re-renders the whole form after every search (kategori
    # resets, search form hides, comboboxes get new UUIDs) — re-establish
    # it before each state. Cheap fast-path when already intact.
    try:
        if not _ensure_search_form(page):
            # Form destroyed (e.g. after a result) — reopen via menu
            if not _open_reserve_page_via_menu(page):
                return skip("borang carian hilang selepas carian terdahulu")
            page.wait_for_timeout(1000)
            try:
                page.wait_for_load_state("networkidle", timeout=10_000)
            except Exception:
                pass
            if not _ensure_search_form(page):
                return skip("borang carian tak dapat dipulihkan")
    except Exception as e:
        return skip(f"ralat borang: {e}")

    # FRESH combobox ids — mandatory after every re-render
    try:
        ids = _resolve_combo_ids(page)
    except Exception as e:
        return skip(f"ralat resolve combobox: {e}")
    if not ids.get("negeri") or not ids.get("awalan"):
        return skip("borang carian tidak lengkap")

    # Negeri (duplicate-onChange refresh — matches real browser)
    try:
        _zk_api_select_option(page, f"#{ids['negeri']}", jpj_state)
    except Exception as e:
        return skip(f"gagal pilih negeri: {e}")

    # Awalan — enumerate ALL prefixes via fresh widget id
    try:
        awalan_items = _zk_api_get_items(page, ids["awalan"]) or []
        if not awalan_items:
            _zk_api_fire(page, ids["awalan"], 'onChange', {"value": "", "start": 0})
            page.wait_for_timeout(300)
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            awalan_items = _zk_api_get_items(page, ids["awalan"]) or []
        if not awalan_items:
            return skip("tiada senarai awalan")
    except Exception as e:
        return skip(f"ralat awalan: {e}")

    # Mode = Nombor — static per state
    try:
        if ids.get("mode"):
            _zk_api_select_option(page, f"#{ids['mode']}", "Nombor")
    except Exception:
        pass

    # Search each awalan until the number is found available
    last_status = "Tidak Tersedia"
    last_plate = ""      # last full plate tried (awalan + nombor + akhiran)
    last_akhiran = ""    # suffix of the last plate tried
    for aw_item in awalan_items:
        if stop_event and stop_event.is_set():
            break
        awalan = aw_item["label"]
        awalan_raw = aw_item.get("label_raw", awalan)

        # ── Prefix cache: skip awalan already searched by another state ──
        if prefix_cache is not None and awalan in prefix_cache:
            cached = prefix_cache[awalan]
            if cached.get("available"):
                say(f"Check {state_name}: {awalan} {num_str}... (cached ✓)")
                return {
                    "state": state_name,
                    "awalan": awalan,
                    "akhiran": cached.get("akhiran", ""),
                    "finale": "",
                    "nombor": f"{awalan} {num_str}{(' ' + cached['akhiran']) if cached.get('akhiran') else ''}".strip(),
                    "available": True,
                    "status_text": cached.get("status_text", "Tersedia"),
                    "harga": cached.get("harga", HARGA_SEMASA),
                }
            say(f"Check {state_name}: {awalan} {num_str}... (cached ✗)")
            last_status = cached.get("status_text", "Tidak Tersedia")
            continue

        try:
            _zk_api_select_option(page, f"#{ids['awalan']}", awalan_raw,
                                  item_uuid=aw_item.get("uuid"))
        except Exception:
            continue

        # Akhiran — first suffix offered for this awalan (fresh items)
        akhiran = ""
        try:
            if ids.get("akhiran"):
                items = _zk_api_get_items(page, ids["akhiran"])
                if items:
                    akhiran = items[0]["label"]
                    _zk_api_select_option(page, f"#{ids['akhiran']}",
                                          items[0].get("label_raw", akhiran),
                                          item_uuid=items[0].get("uuid"))
        except Exception:
            pass

        # Track the full plate being tried (awalan + nombor + akhiran)
        last_plate = f"{awalan} {num_str}{(' ' + akhiran) if akhiran else ''}".strip()
        last_akhiran = akhiran or ""

        # Report the full plate being searched (UI requirement #2)
        say(f"Check {state_name}: {last_plate}...")

        try:
            _zk_dismiss_popups(page)
        except Exception:
            pass

        # Cari
        try:
            _zk_api_fill_number(page, num_str)
            _zk_dismiss_popups(page)
            page.wait_for_timeout(150)
        except Exception:
            continue

        # Parse — full plate format (awalan + nombor + akhiran)
        result = _zk_parse_result(page, awalan, num_str, akhiran)

        # ── Cache result so states sharing this prefix skip the search ──
        if prefix_cache is not None:
            prefix_cache[awalan] = {
                "available": result.get("available", False) if result else False,
                "status_text": result.get("status_text", "Tidak Tersedia") if result else "Tidak Tersedia",
                "akhiran": akhiran or "",
                "harga": result.get("harga", "") if result else "",
            }

        if not result:
            last_status = "Tidak Tersedia"
            continue
        if result.get("available"):
            return {
                "state": state_name,
                "awalan": awalan,
                "akhiran": akhiran or "",
                "finale": "",
                "nombor": f"{awalan} {num_str}{(' ' + akhiran) if akhiran else ''}".strip(),
                "available": True,
                "status_text": result["status_text"],
                "harga": result.get("harga", HARGA_SEMASA),
            }
        last_status = result.get("status_text", "Tidak Tersedia")

    # All awalan searched — number not available in this state.
    # Use the last full plate tried so the suffix letter is preserved.
    return {
        "state": state_name,
        "awalan": awalan_items[0]["label"] if awalan_items else "",
        "akhiran": last_akhiran,
        "finale": "",
        "nombor": last_plate or f"{(awalan_items[0]['label'] if awalan_items else '???')} {num_str}",
        "available": False,
        "status_text": last_status,
        "harga": "",
    }


def check_number(number, headless=True, debug=False, on_progress=None, stop_event=None,
                 on_status=None, visible=False, states=None, **_compat_kwargs):
    """Check a number on real JPJ mySIKAP using ZK framework.

    Every call opens a fresh VISIBLE browser window for login (user types
    password + CAPTCHA), minimizes the window once logged in, then scans
    all target states/series in that background window. Nothing is
    persisted between calls.

    Args:
        number: Number to check (1-9999)
        headless: IGNORED (kept for API compatibility with older callers)
        debug: Save screenshots / logs
        on_progress: Callback(result_dict) after each state result
        on_status: Callback(text) with verbose human-readable progress
        stop_event: threading.Event to signal early stop
        visible: Keep the browser window un-minimized after login
        states: Iterable of state codes to check (default: all)
    """
    results = {}
    _ensure_dirs()
    _zk_debug_enable(debug)
    num_str = str(number)

    def say(msg):
        print(f"  {msg}")
        if on_status:
            try:
                on_status(msg)
            except Exception:
                pass

    targets = list(PRODUCTION_STATES)
    if states:
        wanted = {str(s).zfill(2) for s in states}
        targets = [t for t in targets if t[0] in wanted]
        if not targets:
            say(f"Tiada negeri sepadan untuk: {states}")
            return results

    with sync_playwright() as pw:
        # Window must be VISIBLE for the manual login; the scan itself
        # runs minimized (unless visible=True).
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(30_000)

        try:
            say("Membuka JPJ mySIKAP...")
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=60_000)

            if not _is_logged_in(page):
                if not _interactive_login(page, on_status=say):
                    say("Gagal login. Henti.")
                    raise LoginFailed("Login tidak selesai dalam masa 5 minit")
            else:
                say("Sesi masih aktif — terus scan")

            # Wait for dashboard to fully load before navigating (the ZK
            # bookmark listener only exists once the app is booted)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass

            # Minimize the window: it works in the background while the
            # user stays in the GUI/terminal.
            if not visible:
                if _minimize_window(page):
                    say("Tetingkap JPJ diminimize — scan berjalan di background")
                else:
                    say("Tetingkap tak dapat diminimize — teruskan")

            # Handle baseModLanding popup if present (may appear post-login)
            try:
                ok_btn = page.locator("button.z-button-os").filter(has_text="Ok").first
                if ok_btn.is_visible(timeout=5000):
                    ok_btn.click()
                    page.wait_for_timeout(1500)
            except Exception:
                pass

            # Open the reserve-number page through the REAL menu — the
            # direct bookmark URL leaves the form half-initialized.
            say("Membuka menu Semak No. Pendaftaran Semasa...")
            RESERVE_URL = PROD_BASE + "#%2Fvel%2F04velnummgt%2Fvel04ReserveNumberAdd"
            opened = _open_reserve_page_via_menu(page)
            if not opened:
                say("Menu tak jumpa — guna pautan terus...")
                page.goto(RESERVE_URL, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(1500)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

            # Wait for the Kategori Siri combobox (the form's first row).
            # NOTE: the search table itself stays HIDDEN until a kategori
            # is selected — so wait for it AFTER selecting, not before.
            try:
                page.wait_for_selector(
                    "#seriesCategoryTableId", state="visible", timeout=20_000
                )
            except Exception:
                # Retry once via menu, then bookmark URL as last resort
                say("Borang lambat — cuba lagi...")
                if not _open_reserve_page_via_menu(page):
                    page.goto(RESERVE_URL, wait_until="domcontentloaded",
                              timeout=30_000)
                page.wait_for_timeout(1500)
                try:
                    page.wait_for_selector(
                        "#seriesCategoryTableId", state="visible", timeout=20_000
                    )
                except Exception:
                    say("Borang tidak dapat dimuatkan — semua negeri dilaporkan sebagai dilangkau")
                    for code, state_name, jpj_state in targets:
                        results[f"{code}_{state_name}"] = {
                            "state": state_name,
                            "awalan": "", "akhiran": "", "finale": "",
                            "nombor": f"??? {num_str}",
                            "available": False,
                            "status_text": "Dilangkau (borang tidak dimuatkan)",
                            "harga": "",
                        }
                        if on_progress:
                            on_progress(results[f"{code}_{state_name}"])
                    return results

            # Select Kategori Siri = "Nombor Pendaftaran Semasa" FIRST —
            # this makes the search form (negeri/awalan/akhiran) appear.
            kategori_ok = False
            for attempt in range(3):
                try:
                    _zk_api_select_option(
                        page,
                        "#seriesCategoryTableId .z-combobox-rounded-inp",
                        "Nombor Pendaftaran Semasa",
                    )
                    kategori_ok = True
                    say("Kategori dipilih: Nombor Pendaftaran Semasa")
                    break
                except Exception as e:
                    say(f"Kategori gagal (cubaan {attempt+1}/3): {e}")
                    page.wait_for_timeout(800)
            if not kategori_ok:
                say("Kategori tidak dapat dipilih — semua negeri dilaporkan sebagai dilangkau")
                for code, state_name, jpj_state in targets:
                    results[f"{code}_{state_name}"] = {
                        "state": state_name,
                        "awalan": "", "akhiran": "", "finale": "",
                        "nombor": f"??? {num_str}",
                        "available": False,
                        "status_text": "Dilangkau (kategori tidak dipilih)",
                        "harga": "",
                    }
                    if on_progress:
                        on_progress(results[f"{code}_{state_name}"])
                return results

            # NOW the search form should render — wait for it naturally
            try:
                page.wait_for_selector(
                    "#searchTableId", state="visible", timeout=20_000
                )
            except Exception:
                say("Borang carian tak muncul selepas kategori — cuba refresh kategori...")
                try:
                    _zk_api_select_option(
                        page,
                        "#seriesCategoryTableId .z-combobox-rounded-inp",
                        "Nombor Pendaftaran Semasa",
                    )
                    page.wait_for_selector(
                        "#searchTableId", state="visible", timeout=15_000
                    )
                except Exception:
                    say("Borang carian masih tak muncul — semua negeri dilaporkan sebagai dilangkau")
                    for code, state_name, jpj_state in targets:
                        results[f"{code}_{state_name}"] = {
                            "state": state_name,
                            "awalan": "", "akhiran": "", "finale": "",
                            "nombor": f"??? {num_str}",
                            "available": False,
                            "status_text": "Dilangkau (borang carian tak muncul)",
                            "harga": "",
                        }
                        if on_progress:
                            on_progress(results[f"{code}_{state_name}"])
                    return results
            say("Borang carian sedia")

            # ── State-checking loop ──
            total = len(targets)
            for idx, (code, state_name, jpj_state) in enumerate(targets, 1):
                if stop_event and stop_event.is_set():
                    say("Dihentikan oleh pengguna")
                    break
                say(f"[{idx}/{total}] Check {state_name}...")
                rd = _check_single_state(page, code, state_name, jpj_state, num_str,
                                         stop_event=stop_event, on_status=say)
                if rd == "__SESSION_LOST__":
                    say(f"Sesi tamat selepas {len(results)} negeri")
                    break
                if rd is not None:
                    icon = "✅" if rd["available"] else "❌"
                    say(f"{icon} {state_name}: {rd['nombor']} — {rd['status_text']}")
                    results[f"{code}_{state_name}"] = rd
                    if on_progress:
                        on_progress(rd)

            # Summary
            available_codes = [s for s, d in results.items() if d["available"]]
            if available_codes:
                print(f"\n  Nombor {number} TERSEDIA di:")
                for s in available_codes:
                    print(f"     {results[s]['state']} --- {results[s]['nombor']}")
            else:
                print(f"\n  Nombor {number} TIDAK tersedia di mana-mana")
            return results
        except LoginFailed:
            raise
        except Exception as e:
            print(f"  Ralat: {e}")
            import traceback
            traceback.print_exc()
            return results
        finally:
            page.close()
            ctx.close()
            browser.close()


# ---------------------------------------------------------------------------
# Session class — login once, check many numbers
# ---------------------------------------------------------------------------

class JpjSession:
    """Persistent JPJ browser session — login once, check many numbers.

    Keeps the Playwright browser open between number checks so the user
    only faces the CAPTCHA once per session, not once per number.

    Usage:
        session = JpjSession(visible=False, on_status=say)
        session.login()                         # browser opens, user logs in
        results_1 = session.check_number(888)   # scan all states
        results_2 = session.check_number(777)   # reuse same session
        session.close()
    """

    def __init__(self, visible=False, on_status=None, stop_event=None):
        self.visible = visible
        self._on_status = on_status
        self.stop_event = stop_event
        self.pw = None
        self.browser = None
        self.ctx = None
        self.page = None
        self.logged_in = False
        self.targets = list(PRODUCTION_STATES)

    def _say(self, msg):
        print(f"  {msg}")
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass

    def login(self, timeout=900):
        """Open browser, wait for manual login, open search form."""
        _ensure_dirs()
        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.ctx = self.browser.new_context(viewport={"width": 1280, "height": 900})
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(30_000)

        try:
            self._say("Membuka JPJ mySIKAP...")
            self.page.goto(LOGIN_URL, wait_until="networkidle", timeout=60_000)

            if not _is_logged_in(self.page):
                if not _interactive_login(self.page, timeout=timeout,
                                          on_status=self._say):
                    self._say("Gagal login. Henti.")
                    raise LoginFailed(
                        "Login tidak selesai dalam masa yang diberikan")
            else:
                self._say("Sesi masih aktif — terus scan")

            try:
                self.page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass

            if not self.visible:
                if _minimize_window(self.page):
                    self._say("Tetingkap JPJ diminimize — scan berjalan "
                              "di background")
                else:
                    self._say("Tetingkap tak dapat diminimize — teruskan")

            try:
                ok_btn = self.page.locator("button.z-button-os").filter(
                    has_text="Ok").first
                if ok_btn.is_visible(timeout=5000):
                    ok_btn.click()
                    self.page.wait_for_timeout(1500)
            except Exception:
                pass

            self._say("Membuka menu Semak No. Pendaftaran Semasa...")
            RESERVE_URL = (PROD_BASE
                            + "#%2Fvel%2F04velnummgt%2Fvel04ReserveNumberAdd")
            opened = _open_reserve_page_via_menu(self.page)
            if not opened:
                self._say("Menu tak jumpa — guna pautan terus...")
                self.page.goto(RESERVE_URL, wait_until="domcontentloaded",
                               timeout=30_000)
            self.page.wait_for_timeout(1500)
            try:
                self.page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

            try:
                self.page.wait_for_selector(
                    "#seriesCategoryTableId", state="visible", timeout=20_000)
            except Exception:
                self._say("Borang lambat — cuba lagi...")
                if not _open_reserve_page_via_menu(self.page):
                    self.page.goto(RESERVE_URL, wait_until="domcontentloaded",
                                   timeout=30_000)
                self.page.wait_for_timeout(1500)
                try:
                    self.page.wait_for_selector(
                        "#seriesCategoryTableId", state="visible",
                        timeout=20_000)
                except Exception:
                    raise Exception("Borang tidak dapat dimuatkan")

            kategori_ok = False
            for attempt in range(3):
                try:
                    _zk_api_select_option(
                        self.page,
                        "#seriesCategoryTableId .z-combobox-rounded-inp",
                        "Nombor Pendaftaran Semasa",
                    )
                    kategori_ok = True
                    self._say("Kategori dipilih: Nombor Pendaftaran Semasa")
                    break
                except Exception as e:
                    self._say(f"Kategori gagal (cubaan {attempt+1}/3): {e}")
                    self.page.wait_for_timeout(800)
            if not kategori_ok:
                raise Exception("Kategori tidak dapat dipilih")

            try:
                self.page.wait_for_selector(
                    "#searchTableId", state="visible", timeout=20_000)
            except Exception:
                self._say("Borang carian tak muncul — refresh kategori...")
                try:
                    _zk_api_select_option(
                        self.page,
                        "#seriesCategoryTableId .z-combobox-rounded-inp",
                        "Nombor Pendaftaran Semasa",
                    )
                    self.page.wait_for_selector(
                        "#searchTableId", state="visible", timeout=15_000)
                except Exception:
                    raise Exception("Borang carian tidak muncul")

            self._say("Borang carian sedia")
            self.logged_in = True
            return True
        except LoginFailed:
            self._cleanup()
            raise
        except Exception:
            self._cleanup()
            raise

    def is_alive(self):
        """Check if the session/browser is still responsive."""
        if not self.page:
            return False
        try:
            self.page.evaluate("1+1")
            return True
        except Exception:
            return False

    def check_number(self, number, states=None, on_progress=None,
                     on_status=None, stop_event=None):
        """Check one number using the existing session.

        Returns results dict, or '__SESSION_LOST__' if the session died."""
        if not self.logged_in or not self.is_alive():
            return "__SESSION_LOST__"

        results = {}
        num_str = str(number)

        def say(msg):
            print(f"  {msg}")
            if on_status:
                try:
                    on_status(msg)
                except Exception:
                    pass
            elif self._on_status:
                try:
                    self._on_status(msg)
                except Exception:
                    pass

        targets = list(self.targets)
        if states:
            wanted = {str(s).zfill(2) for s in states}
            targets = [t for t in targets if t[0] in wanted]
            if not targets:
                say(f"Tiada negeri sepadan untuk: {states}")
                return results

        stop = stop_event or self.stop_event

        try:
            self.page.evaluate("1+1")
        except Exception:
            return "__SESSION_LOST__"

        try:
            _zk_dismiss_popups(self.page)
        except Exception:
            pass

        # Ensure search form is ready (reset after previous number's scan)
        try:
            if not _ensure_search_form(self.page):
                if not _open_reserve_page_via_menu(self.page):
                    say("Borang carian hilang — tidak dapat dipulihkan")
                    for code, state_name, jpj_state in targets:
                        results[f"{code}_{state_name}"] = {
                            "state": state_name,
                            "awalan": "", "akhiran": "", "finale": "",
                            "nombor": f"??? {num_str}",
                            "available": False,
                            "status_text": "Dilangkau (borang hilang)",
                            "harga": "",
                        }
                        if on_progress:
                            on_progress(results[f"{code}_{state_name}"])
                    return results
                self.page.wait_for_timeout(1000)
                try:
                    self.page.wait_for_load_state("networkidle",
                                                  timeout=10_000)
                except Exception:
                    pass
                if not _ensure_search_form(self.page):
                    say("Borang carian tak dapat dipulihkan")
                    for code, state_name, jpj_state in targets:
                        results[f"{code}_{state_name}"] = {
                            "state": state_name,
                            "awalan": "", "akhiran": "", "finale": "",
                            "nombor": f"??? {num_str}",
                            "available": False,
                            "status_text": "Dilangkau (borang tak pulih)",
                            "harga": "",
                        }
                        if on_progress:
                            on_progress(results[f"{code}_{state_name}"])
                    return results

            total = len(targets)
            prefix_cache = {}  # awalan → result, shared across states to skip dupes
            for idx, (code, state_name, jpj_state) in enumerate(targets, 1):
                if stop and stop.is_set():
                    say("Dihentikan oleh pengguna")
                    break
                say(f"[{idx}/{total}] Check {state_name}...")
                rd = _check_single_state(self.page, code, state_name,
                                          jpj_state, num_str,
                                          stop_event=stop, on_status=say,
                                          prefix_cache=prefix_cache)
                if rd == "__SESSION_LOST__":
                    say(f"Sesi tamat selepas {len(results)} negeri")
                    break
                if rd is not None:
                    icon = "✅" if rd["available"] else "❌"
                    say(f"{icon} {state_name}: {rd['nombor']} — "
                        f"{rd['status_text']}")
                    results[f"{code}_{state_name}"] = rd
                    if on_progress:
                        on_progress(rd)

            available = [s for s, d in results.items() if d["available"]]
            if available:
                print(f"\n  Nombor {number} TERSEDIA di:")
                for s in available:
                    print(f"     {results[s]['state']} --- "
                          f"{results[s]['nombor']}")
            else:
                print(f"\n  Nombor {number} TIDAK tersedia di mana-mana")
            return results
        except Exception as e:
            print(f"  Ralat: {e}")
            import traceback
            traceback.print_exc()
            return results

    def _cleanup(self):
        for closer in (
            lambda: self.page.close() if self.page else None,
            lambda: self.ctx.close() if self.ctx else None,
            lambda: self.browser.close() if self.browser else None,
            lambda: self.pw.stop() if self.pw else None,
        ):
            try:
                closer()
            except Exception:
                pass
        self.logged_in = False
        self.page = None
        self.ctx = None
        self.browser = None
        self.pw = None

    def close(self):
        """Close the browser and release all resources."""
        self._cleanup()
        self._say("Sesi JPJ ditutup.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jpj_automation.py",
        description="JPJ Number Plate Checker --- check nombor spesifik merentas negeri",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Contoh:
  {sys.argv[0]} --number 888
  {sys.argv[0]} --number 1234 --states 10 14
  {sys.argv[0]} --number 777 --output result.json
  {sys.argv[0]} --number 69 --states 10 14 04 07
        """,
    )
    p.add_argument("--number", type=int,
                   help="Nombor yang nak diperiksa (1-9999)")
    p.add_argument("--states", nargs="+",
                   help="Negeri untuk diperiksa (default: semua)")
    p.add_argument("--output",
                   help="Simpan hasil ke fail JSON")
    p.add_argument("--visible", action="store_true",
                   help="Jangan minimize tetingkap browser selepas login")
    p.add_argument("--timeout", type=int, default=30,
                   help="Timeout page load (saat)")
    p.add_argument("--slow-mo", type=int, default=0,
                   help="Slow motion (ms)")
    p.add_argument("--debug", action="store_true",
                   help="Debug mode: screenshots + form state logging")
    return p


def main() -> int:
    args = build_parser().parse_args()
    _ensure_dirs()

    # --number required for check mode
    if args.number is None:
        build_parser().print_usage()
        print("jpj_automation.py: error: the following arguments are required: --number")
        return 1

    print(f"  [Production] {PROD_BASE}")
    print(f"  Nombor: {args.number}")

    try:
        results = check_number(
            args.number, debug=args.debug, states=args.states,
            visible=args.visible,
        )
    except LoginFailed as e:
        print(f"  {e}")
        results = {}

    # Summary
    available_states = [s for s, d in results.items() if d.get("available")]
    print(f"\n{'='*50}")
    if available_states:
        print(f"  Nombor {args.number} TERSEDIA di:")
        for s in available_states:
            d = results[s]
            print(f"     {d['state']} --- {d['nombor']}")
    else:
        print(f"  Nombor {args.number} TIDAK tersedia di mana-mana negeri")
    print(f"{'='*50}")

    if args.output:
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "number": args.number,
            "results": results,
            "summary": {
                "checked_states": len(results),
                "available_in": len(available_states),
                "available_states": available_states,
            }
        }
        output_path = Path(args.output)
        if not output_path.is_absolute():
            output_path = OUTPUT_DIR / output_path
        output_path.write_text(json.dumps(output_data, indent=2))
        print(f"\n  Results -> {output_path}")

    return 0 if available_states else 1


if __name__ == "__main__":
    sys.exit(main())

