import asyncio
from playwright.async_api import async_playwright
import re

async def scrape_news_from_groww(ticker: str):
    """
    Scrapes news from Groww for a given ticker.
    Returns a list of dictionaries with keys: 'time_str', 'news', 'url'.
    """
    print(f"🕵️ [Scraper] Starting news extraction for: {ticker}")
    news_data = []
    
    try:
        async with async_playwright() as p:
            # Launch browser with slightly longer timeout args if needed
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")
            page = await context.new_page()

            try:
                print(f"🌍 [Scraper] Navigating to Groww...")
                # 1. Open Groww
                await page.goto("https://groww.in/", timeout=40000)

                # 2. Activate Search
                # Try multiple potential selectors for the search bar
                search_selectors = ["input#globalSearch23", "div.se27SeSearchMainDivPlaceholder", "input[type='text']"]
                search_input = None
                
                for sel in search_selectors:
                     if await page.locator(sel).count() > 0 and await page.locator(sel).is_visible():
                         # If it's the placeholder div, click it to reveal input, then find input
                         if "Placeholder" in sel:
                             await page.locator(sel).click()
                             search_input = page.locator("input#globalSearch23")
                         else:
                             search_input = page.locator(sel)
                         break
                
                if not search_input:
                     # Last ditch: keyboard shortcut
                     await page.keyboard.press("Control+K")
                     search_input = page.locator("input#globalSearch23")

                # 3. Type Ticker
                print(f"⌨️ [Scraper] Searching for ticker: {ticker}")
                await search_input.wait_for(state="visible", timeout=10000)
                await search_input.fill("")
                await search_input.type(ticker, delay=150) # Type slower

                # 4. Click Suggestion
                print(f"point [Scraper] Waiting for suggestions...")
                # Wait for the suggestion box to appear
                await page.wait_for_selector(".se27SeSuggestion, .se27SeResultList", timeout=10000)
                
                # Use first suggestion
                suggestions = page.locator(".se27SeSuggestion")
                if await suggestions.count() > 0:
                    await suggestions.first.click()
                else:
                    print("⚠️ No suggestions found.")
                    await browser.close()
                    return []

                # 5. Wait for Navigation
                print(f"⏳ [Scraper] Waiting for stock page...")
                await page.wait_for_url("**/stocks/**", timeout=20000)

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
                except Exception:
                     # It's possible there are no news items, or selector changed.
                     print(f"⚠️ News container not found (timeout). Possibly no news.")
                     await browser.close()
                     return []

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
            
            except Exception as e_inner:
                print(f"❌ [Scraper] Inner Error: {e_inner}")
            
            await browser.close()
            
    except Exception as e_outer:
         print(f"❌ [Scraper] Critical Error or Browser Launch Failed: {e_outer}")

    print(f"✅ [Scraper] Finished. Tokens found: {len(news_data)}")
    return news_data
