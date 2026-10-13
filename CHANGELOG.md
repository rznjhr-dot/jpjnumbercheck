# Changelog

## v2.0 (2026-10-13)

### Added
- Batch mode: enter multiple numbers, all scanned in one login session
  (JpjSession class keeps the browser open between checks)
- Hacker terminal UI: phosphor green on black, monospace, matrix rain
  background, scanline overlay, live verbose log with auto-scroll
- Matrix typing effect at bottom of terminal during scans
- Prefix cache: states sharing the same awalan (e.g. SIBU & MUKAH share
  QS series) skip the duplicate search and reuse the cached result
- Cross-platform installer (install.py) for macOS, Windows, and Linux
- Platform launchers: run.sh (macOS/Linux), run.bat (Windows)
- Color-coded terminal log: yellow (searching), bright green (found),
  gray (not available), red (errors), cyan (targets)
- Kill server button with auto-close tab countdown

### Changed
- 30 states scanned (Putrajaya and Labuan excluded — plates not
  transferable to other states)
- Plate results: white background with black text
- Dynamic state count in header
- Simplified input: multi-number text area, no fast mode toggle

### Removed
- Fast mode (experimental HTTP-based scanning via ZK AU protocol)
- Reverse engineering guide and traffic capture tools
- Old launchers (CekNombor.command, JPJ Checker.command)
- Session badge pill from UI
