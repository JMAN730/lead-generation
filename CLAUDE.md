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

# CLI — Google Maps + Yelp (requires YELP_API_KEY)
YELP_API_KEY=your_key python scraper.py "Toledo, Ohio" --sources google,yelp --limit 20

# CLI — multiple locations from file
python scraper.py --file cities_ohio.txt --limit 20 --concurrency 2

# CLI flags
#   --limit N           max results per category (default: 20)
#   --concurrency N     categories processed in parallel (default: 1)
#   --output-dir DIR    directory for CSV and <output-file>.progress.json (default: .)
#   --output-file NAME  custom CSV filename (default: leads_YYYYMMDD_HHMMSS.csv)
#   --categories-file F custom category list, one category per line
#   --exclude-chains-file F custom chain exclusion list, one chain per line
#   --sources LIST      comma-separated lead sources: google,yelp (default: google)
#   --dry-run           validate leads without writing CSV or progress files
#   --call-sheet        also write <output-file-stem>_call_sheet.csv
#   --preset F          load run settings from a JSON preset
#   --save-preset F     save resolved run settings to a JSON preset and exit
```

## Testing & validation

Run the unit tests after any code change before handing work back:

```bash
python -m unittest
```

Use `python3 -m unittest` where `python` is unavailable. There is no linter configured in this project.

- Tests live in `tests/test_scraper.py` and use `unittest.IsolatedAsyncioTestCase` for the async cases. The package marker is `tests/__init__.py`.
- Network and browser work is never hit live. Tests monkeypatch module-level functions (`scraper.scrape_gmaps`, `scraper.check_website`, `scraper.scrape_source`) and use `httpx.MockTransport` for HTTP/Yelp paths. Follow this pattern when adding tests — do not make real network calls.
- Most behavioral tests drive `process_category()` against a `tempfile.TemporaryDirectory()` and assert on the written CSV, call sheet, progress file, and summary counters.
- CI (`.github/workflows/test.yml`) runs on every push and pull request with Python 3.12: it installs `requirements.txt`, installs the Playwright Chromium browser, runs `python -m pip check`, `python -m unittest`, then `python -m compileall scraper.py gui.py tests`. Keep all four green.

## Related docs

- `README.md` — user-facing setup, usage, and output column reference.
- `AGENTS.md` — parallel guidance for other coding agents; keep its architecture notes roughly in sync with this file when behavior changes.

## Architecture

The project has two entry points that share one async core:

- **`scraper.py`** — all scraping logic plus a `__main__` CLI entry point
- **`gui.py`** — Tkinter front-end that imports and calls `run_scraper()` from `scraper.py`

### Scraping pipeline (scraper.py)

`run_scraper()` → `process_category()` → `scrape_source()` → source adapter + `check_website()`

1. **`scrape_gmaps()`** opens a Playwright page, navigates to `google.com/maps/search/…`, scrolls the feed, and collects `(name, url, rating, reviews)` tuples — rating/reviews are read from feed `aria-label` attributes here (fast path). Chain names are filtered via a precompiled regex (`_CHAIN_RE`) against `EXCLUDED_CHAINS`.

2. **`scrape_yelp_api()`** uses the official Yelp API when `yelp` is selected in `--sources`. It requires `YELP_API_KEY`, normalizes Yelp results into the shared lead shape, and attempts lightweight Google Maps enrichment for website/email details.

3. **`get_business_details()`** opens a fresh page per business (up to 5 concurrent via `asyncio.Semaphore`) and extracts phone, email, website, and rating/reviews from the Maps detail panel. Rating extraction has three fallback strategies: inline text regex → alternate line pattern → `aria-label` attribute on the star element.

4. **`check_website()`** normalizes website URLs, rejects Google/social/non-web URLs, and makes an HTTP GET with `httpx` (up to 10 concurrent). It returns structured validation details (`is_valid`, normalized/final URL, HTTP status, and reason). Status codes below 400 (and the blocked-but-real set `401/403/405/429` in `VALID_BLOCKED_STATUSES`) count as valid. Facebook/social-only URLs are captured as profile context and scored as no standalone website. **Leads are saved only when `is_valid` is `False`** — the tool targets businesses without a working standalone website.

5. **`score_lead()`** assigns each lead a `Priority Score` (0–100, clamped), a `Call Priority` bucket (High ≥70, Medium ≥45, else Low), and a human-readable `Priority Reason`. Inputs are the website reason, review count, rating, and phone/email presence — strongest signal is a missing/social-only website plus review history.

6. Results are appended to CSV via `pandas`, including normalized phone/domain fields, source fields, website validation reason/status columns, and call-priority score/reason columns. Column order is fixed in `process_category()`; the call sheet uses `CALL_SHEET_COLUMNS`. Exported text fields are sanitized against spreadsheet formula injection (leading `= + - @` etc.) before writing. Deduplication (`get_lead_dedupe_keys()`) uses normalized phone, source IDs/URLs, Google Maps URL, domain, and name+phone keys loaded once at startup. A shared `asyncio.Lock` protects CSV appends, call-sheet writes, progress writes, and dedupe state when category concurrency is enabled.

7. Progress is atomically persisted next to the CSV as `<output-file-stem>.progress.json` after each source/category completes. New progress entries use `[source, location, category]`; old Google-only `[location, category]` entries are still treated as completed Google work. Per-category work is wrapped in a 180 s `asyncio.wait_for`; a timeout or a retryable `SourceScrapeError` (e.g. Yelp HTTP/network failure) is logged and **does not** mark the category complete, so it retries on the next run. Dry runs skip CSV and progress writes. Completed runs save `<output-file-stem>_summary.json`; `--call-sheet` also writes `<output-file-stem>_call_sheet.csv`.

`run_scraper()` strips path components from `--output-file` (via `os.path.basename`) and forces a `.csv` extension to block path traversal. Output filenames default to `leads_YYYYMMDD_HHMMSS.csv`.

### GUI threading model (gui.py)

The GUI runs Tkinter on the main thread. Scraping runs in a `daemon=True` `threading.Thread` that creates its own `asyncio` event loop (`asyncio.new_event_loop()`). Stop/restart is coordinated via two boolean flags on `ScraperGUI`:

- `stop_requested` — polled by `stop_check` lambda passed into `run_scraper()`; checked between categories and between individual businesses
- `_restart_after_stop` — when `True`, `on_scraping_finished()` automatically calls `start_scraping()` again after the thread exits

`sys.stdout` and `sys.stderr` are replaced with a `StreamToQueue` instance that schedules `text.insert()` calls back onto the Tk main thread via `widget.after(0, …)`.

### Key constants (scraper.py)

- `CATEGORIES` — default list of business types to search; the GUI exposes these as an editable listbox
- `EXCLUDED_CHAINS` — business names to filter out; extend this list when well-known chains appear in results (as noted in README)
- Semaphore limits: 5 concurrent detail-page fetches, 10 concurrent website checks, 180 s timeout per category
