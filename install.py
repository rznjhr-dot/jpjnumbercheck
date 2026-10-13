#!/usr/bin/env python3
"""
JPJ Number Checker — Cross-platform installer.
Works on macOS, Windows, and Linux.

Usage: python install.py
"""
import os
import subprocess
import sys

MIN_PYTHON = (3, 9)
REQUIREMENTS = ["streamlit>=1.37.0", "playwright>=1.40.0"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    if sys.version_info < MIN_PYTHON:
        print("ERROR: Python {}.{}+ required, you have {}.{}".format(
            MIN_PYTHON[0], MIN_PYTHON[1],
            sys.version_info[0], sys.version_info[1]))
        sys.exit(1)

    print("Python {}.{}.{} detected".format(
        sys.version_info[0], sys.version_info[1], sys.version_info[2]))

    venv_dir = os.path.join(SCRIPT_DIR, ".venv")
    if not os.path.exists(venv_dir):
        print("Creating virtual environment (.venv/)...")
        subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
    else:
        print("Virtual environment already exists (.venv/)")

    if os.name == "nt":
        pip = os.path.join(venv_dir, "Scripts", "pip")
        python = os.path.join(venv_dir, "Scripts", "python")
    else:
        pip = os.path.join(venv_dir, "bin", "pip")
        python = os.path.join(venv_dir, "bin", "python")

    print("Installing dependencies (streamlit, playwright)...")
    subprocess.check_call([pip, "install"] + REQUIREMENTS)

    print("Installing Chromium browser for Playwright (~150MB)...")
    subprocess.check_call([python, "-m", "playwright", "install", "chromium"])

    if sys.platform.startswith("linux"):
        print("Installing Linux system dependencies for Chromium...")
        try:
            subprocess.check_call(
                [python, "-m", "playwright", "install-deps", "chromium"])
        except subprocess.CalledProcessError:
            print("WARNING: Could not install system deps automatically.")
            print("  Run: sudo {} -m playwright install-deps chromium".format(
                python))

    print("\nVerifying installation...")
    try:
        subprocess.check_call(
            [python, "-c", "import streamlit; import playwright; print('OK')"])
    except subprocess.CalledProcessError:
        print("ERROR: Verification failed. Check errors above.")
        sys.exit(1)

    print("\n" + "=" * 50)
    print("  Installation complete!")
    print("=" * 50)
    if os.name == "nt":
        print("\n  To start the app:")
        print("    run.bat")
    else:
        print("\n  To start the app:")
        print("    ./run.sh")
    print("\n  Or manually:")
    print("    {} -m streamlit run app.py".format(python))
    print("\n  Then open: http://localhost:8501")


if __name__ == "__main__":
    main()
