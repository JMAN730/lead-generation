# GEMINI.md - Project Context

## Project Overview
This is a **Google Maps Business Scraper and Lead Generation** tool. It is designed to autonomously search for businesses on Google Maps based on a user-defined query, extract their names and website URLs, and then validate the status of those websites (checking for 200 OK responses).

### Main Technologies
- **Language:** Python 3.12+
- **Browser Automation:** [Playwright](https://playwright.dev/python/) (for handling dynamic content and infinite scrolling on Google Maps).
- **HTTP Client:** [httpx](https://www.python-httpx.org/) (used asynchronously for fast website validation).
- **Data Handling:** [pandas](https://pandas.pydata.org/) (for saving results to CSV).

## Building and Running
The project uses a Python virtual environment to manage dependencies.

### Installation
1.  **Setup Virtual Environment:**
    ```bash
    python3 -m venv venv
    ```
2.  **Install Dependencies:**
    ```bash
    ./venv/bin/pip install -r requirements.txt
    ```
3.  **Install Browser Binaries:**
    ```bash
    ./venv/bin/playwright install chromium
    ```

### Execution
Run the scraper using the following command:
```bash
./venv/bin/python scraper.py "Your Search Query" --limit 50
```
-   `query`: The search term (e.g., "Cafes in Paris").
-   `--limit`: (Optional) The maximum number of results to retrieve (default: 50).

### Scraping & Filtering Logic
-   **Chain Filtering:** The script includes a list of popular chains (`EXCLUDED_CHAINS`) to filter out major corporations.
-   **Lead Filtering:** After scraping, the tool validates all found websites. It then **removes** any business that has a working, active website (Status 200). 
-   **Target Leads:** The final `leads.csv` only contains businesses that either have **no website listed** on Google Maps or have a website that is **broken/inactive**. This makes it a specialized tool for web development lead generation.

### Output
-   **File:** `leads.csv`
-   **Columns:** `Name`, `Maps URL`, `Website`, `Status` (Active, No Website, Status Code, or Error), `Final URL`.

### Known Constraints
-   Google Maps may occasionally present cookie consent dialogs, which the script attempts to handle automatically.
-   Website validation uses custom headers to avoid basic anti-bot blocks (403/401 errors).
