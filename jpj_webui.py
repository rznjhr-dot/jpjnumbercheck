#!/usr/bin/env python3
"""
JPJ Number Checker — Web UI. Production-only (real JPJ mySIKAP).

Satu input, satu button. Type nombor, klik Cari.
Dia akan scan semua negeri dan return result kat mana nombor tu available.

Usage:
  python3 jpj_webui.py                # prompt for number
  python3 jpj_webui.py 888            # check number 888
  python3 jpj_webui.py 888 --headless # headless mode
"""

import sys
from jpj_automation import check_number


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0

    headless = "--headless" in sys.argv

    if len(sys.argv) > 1:
        try:
            number = int(sys.argv[1])
        except ValueError:
            print("✗ Masukkan nombor yang sah (1-9999)")
            return 1
    else:
        while True:
            raw = input("Nombor (1-9999): ").strip()
            if raw.isdigit():
                number = int(raw)
                break
            print("✗ Masukkan nombor yang sah")

    if number < 1 or number > 9999:
        print("✗ Nombor mesti antara 1-9999")
        return 1

    print(f"\n🔍 Mencari nombor {number} di semua negeri...\n")
    results = check_number(number, headless=headless)

    available = [s for s, d in results.items() if d.get("available")]
    if available:
        print(f"\n✅ Nombor {number} TERSEDIA di {len(available)} negeri!")
        for s in available:
            d = results[s]
            print(f"   {d['state']} — {d['nombor']}")
    else:
        print(f"\n❌ Nombor {number} TIDAK tersedia di mana-mana negeri")

    return 0 if available else 1


if __name__ == "__main__":
    sys.exit(main())
