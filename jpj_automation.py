#!/usr/bin/env python3
"""
JPJ Vehicle Number Plate Checker — check if a specific number is available
across all states/series.

Usage:
  python3 jpj_automation.py --number 888
  python3 jpj_automation.py --number 1234 --states 10 14
  python3 jpj_automation.py --number 777 --output result.json
"""

import argparse
import json
import os
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
SESSION_DIR = BASE_DIR / "sessions"
OUTPUT_DIR = BASE_DIR / "output"
SESSION_FILE = SESSION_DIR / "jpj_session.json"

STATES = {
    "01": "JOHOR", "02": "KEDAH", "03": "KELANTAN",
    "04": "MELAKA", "05": "NEGERI SEMBILAN", "06": "PAHANG",
    "07": "PULAU PINANG", "08": "PERAK", "09": "PERLIS",
    "10": "SELANGOR", "11": "TERENGGANU", "12": "SABAH",
    "13": "SARAWAK", "14": "KUALA LUMPUR", "15": "LABUAN",
    "16": "PUTRAJAYA",
}

# JPJ Production state mappings — real JPJ combobox text per state.
# Sabah/Sarawak have district-level options instead of single state.
# LABUAN (15) doesn't exist in JPJ dropdown.
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
    ("13", "SARAWAK (MUKAH)", "MUKAH"),
    ("13", "SARAWAK (SARIKEI)", "SARIKEI"),
    ("13", "SARAWAK (SIBU)", "SIBU"),
    ("13", "SARAWAK (SRI AMAN)", "SRI AMAN"),
    ("14", "KUALA LUMPUR", "WILAYAH PERSEKUTUAN KUALA LUMPUR"),
    ("16", "PUTRAJAYA", "WILAYAH PERSEKUTUAN PUTRAJAYA"),
]


def _ensure_dirs():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _save_session(context):
    context.storage_state(path=str(SESSION_FILE))
    print(f"  Sesi disimpan ke {SESSION_FILE}")


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


def _wait_manual_login(page) -> bool:
    print("\n" + "=" * 54)
    print("              LOGIN JPJ mySIKAP DIPERLUKAN               ")
    print("=" * 54)
    print(" 1. Masukkan username & password                        ")
    print(" 2. Taip CAPTCHA yang dipaparkan                        ")
    print(" 3. Klik 'Log Masuk'                                    ")
    print(" Script akan meneruskan secara automatik selepas login. ")
    print("=" * 54 + "\n")
    try:
        import time as _time
        deadline = _time.time() + 300  # 5 minit
        while _time.time() < deadline:
            if _is_logged_in(page):
                page.wait_for_load_state("networkidle", timeout=15_000)
                print("  Login berjaya dikesan!\n")
                return True
            _time.sleep(1)
        print("  Tamat masa login (5 minit). Cuba lagi.")
        return False
    except Exception as e:
        print(f"  Ralat tunggu login: {e}")
        return False


# ── ZK Helpers (production mode) ──


def _zk_read_value(page, input_locator):
    """Read the current value of a ZK combobox input via JS."""
    if isinstance(input_locator, str):
        el = page.locator(input_locator)
    else:
        el = input_locator
    try:
        input_id = el.get_attribute("id", timeout=3000)
        if input_id:
            return page.evaluate(
                "(id) => { const e = document.getElementById(id); return e ? e.value : '' }",
                input_id
            )
        return ""
    except Exception:
        return ""


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


