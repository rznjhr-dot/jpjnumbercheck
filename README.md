# JPJ Number Checker

Check vehicle registration number availability across all Malaysian states
on JPJ mySIKAP — batch mode, one login, hacker terminal UI.

Enter 2-3 numbers, log in once (manual CAPTCHA), and the tool scans all
30 states and districts automatically. Results displayed as plate cards
with copy-ready summaries.

## Features

- **Batch mode** — check multiple numbers in a single login session
- **30 states & districts** — all peninsular states, Sabah, Sarawak, KL
  (Putrajaya and Labuan excluded — plates not transferable)
- **Prefix cache** — states sharing the same number series (e.g. Sibu &
  Mukah share QS) are only searched once, saving time
- **Hacker terminal UI** — phosphor green on black, matrix rain
  background, live verbose log with auto-scroll, typing effect
- **Color-coded results** — yellow (searching), green (found), gray
  (not available), red (errors)
- **Copy summaries** — formatted plate availability summary for each
  number, ready to paste to customers

## Prerequisites

- **Python 3.9 or newer** ([python.org](https://python.org))
- **Internet connection**
- **A valid JPJ mySIKAP account** (you log in yourself — the tool does
  not provide credentials)

## Installation

### macOS / Linux

```bash
git clone https://github.com/rznjhr-dot/jpjnumberplatecheck.git
cd jpjnumberplatecheck
python3 install.py
```

### Windows

```cmd
git clone https://github.com/jpjnumberplatecheck/jpjnumberplatecheck.git
cd jpjnumberplatecheck
python install.py
```

The installer creates a virtual environment (`.venv/`), installs
Streamlit and Playwright, and downloads the Chromium browser (~150MB).

## Usage

### Start the app

**macOS / Linux:**
```bash
./run.sh
```

**Windows:**
```cmd
run.bat
```

Then open `http://localhost:8501` in your browser.

### Scan numbers

1. Enter numbers in the text area (one per line, or comma-separated)
   - Example: `888`, `777`, `1234`
2. Click **EXECUTE SCAN**
3. A browser window opens — log in to JPJ mySIKAP with your password
   and CAPTCHA (this happens once per session)
4. The browser minimizes — scanning runs in the background
5. Watch the terminal log for live progress
6. When done, results appear as plate cards with availability status
   and price

### macOS .app bundle (optional)

For a double-clickable macOS app:

```bash
./build_streamlit_app.sh
```

This creates `JPJ Checker.app` in the project directory.

## How It Works

1. **Login**: A Chromium browser (via Playwright) opens the JPJ mySIKAP
   portal. You log in manually — the tool does **not** bypass, solve, or
   automate CAPTCHA.

2. **Batch scanning**: After login, the browser session stays open.
   Each number is checked across all 30 states. The tool selects each
   state, picks the available prefix (awalan), enters the number, and
   reads the result.

3. **Prefix caching**: When multiple states share the same number
   series prefix, only the first state searches it. Subsequent states
   reuse the cached result (shown as "cached" in the terminal log).

4. **Results**: Available plates are shown as cards with the full plate
   number, state, and price. A text summary is generated for
   copy-pasting.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `streamlit: command not found` | Use `python -m streamlit run app.py` |
| Browser doesn't open | Run `python -m playwright install chromium` |
| Port 8501 already in use | Edit `run.sh`/`run.bat`: change `--server.port 8501` to another port |
| JPJ login page doesn't load | Check internet connection; JPJ may restrict non-Malaysian IPs |
| Scan stops mid-way | The JPJ session may have expired. Restart the app and scan again |

## Project Structure

```
jpjnumberplatecheck/
├── app.py                  # Streamlit GUI (main entry point)
├── jpj_automation.py       # Browser automation engine + JpjSession
├── install.py              # Cross-platform installer
├── run.sh                  # macOS/Linux launcher
├── run.bat                 # Windows launcher
├── build_streamlit_app.sh  # macOS .app bundle builder (optional)
├── requirements.txt        # Python dependencies
├── CHANGELOG.md            # Version history
├── LICENSE                 # MIT license
└── .env.example            # Environment variable template (empty)
```

## Disclaimer

THIS TOOL IS NOT AFFILIATED WITH, ENDORSED BY, OR CONNECTED TO
Jabatan Pengangkutan Jalan (JPJ) OR THE MALAYSIAN GOVERNMENT.

- **Your own account**: You need your own valid JPJ mySIKAP account.
  The tool does not provide credentials.
- **CAPTCHA is manual**: The tool does NOT bypass, solve, or automate
  CAPTCHA. You type it yourself every session.
- **Personal use**: This tool is intended for personal, non-commercial
  use only.
- **No warranty**: This software is provided "as is" without warranty.
  It may stop working if JPJ changes their website.
- **Terms of service**: Users are responsible for complying with JPJ's
  terms of service regarding automated access.
- **Privacy**: The tool runs entirely locally. No data is sent to any
  server except JPJ's own website during your manual login and scan.
  No telemetry, no analytics, no tracking.
- **Malaysian access**: JPJ mySIKAP may restrict access to Malaysian IP
  addresses. Users outside Malaysia may need a VPN.

## License

[MIT](LICENSE)
