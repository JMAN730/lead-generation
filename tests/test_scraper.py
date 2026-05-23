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
            self.assertFalse(os.path.exists(os.path.join(tmp, "leads_a.progress.json.tmp")))

    def test_load_lines_file_ignores_blank_lines_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "values.txt")
            with open(path, "w") as f:
                f.write("\n# comment\nRoofers\n  Concrete  \n")

            self.assertEqual(scraper.load_lines_file(path), ["Roofers", "Concrete"])

    def test_sanitize_csv_value_blocks_formula_prefixes(self):
        self.assertEqual(scraper.sanitize_csv_value("=cmd"), "'=cmd")
        self.assertEqual(scraper.sanitize_csv_value("+SUM(A1:A2)"), "'+SUM(A1:A2)")
        self.assertEqual(scraper.sanitize_csv_value("Plain Name"), "Plain Name")

    def test_score_lead_prioritizes_call_ready_no_website_leads(self):
        lead = {
            "Phone": "555-111-2222",
            "Email": "owner@example.com",
            "Website Reason": "missing_or_invalid_url",
            "Rating": 4.8,
            "Reviews": 120,
        }

        scored = scraper.score_lead(lead)

        self.assertEqual(scored["Call Priority"], "High")
        self.assertGreaterEqual(scored["Priority Score"], 70)
        self.assertIn("no website", scored["Priority Reason"])

    def test_dedupe_keys_normalize_phone_maps_and_domain(self):
        lead = {
            "Name": "ACME Roofing",
            "Phone": "+1 (555) 111-2222",
            "Website": "www.example.com",
            "Google Maps URL": "https://maps.example/place/1",
            "Yelp URL": "https://www.yelp.com/biz/acme",
            "Source": "yelp",
            "Source ID": "acme-id",
        }

        keys = scraper.get_lead_dedupe_keys(lead)

        self.assertIn("phone:5551112222", keys)
        self.assertIn("domain:example.com", keys)
        self.assertIn("maps:https://maps.example/place/1", keys)
        self.assertIn("yelp_id:acme-id", keys)
        self.assertIn("yelp_url:https://www.yelp.com/biz/acme", keys)

    def test_preset_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "preset.json")
            config = {"locations": ["Toledo"], "categories": ["Roofers"], "call_sheet": True}

            scraper.save_preset(path, config)

            self.assertEqual(scraper.load_preset(path), config)

    def test_preset_value_coercion(self):
        self.assertEqual(scraper.coerce_positive_int("2", "concurrency"), 2)
        self.assertEqual(scraper.coerce_string_list([" Toledo ", "", "Akron"], "locations"), ["Toledo", "Akron"])
        self.assertEqual(scraper.coerce_sources("google,yelp"), ["google", "yelp"])
        self.assertEqual(scraper.coerce_sources(["Google", "google"]), ["google"])
        with self.assertRaises(ValueError):
            scraper.coerce_positive_int("0", "limit")
        with self.assertRaises(ValueError):
            scraper.coerce_string_list("Toledo", "locations")
        with self.assertRaises(ValueError):
            scraper.coerce_sources("facebook")

    def test_progress_supports_source_keys_and_old_google_keys(self):
        progress = {("Toledo", "Roofers"), ("yelp", "Toledo", "Concrete")}

        self.assertTrue(scraper.is_progress_done(progress, "google", "Toledo", "Roofers"))
        self.assertTrue(scraper.is_progress_done(progress, "yelp", "Toledo", "Concrete"))
        self.assertFalse(scraper.is_progress_done(progress, "yelp", "Toledo", "Roofers"))

    async def test_check_website_treats_blocked_real_sites_as_valid(self):
        async def handler(request):
            return httpx.Response(403)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await scraper.check_website(client, "example.com", asyncio.Semaphore(1))
            self.assertTrue(result["is_valid"])
            self.assertEqual(result["status_code"], 403)

            result = await scraper.check_website(client, "https://facebook.com/foo", asyncio.Semaphore(1))
            self.assertFalse(result["is_valid"])
            self.assertEqual(result["reason"], "social_media")

    async def test_check_website_has_outer_timeout(self):
        async def handler(request):
            await asyncio.sleep(0.05)
            return httpx.Response(200)

        original_timeout = scraper.WEBSITE_CHECK_TIMEOUT
        scraper.WEBSITE_CHECK_TIMEOUT = 0.01
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                result = await scraper.check_website(client, "example.com", asyncio.Semaphore(1))
                self.assertFalse(result["is_valid"])
                self.assertEqual(result["reason"], "TimeoutError")
        finally:
            scraper.WEBSITE_CHECK_TIMEOUT = original_timeout

    async def test_yelp_api_normalizes_businesses(self):
        async def handler(request):
            self.assertEqual(request.headers["authorization"], "Bearer key")
            return httpx.Response(200, json={
                "businesses": [{
                    "id": "biz-1",
                    "name": "Local Roofer",
                    "display_phone": "(555) 111-2222",
                    "url": "https://www.yelp.com/biz/local-roofer",
                    "rating": 4.5,
                    "review_count": 42,
                }]
            })

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            results = await scraper.scrape_yelp_api(client, "Roofers in Toledo", "Toledo", "Roofers", api_key="key")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["Source"], "yelp")
        self.assertEqual(results[0]["Source ID"], "biz-1")
        self.assertEqual(results[0]["Website Reason Override"], "website_unknown")

    async def test_yelp_api_paginates_to_requested_limit(self):
        requests = []

        async def handler(request):
            params = request.url.params
            limit = int(params["limit"])
            offset = int(params["offset"])
            requests.append((limit, offset))
            businesses = []
            for i in range(offset, offset + limit):
                businesses.append({
                    "id": f"biz-{i}",
                    "name": f"Local Roofer {i}",
                    "display_phone": f"(555) 111-{i:04d}",
                    "url": f"https://www.yelp.com/biz/local-roofer-{i}",
                })
            return httpx.Response(200, json={"businesses": businesses, "total": 65})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            results = await scraper.scrape_yelp_api(client, "Roofers in Toledo", "Toledo", "Roofers", max_results=65, api_key="key")

        self.assertEqual(len(results), 65)
        self.assertEqual(requests, [(50, 0), (15, 50)])
        self.assertEqual(results[-1]["Source ID"], "biz-64")

    async def test_yelp_api_failure_raises_source_error(self):
        async def handler(request):
            return httpx.Response(429)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(scraper.SourceScrapeError):
                await scraper.scrape_yelp_api(client, "Roofers in Toledo", "Toledo", "Roofers", api_key="key")

    async def test_source_failure_does_not_save_progress(self):
        async def fake_scrape_source(*args, **kwargs):
            raise scraper.SourceScrapeError("Yelp search failed for 'Roofers in Toledo'")

        original_scrape_source = scraper.scrape_source
        scraper.scrape_source = fake_scrape_source
        try:
            with tempfile.TemporaryDirectory() as tmp:
                existing_leads = set()
                progress_set = set()
                state_lock = asyncio.Lock()
                summary = scraper.create_run_summary(["Toledo"], ["Roofers"], "leads.csv")

                with contextlib.redirect_stdout(io.StringIO()):
                    await scraper.process_category(
                        None, None, "Toledo", "Roofers", 1, tmp, existing_leads,
                        progress_set, "leads.csv", state_lock, source="yelp", summary=summary
                    )

                self.assertEqual(progress_set, set())
                self.assertFalse(os.path.exists(os.path.join(tmp, "leads.progress.json")))
                self.assertEqual(summary["categories_completed"], 0)
        finally:
            scraper.scrape_source = original_scrape_source

    async def test_run_scraper_requires_yelp_api_key(self):
        with self.assertRaisesRegex(ValueError, "YELP_API_KEY"):
            await scraper.run_scraper(["Toledo"], sources=["yelp"], summary_report=False)

    async def test_concurrent_categories_do_not_duplicate_csv_rows(self):
        async def fake_scrape(browser_context, search_query, limit, stop_check=None, chain_regex=None):
            return [{
                "Name": "=Same Lead",
                "Phone": "555-111-2222",
                "Email": None,
                "Website": None,
                "Rating": None,
                "Reviews": None,
                "Google Maps URL": "https://maps.example/place",
            }]

        async def fake_check(client, url, semaphore):
            return {"is_valid": False, "url": None, "status_code": None, "reason": "missing_or_invalid_url"}

        original_scrape = scraper.scrape_gmaps
        original_check = scraper.check_website
        scraper.scrape_gmaps = fake_scrape
        scraper.check_website = fake_check
        try:
            with tempfile.TemporaryDirectory() as tmp:
                existing_leads = set()
                progress_set = set()
                state_lock = asyncio.Lock()
                summary = scraper.create_run_summary(["Toledo"], ["Roofers", "Concrete"], "leads.csv")

                with contextlib.redirect_stdout(io.StringIO()):
                    await asyncio.gather(
                        scraper.process_category(None, None, "Toledo", "Roofers", 1, tmp, existing_leads, progress_set, "leads.csv", state_lock, summary=summary),
                        scraper.process_category(None, None, "Toledo", "Concrete", 1, tmp, existing_leads, progress_set, "leads.csv", state_lock, summary=summary),
                    )

                df = pd.read_csv(os.path.join(tmp, "leads.csv"))
                self.assertEqual(len(df), 1)
                self.assertEqual(df.loc[0, "Name"], "'=Same Lead")
                self.assertEqual(str(df.loc[0, "Normalized Phone"]), "5551112222")
                self.assertEqual(df.loc[0, "Website Reason"], "missing_or_invalid_url")
                self.assertEqual(df.loc[0, "Source"], "google")
                self.assertEqual(df.loc[0, "Call Priority"], "Medium")
                self.assertEqual(summary["duplicates_skipped"], 1)
                self.assertEqual(progress_set, {("google", "Toledo", "Roofers"), ("google", "Toledo", "Concrete")})
        finally:
            scraper.scrape_gmaps = original_scrape
            scraper.check_website = original_check

    async def test_process_category_writes_call_sheet_and_summary_counts(self):
        async def fake_scrape(browser_context, search_query, limit, stop_check=None, chain_regex=None):
            return [{
                "Name": "Priority Lead",
                "Phone": "555-333-4444",
                "Email": "owner@example.com",
                "Website": None,
                "Rating": 4.9,
                "Reviews": 150,
                "Google Maps URL": "https://maps.example/place/priority",
            }]

        async def fake_check(client, url, semaphore):
            return {"is_valid": False, "url": None, "status_code": None, "reason": "missing_or_invalid_url"}

        original_scrape = scraper.scrape_gmaps
        original_check = scraper.check_website
        scraper.scrape_gmaps = fake_scrape
        scraper.check_website = fake_check
        try:
            with tempfile.TemporaryDirectory() as tmp:
                existing_leads = set()
                progress_set = set()
                state_lock = asyncio.Lock()
                summary = scraper.create_run_summary(["Toledo"], ["Roofers"], "leads.csv")

                with contextlib.redirect_stdout(io.StringIO()):
                    await scraper.process_category(
                        None, None, "Toledo", "Roofers", 1, tmp, existing_leads,
                        progress_set, "leads.csv", state_lock, call_sheet=True, summary=summary
                    )

                call_sheet = pd.read_csv(os.path.join(tmp, "leads_call_sheet.csv"))
                self.assertEqual(call_sheet.loc[0, "Call Priority"], "High")
                self.assertEqual(str(call_sheet.loc[0, "Normalized Phone"]), "5553334444")
                self.assertEqual(summary["leads_written"], 1)
                self.assertEqual(summary["by_source"]["google"], 1)
                self.assertEqual(summary["by_website_reason"]["missing_or_invalid_url"], 1)
        finally:
            scraper.scrape_gmaps = original_scrape
            scraper.check_website = original_check

    async def test_dry_run_does_not_write_csv_or_progress(self):
        async def fake_scrape(browser_context, search_query, limit, stop_check=None, chain_regex=None):
            return [{
                "Name": "Dry Run Lead",
                "Phone": "555-222-3333",
                "Email": None,
                "Website": None,
                "Rating": None,
                "Reviews": None,
                "Google Maps URL": "https://maps.example/place",
            }]

        async def fake_check(client, url, semaphore):
            return {"is_valid": False, "url": None, "status_code": None, "reason": "missing_or_invalid_url"}

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
                    await scraper.process_category(None, None, "Toledo", "Roofers", 1, tmp, existing_leads, progress_set, "leads.csv", state_lock, dry_run=True)

                self.assertFalse(os.path.exists(os.path.join(tmp, "leads.csv")))
                self.assertFalse(os.path.exists(os.path.join(tmp, "leads.progress.json")))
                self.assertEqual(progress_set, set())
        finally:
            scraper.scrape_gmaps = original_scrape
            scraper.check_website = original_check

    async def test_facebook_url_is_captured_as_social_profile(self):
        async def fake_scrape(browser_context, search_query, limit, stop_check=None, chain_regex=None):
            return [{
                "Name": "Facebook Only Lead",
                "Phone": "555-222-3333",
                "Email": None,
                "Website": "https://www.facebook.com/facebookonlylead",
                "Rating": None,
                "Reviews": None,
                "Google Maps URL": "https://maps.example/place",
            }]

        original_scrape = scraper.scrape_gmaps
        scraper.scrape_gmaps = fake_scrape
        try:
            with tempfile.TemporaryDirectory() as tmp:
                existing_leads = set()
                progress_set = set()
                state_lock = asyncio.Lock()

                with contextlib.redirect_stdout(io.StringIO()):
                    await scraper.process_category(None, None, "Toledo", "Roofers", 1, tmp, existing_leads, progress_set, "leads.csv", state_lock)

                df = pd.read_csv(os.path.join(tmp, "leads.csv"))
                self.assertEqual(df.loc[0, "Website Reason"], "social_media")
                self.assertEqual(df.loc[0, "Facebook URL"], "https://www.facebook.com/facebookonlylead")
        finally:
            scraper.scrape_gmaps = original_scrape


if __name__ == "__main__":
    unittest.main()