def _zk_select_option(page, input_locator, option_text):
    """Click a ZK combobox and select option by visible text.
    Uses Playwright trusted click events so ZK processes the selection
    and sends AU request naturally."""
    page.wait_for_timeout(200)

    if isinstance(input_locator, str):
        input_el = page.locator(input_locator)
    else:
        input_el = input_locator

    input_id = input_el.get_attribute("id", timeout=5000)
    base_id = input_id.replace("-real", "") if input_id and "-real" in input_id else input_id
    pp_id = base_id + "-pp"

    # Check if already selected
    try:
        current_val = input_el.input_value(timeout=1000)
        if current_val and current_val.replace('\xa0', ' ') == option_text:
            return
    except Exception:
        pass

    # Open the popup naturally
    _zk_open_popup(page, input_el, pp_id)

    # Try Playwright trusted click on the comboitem (no force=True — Playwright
    # verifies visibility, stability, and position so ZK gets real events)
    try:
        # Items use \xa0 (non-breaking space), so match \s (which includes \xa0 in JS)
        escaped = re.escape(option_text)
        pattern = escaped.replace(r'\ ', r'\s+')
        item_loc = page.locator(f"#{pp_id} .z-comboitem").filter(
            has_text=re.compile(pattern, re.I)
        ).first
        item_loc.click(timeout=5000)
        page.wait_for_load_state("networkidle", timeout=5000)
        page.wait_for_timeout(500)
        return
    except Exception as e:
        raise Exception(
            f"Failed to select '{option_text}' via trusted click: {e}"
        )


def _zk_get_and_select_first(page, input_locator):
    """Open a ZK combobox and select the first non-empty option.
    Uses Playwright trusted click on the first comboitem for ZK
    to process naturally. Returns selected text or None."""
    page.wait_for_timeout(200)

    if isinstance(input_locator, str):
        input_el = page.locator(input_locator)
    else:
        input_el = input_locator

    input_id = input_el.get_attribute("id", timeout=5000)
    base_id = input_id.replace("-real", "") if input_id and "-real" in input_id else input_id
    pp_id = base_id + "-pp"

    # Open popup naturally
    _zk_open_popup(page, input_el, pp_id)

    # Find first non-empty value
    first_val = page.evaluate("""(ppId) => {
        const pp = document.getElementById(ppId);
        if (!pp) return null;
        const items = pp.querySelectorAll('.z-comboitem');
        for (let item of items) {
            const raw = item.textContent.trim();
            if (raw) {
                return raw.replace(/\xa0/g, ' ');
            }
        }
        return null;
    }""", pp_id)

    if not first_val:
        return None

    # Playwright trusted click on first item
    try:
        item_loc = page.locator(f"#{pp_id} .z-comboitem").first
        item_loc.click(timeout=5000)
        page.wait_for_load_state("networkidle", timeout=5000)
        page.wait_for_timeout(500)
        return first_val
    except Exception as e:
        raise Exception(
            f"Failed to select first item '{first_val}' via trusted click: {e}"
        )


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


def _zk_has_options(page, input_locator) -> bool:
    """Check if a ZK combobox has any selectable options (items in popup)."""
    page.wait_for_timeout(200)
    if isinstance(input_locator, str):
        input_el = page.locator(input_locator)
    else:
        input_el = input_locator

    try:
        input_id = input_el.get_attribute("id", timeout=3000)
        if not input_id:
            return False
        base_id = input_id.replace("-real", "") if "-real" in input_id else input_id
        pp_id = base_id + "-pp"

        # Check if popup already has items
        count = page.evaluate(
            "(ppId) => { const pp = document.getElementById(ppId); return pp ? pp.querySelectorAll('.z-comboitem').length : -1 }",
            pp_id
        )
        if count > 0:
            return True
        if count == 0:
            # Popup exists but no items - try opening to load
            _zk_open_popup(page, input_el, pp_id)
            page.wait_for_timeout(500)
            for _ in range(15):
                count = page.evaluate(
                    "(ppId) => { const pp = document.getElementById(ppId); return pp ? pp.querySelectorAll('.z-comboitem').length : -1 }",
                    pp_id
                )
                if count > 0:
                    return True
                page.wait_for_timeout(200)
        return False
    except Exception:
        return False


