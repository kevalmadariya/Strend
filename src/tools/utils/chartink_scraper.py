from playwright.async_api import async_playwright
import asyncio
import sys
import io
import csv
import re
import os
from dotenv import load_dotenv
load_dotenv()

if os.getenv("ENVIRONMENT_OS", sys.platform) == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def fetch_chartink_data(
    url: str,
    query_text: str = None,
    total_pages: int = 3,
    viewport: dict = {"width": 1280, "height": 800},
    wait_for: int = 2000
):
    """
    Scrapes data from Chartink screener via CSV download.

    Args:
        url (str): The URL of the screener.
        query_text (str, optional): Custom query to run.
        total_pages (int): Determines total entries = 20 * total_pages.
        viewport (dict): Browser viewport settings.
        wait_for (int): Time to wait (ms) for loading.

    Returns:
        tuple: (headers, all_rows) where headers is a list of strings and all_rows is a list of lists.
    """
    print(f"🔵 Started fetch_chartink_data with URL: {url}")

    all_rows = []
    headers = []

    async with async_playwright() as p:
        print("🟢 Launching browser...")
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport=viewport)

        async def take_shot(name):
            folder = "debug_screenshots"
            if not os.path.exists(folder):
                os.makedirs(folder)
            path = os.path.join(folder, f"{name}.png")
            await page.screenshot(path=path, full_page=True)
            print(f"📸 Screenshot saved: {path}")

        print(f"🌍 Navigating to URL: {url}")
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(wait_for)
        await take_shot("01_page_loaded")

        if query_text:
            print(f"📝 Typing query into textarea: {query_text}")
            await page.locator("textarea").first.fill(query_text)
            await take_shot("02_query_filled")
            
            #click enter
            # await page.keyboard.press("Enter")
            # await page.wait_for_timeout(13000)
            # await take_shot("002_enter_pressed")
            
            print("⚙️ Clicking 'Generate' button (robust selector)")
            generate_btn = (
                page.get_by_role("button", name=re.compile(r"generate", re.IGNORECASE))
                .or_(page.locator("button:has-text('Generate'), [role='button']:has-text('Generate')"))
                .or_(page.locator("[aria-label*='generate' i], [title*='generate' i]"))
                .first
            )
            await generate_btn.click()
            await page.wait_for_timeout(1000)
            await take_shot("03_after_generate")

            print("▶️ Clicking 'Run Scan' button (robust selector)")
            run_scan_btn = (
                page.get_by_role("button", name=re.compile(r"run scan", re.IGNORECASE))
                .or_(page.locator("[role='button']:has-text('Run Scan'), div:has-text('Run Scan')"))
                .or_(page.locator("[title*='run scan' i], [aria-label*='run scan' i]"))
                .first
            )
            await run_scan_btn.click()
            await page.wait_for_timeout(12000)
            await take_shot("04_after_run_scan")

        # ── Set rows-per-page so we get 20 * total_pages entries ──────────────
        entries_to_show = 20 * total_pages
        print(f"📊 Setting rows-per-page to {entries_to_show} (20 × {total_pages})")
        try:
            # Try common selector patterns used by DataTables / custom UIs
            rpp_selectors = [
                os.getenv("CHARTINK_ROWS_SELECTOR", ""),
                "select[name='scan_results_length']",
                "select.dataTables_length",
                "select[name='length']",
            ]
            rpp_selectors = [s for s in rpp_selectors if s]  # drop empty strings

            set_ok = False
            for sel in rpp_selectors:
                try:
                    elem = page.locator(sel)
                    if await elem.count() > 0:
                        await elem.select_option(str(entries_to_show))
                        await page.wait_for_load_state("networkidle")
                        await page.wait_for_timeout(wait_for)
                        await take_shot("05_rows_per_page_set")
                        print(f"✅ Rows-per-page set via: {sel}")
                        set_ok = True
                        break
                except Exception:
                    continue

            if not set_ok:
                print("⚠️ Could not find rows-per-page selector — CSV will contain whatever the site defaults to.")
                await take_shot("05_rows_per_page_not_found")

        except Exception as e:
            print(f"⚠️ Rows-per-page block error: {e}")

        # ── Download CSV; Playwright saves to its own temp path — we read & discard ──
        print("📥 Clicking CSV button and intercepting download...")
        try:
            async with page.expect_download() as dl_info:
                await page.click("div.scan-results-toolbar-button:has-text('CSV')")
            download = await dl_info.value

            # `download.path()` returns Playwright's internal temp file — no explicit save needed
            tmp_path = await download.path()
            await take_shot("06_after_csv_download")

            with open(tmp_path, "r", encoding="utf-8") as f:
                raw = f.read()

            # Parse CSV fully in memory
            reader = csv.reader(io.StringIO(raw))
            rows = list(reader)
            if rows:
                headers = rows[0]
                all_rows = rows[1:entries_to_show + 1]  # cap at 20 * total_pages

            print(f"✅ Parsed {len(all_rows)} rows (capped at {entries_to_show}) and {len(headers)} columns from CSV.")

        except Exception as e:
            print(f"❌ CSV download/parse failed: {e}")

        print("🛑 Closing browser")
        await browser.close()

    print("✅ Scraping completed.")
    return headers, all_rows