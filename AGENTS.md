# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

# CLI - single location
python scraper.py "Toledo, Ohio" --limit 20

# CLI - Google Maps + Yelp (requires YELP_API_KEY)
YELP_API_KEY=your_key python scraper.py "Toledo, Ohio" --sources google,yelp --limit 20

# CLI - multiple locations from file
python scraper.py --file cities_ohio.txt --limit 20 --concurrency 2

# CLI flags
#   --limit N           max results per category (default: 20)
#   --concurrency N     categories processed in parallel (default: 1)
#   --output-dir DIR    directory for CSV and progress.json (default: .)
#   --output-file NAME  custom CSV filename (default: leads_YYYYMMDD_HHMMSS.csv)
#   --sources LIST      comma-separated lead sources: google,yelp (default: google)
```

## Validation

After making code changes, run the unit tests automatically before handing work back:

```bash
python -m unittest
```

If `python` is not available, use `python3 -m unittest`. If dependencies are missing and the project venv does not exist, create it with `python3 -m venv venv`, install `pip install -r requirements.txt`, then run tests through the venv. On Debian/Ubuntu hosts where `python3 -m venv` fails because `ensurepip` is missing, install `python3.12-venv` first or use the existing user-site fallback:

```bash
pip3 install --user --break-system-packages -r requirements.txt
python3 -m unittest
```

Run the unit tests with:

```bash
python -m unittest
```

Use the project virtual environment on Windows when dependencies are not installed globally:

```bash
.\venv\Scripts\python.exe -m unittest
```

No separate linter is currently configured.

## Architecture

The project has two entry points that share one async core:

- **`scraper.py`** - all scraping logic plus a `__main__` CLI entry point
- **`gui.py`** - Tkinter front-end that imports and calls `run_scraper()` from `scraper.py`

### Scraping Pipeline

`run_scraper()` -> `process_category()` -> `scrape_source()` -> source adapter + `check_website()`

1. **`scrape_gmaps()`** opens a Playwright page, navigates to `google.com/maps/search/...`, scrolls the feed, and collects business tuples. Rating and review counts are read from feed `aria-label` attributes as the fast path. Chain names are filtered via a precompiled regex (`_CHAIN_RE`) against `EXCLUDED_CHAINS`.

2. **`scrape_yelp_api()`** uses the official Yelp API when the `yelp` source is selected. It requires `YELP_API_KEY`, normalizes Yelp businesses into the shared lead shape, and then attempts lightweight Google Maps enrichment for website/email details.

3. **`get_business_details()`** opens a fresh page per business and extracts phone, email, website, rating, and reviews from the Maps detail panel. Rating extraction has fallback strategies for inline text, alternate line patterns, and star element `aria-label` attributes.

4. **`check_website()`** makes an HTTP GET with `httpx`. It treats real reachable sites as valid and filters social/profile URLs. Facebook/social-only URLs are captured as profile context and scored as no standalone website. Leads are saved only when a business has no working standalone website, because the tool targets businesses that need digital help.

5. Results are appended to CSV via `pandas`. Deduplication uses an in-memory set loaded at startup and guarded during concurrent category writes.

6. Progress is persisted beside each output CSV as `<output-name>.progress.json`, enabling resumable runs per output file. New entries are scoped by `(source, location, category)`; old Google-only progress entries remain compatible.

### GUI Threading Model

The GUI runs Tkinter on the main thread. Scraping runs in a daemon `threading.Thread` that creates its own `asyncio` event loop. Stop/restart is coordinated via two boolean flags on `ScraperGUI`:

- `stop_requested` - polled by the `stop_check` lambda passed into `run_scraper()`
- `_restart_after_stop` - when true, `on_scraping_finished()` automatically calls `start_scraping()` after the thread exits

`sys.stdout` and `sys.stderr` are replaced with a `StreamToQueue` instance that schedules `text.insert()` calls back onto the Tk main thread via `widget.after(0, ...)`.

### Key Constants

- `CATEGORIES` - default business types to search; the GUI exposes these as an editable listbox
- `EXCLUDED_CHAINS` - business names to filter out; extend this list when well-known chains appear in results
- Semaphore limits - detail page fetches and website checks are bounded in `scraper.py`
