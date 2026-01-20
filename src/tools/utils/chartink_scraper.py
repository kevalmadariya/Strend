from playwright.async_api import async_playwright
import asyncio
import sys  

# --- FIX START ---
# This forces Windows to use the correct Event Loop for Playwright
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def fetch_chartink_data(
    url: str,
    query_text: str = None,
    total_pages: int = 3,
    viewport: dict = {"width": 1280, "height": 800},
    wait_for: int = 2000
):
    """
    Scrapes data from Chartink screener.
    
    Args:
        url (str): The URL of the screener.
        query_text (str, optional): Custom query to run.
        total_pages (int): Number of pages to scrape.
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

        print(f"🌍 Navigating to URL: {url}")
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(wait_for)

        if query_text:
            print(f"📝 Typing query into textarea: {query_text}")
            textarea_selector = "textarea[name='comment']"
            await page.fill(textarea_selector, query_text)

            print("⚙️ Clicking 'Generate' button")
            generate_btn_selector = "button:has-text('Generate')"
            await page.click(generate_btn_selector)
            await page.wait_for_timeout(1000)

            print("▶️ Clicking 'Run Scan' button")
            run_scan_selector = "div[title='Click to run scan']"
            await page.click(run_scan_selector)
            await page.wait_for_timeout(1000)

        print("📄 Starting table extraction...")

        for i in range(1, total_pages + 1):
            print(f"📄 Extracting page {i}/{total_pages}")
            table_selector = (
                "table.rounded-b-\[0\.4375rem\].min-w-max.md\:w-full.whitespace-nowrap"
            )
            try:
                await page.wait_for_selector(table_selector, timeout=10000)
            except Exception as e:
                print(f"⚠️ Table not found on page {i}: {e}")
                break

            # extract headers on first page only
            if i == 1:
                print("📌 Extracting table headers")
                ths = await page.query_selector_all(f"{table_selector} thead th")
                headers = [await th.inner_text() for th in ths]

            print("📌 Extracting table rows")
            rows = await page.query_selector_all(f"{table_selector} tbody tr")
            for row in rows:
                cells = await row.query_selector_all("td")
                row_data = [await cell.inner_text() for cell in cells]
                if row_data:
                    all_rows.append(row_data)

            # Pagination
            if i < total_pages:
                try:
                    next_page = str(i + 1)
                    print(f"➡️ Going to next page: {next_page}")
                    pagination = page.locator("div.hidden.sm\\:flex.w-fit.items-center")
                    
                    # Check if next page button exists/is enabled
                    next_btn = pagination.locator(f'button:text("{next_page}")')
                    if await next_btn.count() > 0:
                        await next_btn.click()
                        await page.wait_for_load_state("networkidle")
                        await page.wait_for_timeout(wait_for)
                    else:
                        print("⚠️ Next page button not found, stopping.")
                        break
                except Exception as e:
                    print(f"⚠️ Pagination failed: {e}")
                    break

        print("🛑 Closing browser") 
        await browser.close()
    
    print("✅ Scraping completed.")
    return headers, all_rows
