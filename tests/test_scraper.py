import asyncio
import contextlib
import io
import os
import tempfile
import unittest

import httpx
import pandas as pd

import scraper


class ScraperCoreTests(unittest.IsolatedAsyncioTestCase):
    def test_normalize_website_url(self):
        self.assertEqual(scraper.normalize_website_url("example.com"), "https://example.com")
        self.assertEqual(scraper.normalize_website_url("https://example.com/a"), "https://example.com/a")
        self.assertIsNone(scraper.normalize_website_url("/maps/place/foo"))
        self.assertIsNone(scraper.normalize_website_url("mailto:test@example.com"))

    def test_progress_is_scoped_to_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            scraper.save_progress(tmp, "leads_a.csv", {("Toledo", "Roofers")})
            scraper.save_progress(tmp, "leads_b.csv", {("Akron", "Concrete")})

            self.assertEqual(scraper.load_progress(tmp, "leads_a.csv"), {("Toledo", "Roofers")})
            self.assertEqual(scraper.load_progress(tmp, "leads_b.csv"), {("Akron", "Concrete")})
            self.assertTrue(os.path.exists(os.path.join(tmp, "leads_a.progress.json")))
            self.assertTrue(os.path.exists(os.path.join(tmp, "leads_b.progress.json")))

    async def test_check_website_treats_blocked_real_sites_as_valid(self):
        async def handler(request):
            return httpx.Response(403)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            self.assertTrue(await scraper.check_website(client, "example.com", asyncio.Semaphore(1)))
            self.assertFalse(await scraper.check_website(client, "https://facebook.com/foo", asyncio.Semaphore(1)))

    async def test_concurrent_categories_do_not_duplicate_csv_rows(self):
        async def fake_scrape(browser_context, search_query, limit, stop_check=None):
            return [{
                "Name": "Same Lead",
                "Phone": "555-111-2222",
                "Email": None,
                "Website": None,
                "Rating": None,
                "Reviews": None,
                "Google Maps URL": "https://maps.example/place",
            }]

        async def fake_check(client, url, semaphore):
            return False

        original_scrape = scraper.scrape_gmaps
        original_check = scraper.check_website
        scraper.scrape_gmaps = fake_scrape
        scraper.check_website = fake_check
        try:
            with tempfile.TemporaryDirectory() as tmp:
                existing_leads = set()
                progress_set = set()
                state_lock = asyncio.Lock()

                with contextlib.redirect_stdout(io.StringIO()):
                    await asyncio.gather(
                        scraper.process_category(None, None, "Toledo", "Roofers", 1, tmp, existing_leads, progress_set, "leads.csv", state_lock),
                        scraper.process_category(None, None, "Toledo", "Concrete", 1, tmp, existing_leads, progress_set, "leads.csv", state_lock),
                    )

                df = pd.read_csv(os.path.join(tmp, "leads.csv"))
                self.assertEqual(len(df), 1)
                self.assertEqual(progress_set, {("Toledo", "Roofers"), ("Toledo", "Concrete")})
        finally:
            scraper.scrape_gmaps = original_scrape
            scraper.check_website = original_check


if __name__ == "__main__":
    unittest.main()