def _zk_wait_for_items(page, input_locator, timeout=10):
    """Wait for a ZK combobox to have items loaded.
    Returns True if items appeared, False if timed out."""
    if isinstance(input_locator, str):
        input_el = page.locator(input_locator)
    else:
        input_el = input_locator

    try:
        input_id = input_el.get_attribute("id", timeout=3000)
        if not input_id:
            return False
        base_id = input_id.replace("-real", "") if "-real" in input_id else input_id
        pp_id = base_id + "-pp"

        for _ in range(timeout * 5):
            count = page.evaluate(
                "(ppId) => { const pp = document.getElementById(ppId); return pp ? pp.querySelectorAll('.z-comboitem').length : -1 }",
                pp_id
            )
            if count > 0:
                return True
            page.wait_for_timeout(200)
        return False
    except Exception:
        return False


def _zk_parse_result(page, awalan, nombor, akhiran=""):
    """Parse result from Senarai Nombor listbox after clicking Cari."""
    num_str = str(nombor)
    awalan = awalan.strip()
    akhiran = akhiran.strip() if akhiran else ""
    try:
        page.wait_for_timeout(300)

        # Check for error popup: "No. Tempahan Tidak Wujud"
        try:
            error_box = page.locator(".z-messagebox-window, .z-messagebox").filter(
                has_text="Tidak Wujud"
            ).first
            if error_box.is_visible(timeout=2000):
                close_btn = error_box.locator("button").filter(
                    has_text=re.compile(r"tutup|ok|close", re.I)
                ).first
                if close_btn.is_visible(timeout=1000):
                    close_btn.click()
                else:
                    page.keyboard.press("Enter")
                page.wait_for_timeout(800)
                return {"available": False, "status_text": "No. Tempahan Tidak Wujud"}
        except Exception:
            pass

        _zk_dismiss_popups(page)

        # Check for any listbox body containing the number (result data)
        # This works for both "Senarai Nombor" and "Maklumat Nombor Tempahan"
        try:
            body = page.locator(".z-listbox-body").filter(
                has_text=awalan
            ).filter(
                has_text=num_str
            ).first
            text = body.text_content(timeout=3000).strip()
        except Exception:
            return {"available": False, "status_text": "Tidak Tersedia"}

        if not text:
            return {"available": False, "status_text": "Tidak Tersedia"}

        if awalan in text and num_str in text and (not akhiran or akhiran in text):
            idx = text.find(awalan)
            harga = text[:idx].strip()
            return {
                "available": True,
                "status_text": "Tersedia",
                "harga": harga if harga else "300.00",
            }
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


def _zk_api_select_option(page, css_selector, option_label):
    """Select a combobox option by label using ZK JS API.
    css_selector can be a CSS selector string or a direct widget UUID.
    Returns the selected label on success.
    """
    page.wait_for_timeout(80)

    # Determine widget_id: if css_selector starts with # and has no spaces, treat as direct ID
    if css_selector.startswith('#') and ' ' not in css_selector and '.' not in css_selector:
        widget_id = _zk_api_strip_real(css_selector[1:])
    else:
        widget_id = _zk_api_get_widget_id(page, css_selector)
    if not widget_id:
        raise Exception(f"Cannot find widget for: {css_selector}")

    # Fire onChange with the value
    fired = _zk_api_fire(page, widget_id, 'onChange',
                         {"value": option_label, "start": 0})
    if not fired:
        raise Exception(f"Cannot fire onChange on {widget_id}")

    # Wait a moment then try to fire onSelect with item UUID
    page.wait_for_timeout(150)
    items = _zk_api_get_items(page, widget_id)
    target = None
    for item in items:
        if item["label"].replace('\xa0', ' ').strip() == option_label.strip():
            target = item
            break
    if target:
        _zk_api_fire(page, widget_id, 'onSelect',
                     {"items": [target["uuid"]], "reference": target["uuid"]})

    # Wait for AU round-trip
    page.wait_for_load_state("networkidle", timeout=8_000)
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


