#!/bin/bash
# Build "JPJ Checker.app" — double-click to run the Streamlit GUI.
# Resolves python3 at build time; deps must already be installed.
set -e
cd "$(cd "$(dirname "$0")" && pwd)"

APP="JPJ Checker.app"
APP_DIR="$APP/Contents"
PY="$(command -v python3)"
PROJ_DIR="$(pwd)"

if ! "$PY" -c "import streamlit" 2>/dev/null; then
    echo "ERROR: streamlit not installed for $PY"
    echo "Run: $PY -m pip install -r requirements.txt"
    exit 1
fi

rm -rf "$APP"
mkdir -p "$APP_DIR/MacOS" "$APP_DIR/Resources"

cat > "$APP_DIR/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleName</key><string>JPJ Number Checker</string>
	<key>CFBundleExecutable</key><string>launcher</string>
	<key>CFBundleIdentifier</key><string>com.jpjnumberplatecheck.app</string>
	<key>CFBundleVersion</key><string>2.0</string>
	<key>CFBundlePackageType</key><string>APPL</string>
	<key>LSMinimumSystemVersion</key><string>10.13</string>
	<key>NSHighResolutionCapable</key><true/>
	<key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
	<!-- TCC: we read the project folder (may live in ~/Desktop) -->
	<key>NSDesktopFolderUsageDescription</key>
	<string>JPJ Checker perlu akses kepada fail projek untuk memulakan GUI.</string>
	<key>NSDocumentsFolderUsageDescription</key>
	<string>JPJ Checker perlu akses kepada fail projek untuk memulakan GUI.</string>
</dict>
</plist>
PLIST

cat > "$APP_DIR/MacOS/launcher" <<EOF
#!/bin/bash
# JPJ Checker: start Streamlit (once) and open the browser.
PY="$PY"
APP_PY="$PROJ_DIR/app.py"
URL="http://localhost:8501"
LOG="\$HOME/.jpj_checker.log"

# Already running? Just open the browser.
if curl -sf -o /dev/null "\$URL/_stcore/health"; then
    open "\$URL"
    exit 0
fi

# Start server headless in the background (survives this launcher).
# Absolute script path — the Finder-launched cwd is not readable.
nohup "\$PY" -m streamlit run "\$APP_PY" \\
    --server.port 8501 --server.headless true \\
    --server.fileWatcherType none \\
    > "\$LOG" 2>&1 &

# Wait for readiness (max 30s), then open the browser.
for i in \$(seq 1 60); do
    if curl -sf -o /dev/null "\$URL/_stcore/health"; then
        open "\$URL"
        exit 0
    fi
    sleep 0.5
done

# Diagnose and show a friendly dialog instead of failing silently.
if grep -q "Operation not permitted" "\$LOG" 2>/dev/null; then
    osascript -e 'display dialog "macOS sekat akses kepada folder Desktop.\n\nPENYELESAIAN (sekali sahaja):\n1. Klik \"Buka Settings\" di bawah\n2. Privacy & Security → Full Disk Access\n3. Klik + dan tambah JPJ Checker.app\n4. Buka JPJ Checker semula" with title "JPJ Checker — Perlu Kebenaran" buttons {"Buka Settings", "Tutup"} default button 1 with icon caution' -e 'tell application "System Settings" to open location "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"'
    exit 1
fi

echo "Gagal memulakan server. Log terakhir:"
tail -20 "\$LOG"
exit 1
EOF

chmod +x "$APP_DIR/MacOS/launcher"

# Ad-hoc signature — required for the TCC usage descriptions to be honored
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true

echo "Siap: $APP"
echo "Cara guna: open \"$APP\" atau double-click di Finder."
echo "Log: ~/.jpj_checker.log | Hentikan server: pkill -f 'streamlit run app.py'"
