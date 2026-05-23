# Multi-Source Business Scraper & Lead Generator

An autonomous tool designed to find businesses and identify potential leads based on website status. It specifically targets businesses with **no website**, **social-only presence**, or **broken websites**, making it ideal for web development lead generation.

## Features
- **Dual Interface:** Use the command-line (CLI) or the built-in Graphical User Interface (GUI).
- **Smart Filtering:** Automatically excludes major chains (McDonald's, Starbucks, etc.). You'll probably have to add more to this list in filter.txt
- **Lead Validation:** Checks whether a business has a reachable, non-social website before saving leads that need digital help.
- **Data Capture:** Extracts Name, Phone, Email (if available), and Website.
- **CSV Safety:** Escapes spreadsheet formula prefixes in exported text fields.
- **Configurable Searches:** Load categories and excluded chains from text files without editing Python code.
- **Multi-Source Capture:** Search Google Maps by default and optionally add Yelp via the official Yelp API, including paginated Yelp batches above 50 results.
- **Social Profile Detection:** Facebook-only/social URLs are captured as profile context and treated as no standalone website.
- **Call Priority Scoring:** Adds call priority, score, and reason columns so the best leads are easier to call first.
- **Call Sheet Export:** Optionally writes a cleaner call-ready CSV alongside the raw export.
- **Run Summary:** Saves a JSON summary with counts by category, location, and website issue.
- **Deduplication:** Prevents duplicate entries, including during concurrent category runs, and tracks progress per output file.
- **Parallel Processing:** Supports concurrent category scraping for faster results.
- **Dry Run:** Preview scraping and validation results without writing CSV or progress files.

## Setup
1. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```
2. ## Start the virtual environment 
  - Linux/mac: source venv/bin/activate
  - Windows: venv\Scripts\activate

3. **Install dependencies:**
   - Windows: `.\venv\Scripts\pip install -r requirements.txt`
   - Linux/macOS: `./venv/bin/pip install -r requirements.txt`
4. **Install Playwright browser:**
   - Windows: `.\venv\Scripts\playwright install chromium`
   - Linux/macOS: `./venv/bin/playwright install chromium`

## Usage

### Graphical Interface 
Run the following command to launch the user-friendly interface:
```bash
python gui.py
```

### Command Line Interface 
Run the scraper for a specific location:
```bash
python scraper.py "Toledo, Ohio" --limit 20
```

Add Yelp results with the official Yelp API:
```bash
YELP_API_KEY=your_key python scraper.py "Toledo, Ohio" --sources google,yelp --limit 20
```

####  Usage:
- `location`: The city or area to search.
- `--limit`: Max results per category (default: 20).
- `--file`: Path to a `.txt` file with locations (one per line).
- `--concurrency`: Number of categories to process in parallel (default: 1).
- `--output-dir`: Directory to save the `leads.csv` (default: current directory).
- `--output-file`: Custom CSV filename (default: timestamped filename).
- `--categories-file`: Optional `.txt` file with categories to search, one per line.
- `--exclude-chains-file`: Optional `.txt` file with chain names to filter out, one per line.
- `--sources`: Comma-separated sources to search: `google`, `yelp` (default: `google`).
- `--dry-run`: Run searches and website validation without writing CSV or progress files.
- `--call-sheet`: Also create a call-ready CSV.
- `--preset`: Load run settings from a JSON preset.
- `--save-preset`: Save the resolved settings to a JSON preset and exit.

## Tests
Run the lightweight unit tests with:
```bash
python -m unittest
```

If `python` is not available on Linux, use:
```bash
python3 -m unittest
```

If dependencies are missing, install them in the project virtual environment first. On Debian/Ubuntu systems where `python3 -m venv venv` fails because `ensurepip` is unavailable, install `python3.12-venv`, or use the user-site fallback:
```bash
pip3 install --user --break-system-packages -r requirements.txt
python3 -m unittest
```

## Output
The results are saved in `leads.csv` with the following columns:
- **Name**: Business name.
- **Phone**: Contact number.
- **Normalized Phone**: Digits-only phone number for dedupe/imports.
- **Email**: Publicly listed email (extracted from the Maps panel).
- **Website**: Link found on Google Maps.
- **Website Domain**: Normalized website domain when available.
- **Website Checked URL**: Normalized/final URL used during website validation.
- **Website Status**: HTTP status code when one was received.
- **Website Reason**: Why the website was treated as missing or broken.
- **Call Priority**: High/Medium/Low cold-call priority.
- **Priority Score**: Numeric call-readiness score.
- **Priority Reason**: Human-readable reason for the score.
- **Rating**: Rating when found.
- **Reviews**: Review count when found.
- **Source**: Discovery source such as `google` or `yelp`.
- **Source URL**: Primary listing URL for the source.
- **Source ID**: Source-specific ID when available.
- **Google Maps URL**: Google Maps listing URL when found.
- **Yelp URL**: Yelp listing URL when found.
- **Facebook URL**: Captured Facebook page/profile URL when a business lists social presence.
- **Category**: Business category (e.g., Landscaping).
- **Location**: The area searched.

When enabled, the call sheet is saved as `<output-file-stem>_call_sheet.csv`. Run summaries are saved as `<output-file-stem>_summary.json`.

## Yelp and Facebook Notes
- Yelp support requires `YELP_API_KEY`.
- Yelp API searches request up to 50 businesses per page and continue with `offset` until the requested `--limit` is reached or Yelp has no more results.
- Yelp HTTP/network failures are treated as retryable source failures and do not mark the category complete in the progress file.
- Facebook is not scraped automatically. If a business lists a Facebook page instead of a standalone site, the URL is captured and scored as no standalone website.

## License
MIT