def _zk_debug_screenshot(page, label):
    if not _DEBUG:
        return
    debug_dir = Path("/Users/ridzuanjahari/Desktop/jpjnumbercheck/debug")
    debug_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    path = debug_dir / f"{ts}_{label}.png"
    try:
        page.screenshot(path=str(path))
    except Exception:
        pass


def _zk_debug_form_state(page):
    if not _DEBUG:
        return
    state = page.evaluate("""() => {
        const inputs = document.querySelectorAll('#searchTableId .z-combobox-inp');
        const data = [];
        inputs.forEach(inp => {
            data.push({id: inp.id, value: inp.value});
        });
        const num = document.querySelector('#searchTableId .z-intbox');
        if (num) data.push({id: num.id, value: num.value});
        const btns = document.querySelectorAll('button.z-button-os');
        const btnData = [];
        btns.forEach(btn => {
            btnData.push({text: btn.textContent.trim(), disabled: btn.disabled});
        });
        return {inputs: data, buttons: btnData};
    }""")
    print(f"    [DEBUG] Form state:")
    for inp in state.get("inputs", []):
        print(f"      {inp['id']} = {inp['value']}")
    for btn in state.get("buttons", []):
        print(f"      Button: '{btn['text']}' disabled={btn['disabled']}")


def _zk_debug_result_html(page):
    if not _DEBUG:
        return
    html = page.evaluate("""() => {
        const tabs = document.querySelectorAll('.z-tab-hm');
        const tabData = [];
        tabs.forEach(t => {
            tabData.push({text: t.textContent.trim(), visible: t.offsetParent !== null});
        });
        const bodies = document.querySelectorAll('.z-listbox-body');
        const bodyData = [];
        bodies.forEach(b => {
            bodyData.push(b.textContent.trim().substring(0, 800));
        });
        const msgs = document.querySelectorAll('.z-messagebox, .z-messagebox-window, .z-errorbox');
        const msgData = [];
        msgs.forEach(m => {
            msgData.push({text: m.textContent.trim().substring(0, 300), visible: m.offsetParent !== null});
        });
        return {tabs: tabData, listbox_bodies: bodyData, popups: msgData};
    }""")
    print(f"    [DEBUG] After Cari:")
    for t in html.get("tabs", []):
        print(f"      Tab: '{t['text']}' visible={t['visible']}")
    for i, b in enumerate(html.get("listbox_bodies", [])):
        print(f"      ListBody {i}: {b}")
    for p in html.get("popups", []):
        print(f"      Popup: '{p['text']}' visible={p['visible']}")


# ── Per-state check (extracted for reuse in parallel mode) ──


