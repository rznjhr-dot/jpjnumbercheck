#!/usr/bin/env python3
"""
JPJ Number Checker — GUI tool.

Satu input, satu button. Type nombor, klik Cari.
Dia akan scan semua negeri dan return result kat mana nombor tu available.
"""

import json
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
except ImportError:
    print("❌ Tkinter tak available. Cuba: brew install python-tk")
    sys.exit(1)

from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
STAGING_URL = "http://127.0.0.1:8080/public/"
PROD_URL = "https://public.jpj.gov.my/public/"

BASE_DIR = Path(__file__).parent
SESSION_DIR = BASE_DIR / "sessions"
SESSION_FILE = SESSION_DIR / "jpj_session.json"

STATES = {
    "01": "JOHOR", "02": "KEDAH", "03": "KELANTAN",
    "04": "MELAKA", "05": "NEGERI SEMBILAN", "06": "PAHANG",
    "07": "PULAU PINANG", "08": "PERAK", "09": "PERLIS",
    "10": "SELANGOR", "11": "TERENGGANU", "12": "SABAH",
    "13": "SARAWAK", "14": "KUALA LUMPUR", "15": "LABUAN",
    "16": "PUTRAJAYA",
}

# ---------------------------------------------------------------------------
# Automation Engine
# ---------------------------------------------------------------------------
class JPJEngine:
    def __init__(self, staging: bool = True, headless: bool = True):
        self.staging = staging
        self.headless = headless
        self.base_url = STAGING_URL if staging else PROD_URL
        self.dashboard_url = self.base_url + "dashboard"
        self.login_url = self.base_url
        self._log_callback = None
        self._result_callback = None
        self._done_callback = None
        self._running = False

    def on_log(self, cb):
        self._log_callback = cb

    def on_result(self, cb):
        self._result_callback = cb

    def on_done(self, cb):
        self._done_callback = cb

    def log(self, msg):
        if self._log_callback:
            self._log_callback(msg)

    def _auto_login_staging(self, page, ctx) -> bool:
        """Auto login for staging server."""
        try:
            page.goto(self.login_url, wait_until="networkidle", timeout=30_000)
            page.wait_for_selector("#captchaId img", timeout=10_000)

            captcha_code = ""
            def handle_resp(response):
                nonlocal captcha_code
                if "/public/captcha" in response.url and not captcha_code:
                    body = response.text()
                    texts = re.findall(r'<text[^>]*>([^<]+)</text>', body)
                    if texts:
                        captcha_code = "".join(texts).upper()

            page.on("response", handle_resp)
            page.goto(self.login_url, wait_until="networkidle", timeout=30_000)
            page.wait_for_timeout(1000)

            if not captcha_code:
                captcha_src = page.locator("#captchaId img").get_attribute("src")
                if captcha_src:
                    full_url = f"{self.base_url.rstrip('/public/')}{captcha_src}"
                    resp = ctx.request.get(full_url)
                    texts = re.findall(r'<text[^>]*>([^<]+)</text>', resp.text())
                    if texts:
                        captcha_code = "".join(texts).upper()

            if not captcha_code or len(captcha_code) < 4:
                self.log("✗ Gagal parse CAPTCHA")
                return False

            self.log(f"CAPTCHA: {captcha_code}")
            page.fill("#txtusername", "800101011234")
            page.fill("#txtpassword", "password123")
            page.fill("#inputCaptchaId", captcha_code)
            page.click("#loginBtn")
            page.wait_for_url("**/dashboard*", timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=15_000)
            page.wait_for_timeout(1000)
            self.log("✓ Login OK")
            return True
        except Exception as e:
            self.log(f"✗ Login gagal: {e}")
            return False

    def _wait_manual_login(self, page) -> bool:
        self.log("⌛ Login manual diperlukan (CAPTCHA)")
        self.log("   Isi form dekat browser yang terbuka...")
        self.log("   Lepas login, tunggu page siap...")
        try:
            import time as _time
            deadline = _time.time() + 300
            while _time.time() < deadline and self._running:
                try:
                    if page.locator("#kategoriSelect").is_visible(timeout=1_000):
                        page.wait_for_load_state("networkidle", timeout=15_000)
                        self.log("✓ Login OK")
                        return True
                except Exception:
                    pass
                try:
                    if page.locator("#txtusername").is_hidden(timeout=1_000) and \
                       page.locator("#loginBtn").is_hidden(timeout=1_000):
                        page.wait_for_load_state("networkidle", timeout=15_000)
                        self.log("✓ Login OK (form gone)")
                        return True
                except Exception:
                    pass
                _time.sleep(1)
            self.log("✗ Tamat masa login (5 minit)")
            return False
        except Exception as e:
            self.log(f"✗ Ralat tunggu login: {e}")
            return False

    def check_number(self, number: int, states=None):
        """Main entry point — check a number across states."""
        self._running = True
        state_codes = states or sorted(STATES.keys())
        results = {}

        SESSION_DIR.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=self.headless,
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
                    self.log("✓ Sesi dimuat")
                except Exception:
                    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
            else:
                ctx = browser.new_context(viewport={"width": 1280, "height": 900})

            page = ctx.new_page()
            page.set_default_timeout(30_000)

            try:
                # Login
                if session_loaded and self.staging:
                    page.goto(self.dashboard_url, wait_until="networkidle", timeout=60_000)
                else:
                    page.goto(self.login_url, wait_until="networkidle", timeout=60_000)

                logged_in = False
                try:
                    logged_in = page.locator("#kategoriSelect").is_visible(timeout=3_000)
                except Exception:
                    pass

                if not logged_in:
                    if self.staging:
                        ok = self._auto_login_staging(page, ctx)
                    else:
                        ok = self._wait_manual_login(page)
                    if ok:
                        ctx.storage_state(path=str(SESSION_FILE))
                        self.log("✓ Sesi disimpan")

                if not logged_in and not ok:
                    self.log("✗ Gagal login. Henti.")
                    return

                # Go to dashboard if not there (staging only)
                if self.staging and "dashboard" not in page.url:
                    page.goto(self.dashboard_url, wait_until="networkidle", timeout=60_000)

                # Select kategori
                page.wait_for_selector("#kategoriSelect", state="visible", timeout=10_000)
                page.select_option("#kategoriSelect", "current")
                page.wait_for_timeout(500)
                self.log("✓ Kategori dipilih")

                num_str = str(number)

                for code in state_codes:
                    if not self._running:
                        break

                    state_name = STATES.get(code, code)
                    self.log(f"\n── {state_name} ({code}) ──")

                    # Select state
                    page.wait_for_selector("#stateSelect", state="visible", timeout=10_000)
                    page.select_option("#stateSelect", code)
                    page.wait_for_timeout(1500)

                    # Check if Siri Awalan loaded
                    sa = page.locator("#siriAwalanSelect")
                    try:
                        sa.wait_for(state="visible", timeout=5_000)
                        page.wait_for_timeout(2000)
                    except Exception:
                        self.log(f"  ⚠ Siri Awalan tak muncul")
                        continue

                    options = sa.locator("option").all()
                    if len(options) <= 1:
                        self.log(f"  ⚠ Tiada pilihan Siri Awalan")
                        continue

                    first_awalan = options[1].get_attribute("value") or ""
                    if not first_awalan:
                        continue
                    sa.select_option(first_awalan)
                    page.wait_for_timeout(1500)

                    # Select Series Finale
                    sf = page.locator("#seriesFinaleSelect")
                    try:
                        sf.wait_for(state="visible", timeout=5_000)
                        page.wait_for_timeout(2000)
                        finale_options = sf.locator("option").all()
                        if len(finale_options) > 1:
                            first_finale = finale_options[1].get_attribute("value") or ""
                            if first_finale:
                                sf.select_option(first_finale)
                                page.wait_for_timeout(500)
                        else:
                            first_finale = first_awalan
                    except Exception:
                        first_finale = first_awalan

                    # Switch to Nombor Spesifik
                    try:
                        page.locator("input[value='spesifik']").click()
                        page.wait_for_timeout(300)
                        page.fill("#nomborSpesifik", num_str)
                        page.wait_for_timeout(200)
                    except Exception as e:
                        self.log(f"  ⚠ Gagal set nombor: {e}")
                        continue

                    # Click Cari
                    try:
                        page.locator("#cariBtn").wait_for(state="visible", timeout=5_000)
                        page.wait_for_function(
                            "!document.getElementById('cariBtn').disabled", timeout=5_000
                        )
                        page.locator("#cariBtn").click()
                        page.wait_for_timeout(2000)
                        page.wait_for_selector(
                            "#resultsCard:not(.hidden)", timeout=10_000
                        )
                        page.wait_for_timeout(1000)
                    except Exception as e:
                        self.log(f"  ⚠ Gagal cari: {e}")
                        continue

                    # Parse result
                    result = page.evaluate("""() => {
                        const rows = document.querySelectorAll('#resultsContent table tbody tr');
                        if (rows.length === 0) return null;
                        const cells = rows[0].querySelectorAll('td');
                        if (cells.length < 2) return null;
                        const nombor = cells[0].textContent.trim();
                        const statusEl = cells[1].querySelector('.status');
                        const statusText = statusEl ? statusEl.textContent.trim() : '';
                        return {
                            nombor: nombor,
                            status_text: statusText,
                            available: statusText === 'Tersedia'
                        };
                    }""")

                    if result:
                        icon = "✅" if result["available"] else "❌"
                        status_text = "Tersedia" if result["available"] else "Telah Ditempah"
                        self.log(f"  {icon} {result['nombor']} — {status_text}")
                        results[code] = {
                            "state": state_name,
                            "awalan": first_awalan,
                            "finale": first_finale,
                            "nombor": result["nombor"],
                            "available": result["available"],
                            "status_text": status_text,
                        }
                        if self._result_callback:
                            self._result_callback(code, results[code])
                    else:
                        self.log(f"  ⚠ Tiada keputusan")

                # Done
                self.log(f"\n{'='*45}")
                available = [s for s, d in results.items() if d["available"]]
                if available:
                    self.log(f"✅ Nombor {number} TERSEDIA di:")
                    for s in available:
                        self.log(f"   {results[s]['state']} — {results[s]['nombor']}")
                else:
                    self.log(f"❌ Nombor {number} TIDAK tersedia di mana-mana")
                self.log(f"{'='*45}")

            except Exception as e:
                self.log(f"✗ Ralat: {e}")
                import traceback
                traceback.print_exc()
            finally:
                self._running = False
                page.close()
                ctx.close()
                browser.close()
                if self._done_callback:
                    self._done_callback(results)

    def stop(self):
        self._running = False


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class JPJCheckerGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JPJ Number Checker")
        self.root.geometry("700x600")
        self.root.minsize(500, 400)

        self.engine = JPJEngine(staging=True, headless=True)
        self.engine.on_log(self._on_log)
        self.engine.on_result(self._on_result)
        self.engine.on_done(self._on_done)

        self._build_ui()

    def _build_ui(self):
        # ── Top: Mode + Input ──
        top = ttk.Frame(self.root, padding="12 12 12 4")
        top.pack(fill="x")

        # Mode toggle
        mode_frame = ttk.Frame(top)
        mode_frame.pack(fill="x", pady=(0, 8))
        self.mode_var = tk.StringVar(value="staging")
        ttk.Radiobutton(mode_frame, text="Staging (localhost)", variable=self.mode_var,
                        value="staging", command=self._toggle_mode).pack(side="left", padx=(0, 12))
        ttk.Radiobutton(mode_frame, text="Production (JPJ sebenar)", variable=self.mode_var,
                        value="production", command=self._toggle_mode).pack(side="left")

        # Input row
        input_frame = ttk.Frame(top)
        input_frame.pack(fill="x")

        ttk.Label(input_frame, text="Nombor:", font=("", 12)).pack(side="left", padx=(0, 8))
        self.number_var = tk.StringVar()
        self.input_entry = ttk.Entry(input_frame, textvariable=self.number_var, width=15,
                                     font=("", 14))
        self.input_entry.pack(side="left", padx=(0, 8))
        self.input_entry.bind("<Return>", lambda e: self._search())

        self.search_btn = ttk.Button(input_frame, text="Cari", command=self._search)
        self.search_btn.pack(side="left")

        self.stop_btn = ttk.Button(input_frame, text="⏹ Stop", command=self._stop,
                                   state="disabled")
        self.stop_btn.pack(side="left", padx=(8, 0))

        # Status label
        self.status_var = tk.StringVar(value="Sedia")
        status_bar = ttk.Frame(self.root, padding="12 2 12 4")
        status_bar.pack(fill="x")
        ttk.Label(status_bar, textvariable=self.status_var,
                  font=("", 9)).pack(side="left")

        # ── Results table ──
        table_frame = ttk.Frame(self.root, padding="12 0 12 4")
        table_frame.pack(fill="both", expand=True)

        columns = ("state", "awalan", "finale", "nombor", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                 height=8)
        self.tree.heading("state", text="Negeri")
        self.tree.heading("awalan", text="Siri Awalan")
        self.tree.heading("finale", text="Series Finale")
        self.tree.heading("nombor", text="Nombor")
        self.tree.heading("status", text="Status")

        self.tree.column("state", width=140, minwidth=100)
        self.tree.column("awalan", width=80, minwidth=60)
        self.tree.column("finale", width=80, minwidth=60)
        self.tree.column("nombor", width=120, minwidth=80)
        self.tree.column("status", width=120, minwidth=80)

        scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll_y.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll_y.pack(side="right", fill="y")

        # ── Log area ──
        log_frame = ttk.Frame(self.root, padding="12 0 12 8")
        log_frame.pack(fill="both", expand=True)

        ttk.Label(log_frame, text="Log:", font=("", 9)).pack(anchor="w")
        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, font=("Courier", 9),
                                                  bg="#1e1e1e", fg="#d4d4d4",
                                                  insertbackground="white", state="disabled")
        self.log_area.pack(fill="both", expand=True)

    def _toggle_mode(self):
        is_staging = self.mode_var.get() == "staging"
        self.engine.staging = is_staging
        self.engine.base_url = STAGING_URL if is_staging else PROD_URL
        self.engine.dashboard_url = self.engine.base_url + "dashboard"
        self.engine.login_url = self.engine.base_url
        mode_name = "Staging" if is_staging else "Production"
        self._log(f"Mode: {mode_name}")

    def _search(self):
        num_str = self.number_var.get().strip()
        if not num_str or not num_str.isdigit():
            self._log("✗ Masukkan nombor yang sah (1-9999)")
            return
        number = int(num_str)
        if number < 1 or number > 9999:
            self._log("✗ Nombor mesti antara 1-9999")
            return

        # Clear previous results
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.search_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.input_entry.configure(state="disabled")
        self.status_var.set(f"Mencari nombor {number}...")

        self._log(f"\n🔍 Mencari nombor {number} di semua negeri...\n")

        thread = threading.Thread(
            target=self.engine.check_number,
            args=(number,),
            daemon=True,
        )
        thread.start()

    def _stop(self):
        self.engine.stop()
        self._log("\n⏹ Dihentikan oleh pengguna")
        self._enable_input()

    def _enable_input(self):
        self.search_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.input_entry.configure(state="normal")
        self.status_var.set("Sedia")

    def _on_log(self, msg):
        self.root.after(0, self._log, msg)

    def _log(self, msg):
        self.log_area.configure(state="normal")
        self.log_area.insert("end", msg + "\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def _on_result(self, state_code, data):
        def _update():
            icon = "✅" if data["available"] else "❌"
            status = f"{icon} {data['status_text']}"
            self.tree.insert("", "end", values=(
                data["state"],
                data["awalan"],
                data["finale"],
                data["nombor"],
                status,
            ))
        self.root.after(0, _update)

    def _on_done(self, results):
        self.root.after(0, self._enable_input)
        available = [d for d in results.values() if d["available"]]
        if available:
            self.status_var.set(f"✅ Tersedia di {len(available)} negeri")
        else:
            self.status_var.set("❌ Tidak tersedia")

    def run(self):
        self._log("╔══════════════════════════════════════════════╗")
        self._log("║        JPJ Number Checker v2                ║")
        self._log("╠══════════════════════════════════════════════╣")
        self._log("║ 1. Masukkan nombor (1-9999)                 ║")
        self._log("║ 2. Klik Cari                                ║")
        self._log("║ 3. Tunggu results                           ║")
        self._log("╚══════════════════════════════════════════════╝")
        self._log("")
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = JPJCheckerGUI()
    app.run()
