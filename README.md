# Google Maps Business Scraper & Lead Generator

An autonomous tool designed to scrape Google Maps for businesses and identify potential leads based on website status. It specifically targets businesses with **no website** or **broken websites**, making it ideal for web development lead generation.

## Features
- **Dual Interface:** Use the command-line (CLI) or the built-in Graphical User Interface (GUI).
- **Smart Filtering:** Automatically excludes major chains (McDonald's, Starbucks, etc.).
- **Lead Validation:** Checks if a business's website is active. Only saves leads that need digital help.
- **Data Capture:** Extracts Name, Phone, Email (if available), and Website.
- **Deduplication:** Prevents duplicate entries and tracks progress across multiple runs.
- **Parallel Processing:** Supports concurrent category scraping for faster results.

## Setup
1. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```
2. **Install dependencies:**
   - Windows: `.\venv\Scripts\pip install -r requirements.txt`
   - Linux/macOS: `./venv/bin/pip install -r requirements.txt`
3. **Install Playwright browser:**
   - Windows: `.\venv\Scripts\playwright install chromium`
   - Linux/macOS: `./venv/bin/playwright install chromium`

## Usage

### Graphical Interface (GUI)
Run the following command to launch the user-friendly interface:
```bash
python gui.py
```

### Command Line Interface (CLI)
Run the scraper for a specific location:
```bash
python scraper.py "Toledo, Ohio" --limit 20
```

#### CLI Arguments:
- `location`: The city or area to search.
- `--limit`: Max results per category (default: 20).
- `--file`: Path to a `.txt` file with locations (one per line).
- `--concurrency`: Number of categories to process in parallel (default: 1).
- `--output-dir`: Directory to save the `leads.csv` (default: current directory).

## Output
The results are saved in `leads.csv` with the following columns:
- **Name**: Business name.
- **Phone**: Contact number.
- **Email**: Publicly listed email (extracted from the Maps panel).
- **Website**: Link found on Google Maps.
- **Category**: Business category (e.g., Landscaping).
- **Location**: The area searched.

## License
MIT