def _check_single_state(page, code, state_name, jpj_state, num_str):
    """Check availability for one state/district.
    Returns result dict or None if skipped, '__SESSION_LOST__' if disconnected.
    """
    first_awalan = None
    first_akhiran = ""

    try:
        page.evaluate("1+1")
    except Exception:
        return "__SESSION_LOST__"

    try:
        _zk_dismiss_popups(page)
    except Exception:
        pass

    # Switch to Carian tab
    try:
        carian_tab = page.locator(".z-tab-hm").filter(
            has_text="Carian No. Pendaftaran"
        ).first
        if carian_tab.is_visible(timeout=2000):
            carian_tab.click()
            page.wait_for_timeout(100)
    except Exception:
        pass

    # Kategori
    try:
        kategori_val = page.evaluate("""() => {
            const el = document.querySelector('#seriesCategoryTableId .z-combobox-rounded-inp');
            return el ? el.value : '';
        }""")
        if kategori_val and "Nombor Pendaftaran Semasa" not in kategori_val:
            _zk_api_select_option(page, "#seriesCategoryTableId .z-combobox-rounded-inp",
                                  "Nombor Pendaftaran Semasa")
    except Exception:
        pass

    # Negeri
    try:
        _zk_api_select_option(page, "#searchTableId .z-combobox-inp.z-combobox-readonly",
                              jpj_state)
    except Exception:
        return None

    # Awalan
    try:
        page.wait_for_timeout(200)
        page.wait_for_load_state("networkidle", timeout=8_000)

        awalan_info = page.evaluate("""() => {
            const inputs = document.querySelectorAll('#searchTableId .z-combobox-inp.z-combobox-readonly');
            if (inputs.length < 2) return null;
            const rawId = inputs[1].id;
            const baseId = rawId.replace('-real', '');
            const wgt = zk.Widget.$(baseId);
            if (!wgt) return {id: baseId, items: []};
            const items = [];
            let child = wgt.firstChild;
            while (child) {
                const raw = child.getLabel ? child.getLabel() : child._label || '';
                if (raw !== undefined && raw !== null) {
                    items.push({uuid: child.uuid, label: raw.trim(), label_raw: raw});
                }
                child = child.nextSibling;
            }
            return {id: baseId, items: items};
        }""")

        if not awalan_info:
            return None

        first_awalan = None
        first_awalan_raw = None
        if awalan_info["items"] and len(awalan_info["items"]) > 0:
            first_awalan = awalan_info["items"][0]["label"]
            first_awalan_raw = awalan_info["items"][0]["label_raw"]
        else:
            _zk_api_fire(page, awalan_info["id"], 'onChange', {"value": "", "start": 0})
            page.wait_for_timeout(200)
            page.wait_for_load_state("networkidle", timeout=8_000)
            items_after = _zk_api_get_items(page, awalan_info["id"])
            if items_after and len(items_after) > 0:
                first_awalan = items_after[0]["label"]
                first_awalan_raw = items_after[0]["label_raw"]

        if not first_awalan:
            return None

        select_val = first_awalan_raw or first_awalan
        _zk_api_select_option(page, f"#{awalan_info['id']}", select_val)
    except Exception:
        return None

    # Akhiran
    try:
        third_id = page.evaluate("""() => {
            const inputs = document.querySelectorAll('#searchTableId .z-combobox-inp.z-combobox-readonly');
            if (inputs.length < 3) return null;
            return inputs[2].id;
        }""")
        if third_id:
            items = _zk_api_get_items(page, third_id)
            if items and len(items) > 0:
                first_akhiran = items[0]["label"]
                akhiran_raw = items[0].get("label_raw", first_akhiran)
                _zk_api_select_option(page, f"#{third_id}", akhiran_raw)
    except Exception:
        pass

    try:
        _zk_dismiss_popups(page)
    except Exception:
        pass

    # Mode = Nombor
    try:
        mode_id = page.evaluate("""() => {
            const inputs = document.querySelectorAll('#searchTableId .z-combobox-inp.z-combobox-readonly');
            if (inputs.length < 4) return null;
            return inputs[3].id;
        }""")
        if mode_id:
            _zk_api_select_option(page, f"#{mode_id}", "Nombor")
    except Exception:
        pass

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
        return None

    # Parse
    result = _zk_parse_result(page, first_awalan, num_str, first_akhiran or "")
    if result:
        return {
            "state": state_name,
            "awalan": first_awalan,
            "akhiran": first_akhiran or "",
            "finale": "",
            "nombor": f"{first_awalan} {num_str}",
            "available": result["available"],
            "status_text": result["status_text"],
            "harga": result.get("harga", "300.00"),
        }
    return None


