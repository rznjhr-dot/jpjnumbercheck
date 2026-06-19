# JPJ Number Checker

Semak nombor pendaftaran kenderaan JPJ mySIKAP — available ke tak dekat semua 32 negeri.

---

## 📦 Setup Awal (first time)

### 1. Install dependencies

```bash
cd ~/Desktop/jpjnumbercheck

# Install Python packages
pip3 install streamlit playwright

# Install Playwright browsers (Chromium)
playwright install chromium
```

> Jika `playwright` command not found: `python3 -m playwright install chromium`

### 2. Start app

```bash
python3 -m streamlit run app.py
```

Buka `http://localhost:8501` dekat browser.

---

## 🎯 Cara Guna

### First run (perlu login JPJ)

1. Taip nombor (contoh `888`) → klik **Cari**
2. Browser Chromium akan terbuka automatik — **gambar dekat bawah ni tunjuk**:
   - Login guna IC + password mySIKAP
   - Isi CAPTCHA
   - Klik **Log Masuk**
3. Lepas login, scan akan jalan automatik — jangan tutup browser tu
4. Result stream masuk dekat Streamlit UI

### Run seterusnya (tak perlu login lagi)

- Session cookies disimpan dekat `sessions/jpj_session.json`
- Next search akan guna balik — terus scan tanpa login

### Kalau nak login semula

```bash
rm sessions/jpj_session.json
```

Atau klik **Clear Cache** dekat sidebar.

---

## 🖥️ Tampilan

| Screen | Layout |
|---|---|
| Desktop (>820px) | Title + badge sepaket, form sebelah |
| Tablet (480–820px) | Stack menegak, font lebih kecil |
| Phone (<480px) | Single column, card meta menegak |

---

## 🚀 Deployment Options

### Option A: Lokal (✅ sekarang)

```bash
python3 -m streamlit run app.py
```

| Pro | Con |
|---|---|
| Dah jalan, confirm work | Hanya guna sendiri |
| Login manual senang | Kena ada display |

### Option B: VPS + Browserless (kalau nak web service)

Guna [browserless.io](https://www.browserless.io/) Docker untuk remote Chromium:

```
User → Browser → Streamlit di VPS:8501
                    ↕ websocket
              browserless container (Chromium remote)
                    ↕ HTTP
              public.jpj.gov.my
```

**Setup**:
```bash
docker run -p 3000:3000 browserless/chrome
# then in Python: connect_over_cdp("ws://vps:3000")
```

| Pro | Con |
|---|---|
| Boleh deploy ke VPS | Setup lebih kompleks |
| Ramai user boleh guna | Login still manual (perlu relay) |

### Option C: API Direct (⭐ best — belum siap)

Reverse-engineer JPJ endpoint — buang browser terus:

1. `python3 capture_jpj_api.py`
2. Login JPJ dekat browser yang terbuka
3. Klik **Cari** — dia akan capture POST request ke `public.jpj.gov.my/public/zkau`
4. Decrypt parameter ZK → boleh call direct guna `requests`

| Pro | Con |
|---|---|
| Boleh deploy ke Streamlit Cloud | Kena reverse-engineer dulu |
| Paling cepat (no browser) | JPJ mungkin ubah API |
| Senang maintain | |

---

## 🛠️ Commands Berguna

```bash
# Start app
python3 -m streamlit run app.py

# Start dengan port lain
python3 -m streamlit run app.py --server.port 8502

# Kill app
pkill -f "streamlit run app.py"

# Syntax check
python3 -c "import ast; ast.parse(open('app.py').read()); print('OK')"

# Git
git status
git add app.py
git commit -m "pesan"
git push
```

---

## 📁 Struktur

```
jpjnumbercheck/
├── app.py                  # Streamlit UI (main)
├── jpj_automation.py       # Playwright automation (JPJ)
├── requirements.txt        # Python deps
├── sessions/               # Saved login sessions (gitignored)
│   └── jpj_session.json
└── output/                 # Result JSON (gitignored)
```

---

## ⚠️ Troubleshooting

| Masalah | Solution |
|---|---|
| `streamlit: command not found` | Guna `python3 -m streamlit` |
| Browser tak terbuka | `playwright install chromium` |
| Session expired | `rm sessions/jpj_session.json` then login balik |
| `AttributeError: stop_event` | Refresh Streamlit page |
| Port 8501 dah guna | `--server.port 8502` |
