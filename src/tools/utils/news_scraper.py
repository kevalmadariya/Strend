import asyncio
from playwright.async_api import async_playwright
import re

async def scrape_news_from_groww(ticker: str):
    """
    Scrapes news from Groww for a given ticker.
    Returns a list of dictionaries with keys: 'time_str', 'news', 'url'.
    """
    print(f"🕵️ [Scraper] Starting news extraction for: {ticker}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        news_data = []

        try:
            print(f"🌍 [Scraper] Navigating to Groww...")
            # 1. Open Groww
            await page.goto("https://groww.in/", timeout=60000)

            # 2. Activate Search
            search_input = page.locator("input#globalSearch23")
            if not await search_input.is_visible():
                placeholder = page.locator(".se27SeSearchMainDivPlaceholder")
                if await placeholder.count() > 0:
                    await placeholder.click(force=True)
                else:
                    await page.keyboard.press("Control+K")

            # 3. Type Ticker
            print(f"⌨️ [Scraper] Searching for ticker: {ticker}")
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill("")
            await search_input.type(ticker, delay=100)

            # 4. Click Suggestion
            print(f"point [Scraper] Waiting for suggestions...")
            suggestion = page.locator(".se27SeSuggestion").first
            await suggestion.wait_for(state="visible", timeout=5000)
            await suggestion.click()

            # 5. Wait for Navigation
            print(f"⏳ [Scraper] Waiting for stock page...")
            await page.wait_for_url("**/stocks/**", timeout=15000)

            # 6. Go to Market News
            current_url = page.url
            if current_url.endswith("/"):
                current_url = current_url[:-1]
            
            news_url = f"{current_url}/market-news"
            print(f"🔗 [Scraper] Navigating to News Section: {news_url}")
            await page.goto(news_url, timeout=30000)

            # 7. Extract News
            news_container = ".stockNews_newsRow__BC7Ia"
            print(f"👀 [Scraper] Looking for news items...")
            try:
                await page.wait_for_selector(news_container, timeout=10000)
                news_items = page.locator(news_container)
                count = await news_items.count()
                limit = min(count, 5) # Fetch up to 5 items
                print(f"📄 [Scraper] Found {count} news items, processing {limit}...")

                for i in range(limit):
                    item = news_items.nth(i)

                    header_el = item.locator(".mnc671BoxHeaderText")
                    full_header = await header_el.inner_text() if await header_el.count() > 0 else ""
                    # Header often looks like "Source . 1h ago"
                    time_text = full_header.split(".")[-1].strip() if "." in full_header else full_header

                    body_el = item.locator(".mnc671BoxItemTitle")
                    news_text = await body_el.inner_text() if await body_el.count() > 0 else ""

                    link_el = item.locator("a")
                    news_link = await link_el.get_attribute("href") if await link_el.count() > 0 else ""
                    
                    if news_link and news_link.startswith("/"):
                         news_link = "https://groww.in" + news_link

                    print(f"  > Found: {time_text} - {news_text[:30]}...")
                    news_data.append({
                        "time_str": time_text,
                        "news": news_text.replace("\n", " ").strip(),
                        "url": news_link
                    })
            except Exception as e:
                print(f"⚠️ [Scraper] Error parsing news items: {e}")
                
        except Exception as e:
            print(f"❌ [Scraper] Error during scraping flow: {e}")

        await browser.close()
        print(f"✅ [Scraper] Finished. Tokens found: {len(news_data)}")
        return news_data
