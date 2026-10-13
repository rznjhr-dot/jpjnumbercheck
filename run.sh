#!/bin/bash
# JPJ Number Checker — launcher (macOS/Linux)
cd "$(cd "$(dirname "$0")" && pwd)"
source .venv/bin/activate 2>/dev/null || true
echo "Starting JPJ Number Checker..."
echo "Open http://localhost:8501 in your browser"
echo "Press Ctrl+C to stop"
echo ""
python -m streamlit run app.py --server.port 8501 --server.headless true