def check_number(number, headless=False, debug=False, on_progress=None, stop_event=None,
                 username=None, password=None):
    """Check a number on real JPJ mySIKAP using ZK framework.

    Args:
        number: Number to check (1-9999)
        headless: Run browser in background
        debug: Save screenshots / logs
        on_progress: Callback(state_dict) called after each state result
        stop_event: threading.Event to signal early stop
        username: Pre-fill login username/IC (optional)
        password: Pre-fill login password (optional)
    """
    results = {}
    _ensure_dirs()
    _zk_debug_enable(debug)
    num_str = str(number)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        session_loaded = False
        if SESSION_FILE.exists():
            try:
                ctx = browser.new_context(
                    storage_state=str(SESSION_FILE),
                    viewport={"width": 1280, "height": 900},
                )
                session_loaded = True
                print("  Sesi dimuat")
            except Exception:
                ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        else:
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.set_default_timeout(30_000)

        try:
            if session_loaded:
                page.goto(PROD_BASE, wait_until="networkidle", timeout=60_000)
            else:
                page.goto(LOGIN_URL, wait_until="networkidle", timeout=60_000)

            logged_in = False
            if session_loaded:
                try:
                    logged_in = _is_logged_in(page)
                except Exception:
                    pass

            ok = False
            if not logged_in:
                if headless:
                    print("\n  ⚠️  No valid session found.")
                    if SESSION_FILE.exists():
                        print("  Saved session expired. Re-login:")
                    else:
                        print("  No saved session. Login first:")
                    print("    python3 jpj_automation.py --login")
                    print("  Then try again.\n")
                    return results

                # Auto-fill username/password if provided
                if username or password:
                    try:
                        page.wait_for_selector("#txtusername", state="visible", timeout=10_000)
                        if username:
                            page.fill("#txtusername", username)
                            print(f"  Username diisi")
                        if password:
                            page.fill("#txtpassword", password)
                            print(f"  Password diisi")
                        print("  Sila masukkan CAPTCHA dan klik Log Masuk")
                    except Exception as e:
                        print(f"  Gagal isi login form: {e}")

                ok = _wait_manual_login(page)
                if ok:
                    _save_session(ctx)
            else:
                ok = True

            if not ok:
                print("  Gagal login. Henti.")
                return results

            # Handle baseModLanding popup if present
            try:
                ok_btn = page.locator("button.z-button-os").filter(has_text="Ok").first
                if ok_btn.is_visible(timeout=3000):
                    ok_btn.click()
                    page.wait_for_timeout(1500)
                    print("  Popup ditutup")
            except Exception:
                pass

            # Navigate to reserve number form via hash routing
            print("  Buka halaman Tempahan No. Pendaftaran...")
            page.evaluate("""() => {
                window.location.hash = '/vel/04velnummgt/vel04ReserveNumberAdd';
            }""")
            page.wait_for_timeout(1500)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass

            # Wait for form tables with retry
            for attempt in range(3):
                try:
                    page.wait_for_selector(
                        "#seriesCategoryTableId", state="visible", timeout=15_000
                    )
                    break
                except Exception:
                    if attempt < 2:
                        print(f"  Cubaan {attempt+2}/3 muat borang...")
                        page.evaluate("""() => {
                            window.location.hash = '/vel/04velnummgt/vel04ReserveNumberAdd';
                        }""")
                        page.wait_for_timeout(1500)
                        try:
                            page.wait_for_load_state("networkidle", timeout=10_000)
                        except Exception:
                            pass
                    else:
                        print("  Gagal muat borang. Cuba navigasi penuh...")
                        page.goto(
                            "https://public.jpj.gov.my/public/#%2Fvel%2F04velnummgt%2Fvel04ReserveNumberAdd",
                            wait_until="domcontentloaded", timeout=30_000,
                        )
                        page.wait_for_timeout(3000)
                        page.wait_for_selector(
                            "#seriesCategoryTableId", state="visible", timeout=15_000
                        )
            # Carian No. Pendaftaran tab might need activation
            try:
                carian_tab = page.locator(
                    ".z-tab-hm"
                ).filter(
                    has_text="Carian No. Pendaftaran"
                ).first
                if carian_tab.is_visible(timeout=3000):
                    carian_tab.click()
                    page.wait_for_timeout(300)
            except Exception:
                pass

            # Wait for search form table
            try:
                page.wait_for_selector(
                    "#searchTableId", state="visible", timeout=15_000
                )
            except Exception:
                print("  Papar borang carian...")
                page.evaluate("""() => {
                    var tbl = document.getElementById('searchTableId');
                    if (tbl) {
                        tbl.style.display = 'block';
                        tbl.style.visibility = 'visible';
                        var p = tbl.parentElement;
                        while (p && p !== document.body) {
                            p.style.display = 'block';
                            p.style.visibility = 'visible';
                            p = p.parentElement;
                        }
                    }
                }""")
                page.wait_for_timeout(1000)
            print(f"  Form siap")

            # Select Kategori Siri via ZK API
            try:
                _zk_api_select_option(
                    page,
                    "#seriesCategoryTableId .z-combobox-rounded-inp",
                    "Nombor Pendaftaran Semasa",
                )
                print(f"  Kategori: Nombor Pendaftaran Semasa")
            except Exception as e:
                print(f"  Kategori: {e}")

            # ── State-checking loop ──
            for code, state_name, jpj_state in PRODUCTION_STATES:
                    if stop_event and stop_event.is_set():
                        print(f"  ⏹️  Dihentikan oleh pengguna")
                        break
                    print(f"\n  --- {state_name} ({code}) ---")
                    rd = _check_single_state(page, code, state_name, jpj_state, num_str)
                    if rd == "__SESSION_LOST__":
                        print(f"    Sesi tamat selepas {len(results)} negeri")
                        break
                    if rd is not None:
                        icon = "✅" if rd["available"] else "❌"
                        print(f"    {icon} {rd['nombor']} --- {rd['status_text']}")
                        results[f"{code}_{state_name}"] = rd
                        if on_progress:
                            on_progress(rd)
                    # brief pause between states
                    if stop_event and stop_event.is_set():
                        break
                    page.wait_for_timeout(100)

            # Summary
            available_codes = [s for s, d in results.items() if d["available"]]
            if available_codes:
                print(f"\n  Nombor {number} TERSEDIA di:")
                for s in available_codes:
                    print(f"     {results[s]['state']} --- {results[s]['nombor']}")
            else:
                print(f"\n  Nombor {number} TIDAK tersedia di mana-mana")
            return results
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
    p.add_argument("--headless", action="store_true",
                   help="Headless mode (no browser window)")
    p.add_argument("--no-save-session", action="store_true",
                   help="Jangan simpan sesi")
    p.add_argument("--timeout", type=int, default=30,
                   help="Timeout page load (saat)")
    p.add_argument("--slow-mo", type=int, default=0,
                   help="Slow motion (ms)")
    p.add_argument("--debug", action="store_true",
                   help="Debug mode: screenshots + form state logging")
    p.add_argument("--login", action="store_true",
                   help="Login mode: open browser for manual login then save session and exit")
    return p


def main() -> int:
    args = build_parser().parse_args()
    _ensure_dirs()

    # Login-only mode — doesn't need --number
    if args.login:
        print("  Login mode: membuka browser untuk login manual...")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            page = ctx.new_page()
            page.goto(PROD_BASE, wait_until="networkidle", timeout=60_000)
            if not _is_logged_in(page):
                ok = _wait_manual_login(page)
                if ok:
                    _save_session(ctx)
                    print("  Sesi disimpan. Kini anda boleh guna headless mode.")
                else:
                    print("  Login gagal.")
            else:
                print("  Sudah login.")
                _save_session(ctx)
            page.close()
            ctx.close()
            browser.close()
        return 0

    # --number required for check mode
    if args.number is None:
        build_parser().print_usage()
        print("jpj_automation.py: error: the following arguments are required: --number")
        return 1

    print(f"  [Production] {PROD_BASE}")
    print(f"  Nombor: {args.number}")

    results = check_number(args.number, headless=args.headless, debug=args.debug)

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

