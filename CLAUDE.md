# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
python -m venv venv
# Linux/macOS
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Windows
venv\Scripts\activate
venv\Scripts\pip install -r requirements.txt
venv\Scripts\playwright install chromium
```

## Running the Tool

```bash
# GUI
python gui.py

# CLI — single location
python scraper.py "Toledo, Ohio" --limit 20

# CLI — multiple locations from file
python scraper.py --file cities_ohio.txt --limit 20 --concurrency 2

# CLI flags
#   --limit N           max results per category (default: 20)
#   --concurrency N     categories processed in parallel (default: 1)
#   --output-dir DIR    directory for CSV and <output-file>.progress.json (default: .)
#   --output-file NAME  custom CSV filename (default: leads_YYYYMMDD_HHMMSS.csv)
#   --categories-file F custom category list, one category per line
#   --exclude-chains-file F custom chain exclusion list, one chain per line
#   --dry-run           validate leads without writing CSV or progress files
#   --call-sheet        also write <output-file-stem>_call_sheet.csv
#   --preset F          load run settings from a JSON preset
#   --save-preset F     save resolved run settings to a JSON preset and exit
```

Run the lightweight unit tests with:

```bash
python -m unittest
```

There is no linter configured in this project.

## Architecture

The project has two entry points that share one async core:

- **`scraper.py`** — all scraping logic plus a `__main__` CLI entry point
- **`gui.py`** — Tkinter front-end that imports and calls `run_scraper()` from `scraper.py`

### Scraping pipeline (scraper.py)

`run_scraper()` → `process_category()` → `scrape_gmaps()` + `get_business_details()` + `check_website()`

1. **`scrape_gmaps()`** opens a Playwright page, navigates to `google.com/maps/search/…`, scrolls the feed, and collects `(name, url, rating, reviews)` tuples — rating/reviews are read from feed `aria-label` attributes here (fast path). Chain names are filtered via a precompiled regex (`_CHAIN_RE`) against `EXCLUDED_CHAINS`.

2. **`get_business_details()`** opens a fresh page per business (up to 5 concurrent via `asyncio.Semaphore`) and extracts phone, email, website, and rating/reviews from the Maps detail panel. Rating extraction has three fallback strategies: inline text regex → alternate line pattern → `aria-label` attribute on the star element.

3. **`check_website()`** normalizes website URLs, rejects Google/social/non-web URLs, and makes an HTTP GET with `httpx` (up to 10 concurrent). It returns structured validation details (`is_valid`, normalized/final URL, HTTP status, and reason). Successful redirects and common access-control/rate-limit responses count as evidence that a site exists. **Leads are saved only when `is_valid` is `False`** — the tool targets businesses without a working website.

4. Results are appended to CSV via `pandas`, including normalized phone/domain fields, website validation reason/status columns, and call-priority score/reason columns. Exported text fields are sanitized against spreadsheet formula injection before writing. Deduplication uses normalized phone, Google Maps URL, domain, and name+phone keys loaded once at startup. A shared `asyncio.Lock` protects CSV appends, call-sheet writes, progress writes, and dedupe state when category concurrency is enabled.

5. Progress is atomically persisted next to the CSV as `<output-file-stem>.progress.json` (list of `[location, category]` pairs) after each category completes. This keeps resumable state scoped to the selected output file. Dry runs skip CSV and progress writes. Completed runs save `<output-file-stem>_summary.json`; `--call-sheet` also writes `<output-file-stem>_call_sheet.csv`.

### GUI threading model (gui.py)

The GUI runs Tkinter on the main thread. Scraping runs in a `daemon=True` `threading.Thread` that creates its own `asyncio` event loop (`asyncio.new_event_loop()`). Stop/restart is coordinated via two boolean flags on `ScraperGUI`:

- `stop_requested` — polled by `stop_check` lambda passed into `run_scraper()`; checked between categories and between individual businesses
- `_restart_after_stop` — when `True`, `on_scraping_finished()` automatically calls `start_scraping()` again after the thread exits

`sys.stdout` and `sys.stderr` are replaced with a `StreamToQueue` instance that schedules `text.insert()` calls back onto the Tk main thread via `widget.after(0, …)`.

### Key constants (scraper.py)

- `CATEGORIES` — default list of business types to search; the GUI exposes these as an editable listbox
- `EXCLUDED_CHAINS` — business names to filter out; extend this list when well-known chains appear in results (as noted in README)
- Semaphore limits: 5 concurrent detail-page fetches, 10 concurrent website checks, 180 s timeout per category
