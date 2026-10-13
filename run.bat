@echo off
cd /d "%~dp0"
call .venv\Scripts\activate 2>nul
echo Starting JPJ Number Checker...
echo Open http://localhost:8501 in your browser
echo Press Ctrl+C to stop
echo.
python -m streamlit run app.py --server.port 8501 --server.headless true
pause
