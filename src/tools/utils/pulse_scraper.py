import asyncio
from playwright.async_api import async_playwright
import json

from dotenv import load_dotenv

load_dotenv()

import os
from datetime import date, timedelta
import shutil

async def extract_pulse_news(domain: str = None):
    """
    Scrapes news from Pulse by Zerodha.
    Checks local JSON cache first. If missing, scrapes and saves to cache.
    """
    base_cache_path = os.getenv("PULSE_DATA_PATH", r"c:\General\Strend\playit_data\pulse_news")
    
    # 0. Cleanup Yesterday's Cache
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_folder = os.path.join(base_cache_path, yesterday)
    if os.path.exists(yesterday_folder):
        try:
            shutil.rmtree(yesterday_folder)
            print(f"🗑️ [Pulse Scraper] Deleted yesterday's cache: {yesterday_folder}")
        except Exception as e:
            print(f"⚠️ [Pulse Scraper] Failed to delete yesterday's cache: {e}")

    # 1. Check Today's Cache
    cache_path = os.path.join(base_cache_path, date.today().strftime("%Y-%m-%d"), "pulse_news.json")
    if os.path.exists(cache_path):
        print(f"📂 [Pulse Scraper] Reading from cache: {cache_path}")
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            # If domain filter is requested on cached data
            if domain:
                domain = domain.lower().strip()
                if domain in data:
                    return {domain: data[domain]}
                else:
                    return {domain: []}
            return data
        except Exception as e:
            print(f"⚠️ [Pulse Scraper] Cache read error: {e}. Proceeding to scrape.")

    print(f"🕵️ [Pulse Scraper] Starting extraction (No cache found)...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            url = "https://pulse.zerodha.com/"
            print(f"🌍 [Pulse Scraper] Navigating to {url}...")
            await page.goto(url, timeout=60000)

            # --- 1. DYNAMIC KEYWORD EXTRACTION ---
            print("🔍 [Pulse Scraper] Extracting dynamic keywords from Word Cloud...")

            # Always include these fixed categories
            active_categories = {"nifty", "ipo"}

            # Locate the word cloud links
            # Wait for wordcloud to be visible
            try:
                await page.wait_for_selector("#wordcloud", timeout=10000)
                word_cloud_items = page.locator("#wordcloud a.word")
                count_words = await word_cloud_items.count()

                for i in range(count_words):
                    el = word_cloud_items.nth(i)

                    # Get the style attribute to check font size
                    style_attr = await el.get_attribute("style") or ""
                    # Get the clean word from data-word attribute
                    word_text = await el.get_attribute("data-word")

                    if word_text:
                        # Logic: Check if it is a "Big Text" (32px)
                        if "32px" in style_attr:
                            active_categories.add(word_text.lower())
            except Exception as e:
                 print(f"⚠️ [Pulse Scraper] Wordcloud extraction issue: {e}")

            print(f"📋 [Pulse Scraper] Active Categories: {list(active_categories)}")

            # --- 2. INITIALIZE DICTIONARY ---
            # Create a dictionary entry for every active category + a general fallback
            categorized_news = {cat: [] for cat in active_categories}
            categorized_news["general"] = []

            # --- 3. NEWS EXTRACTION ---
            news_items = page.locator("li.box.item")
            count_news = await news_items.count()
            print(f"📄 [Pulse Scraper] Found {count_news} news items. Processing...")

            for i in range(count_news):
                item = news_items.nth(i)

                # Extract basic details
                headline_el = item.locator("h2 a")
                if await headline_el.count() > 0:
                    headline_text = await headline_el.inner_text()
                    link = await headline_el.get_attribute("href")

                    summary_el = item.locator(".desc")
                    summary_text = await summary_el.inner_text() if await summary_el.count() > 0 else ""

                    meta_el = item.locator(".meta")
                    meta_text = await meta_el.inner_text() if await meta_el.count() > 0 else ""

                    news_object = {
                        "headline": headline_text.strip(),
                        "summary": summary_text.strip(),
                        "meta": meta_text.strip(),
                        "url": link
                    }

                    # --- 4. CATEGORIZATION LOGIC ---
                    # Search for category keywords in both headline and summary
                    full_text = (headline_text + " " + summary_text).lower()
                    assigned = False

                    # Check against our dynamic list of categories
                    for category in active_categories:
                        if category in full_text:
                            categorized_news[category].append(news_object)
                            assigned = True
                            # We don't break here if we want it in multiple buckets? 
                            # The original code broke after first match. Stick to that.
                            break 

                    # Fallback if no keywords matched
                    if not assigned:
                        categorized_news["general"].append(news_object)
            
            # --- SAVE TO CACHE ---
            try:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(categorized_news, f, indent=4)
                print(f"💾 [Pulse Scraper] Saved data to {cache_path}")
            except Exception as e:
                print(f"⚠️ [Pulse Scraper] Failed to save cache: {e}")

            # Filter if domain is requested
            if domain:
                domain = domain.lower().strip()
                if domain in categorized_news:
                    print(f"🎯 [Pulse Scraper] Filtering for domain: {domain}")
                    return {domain: categorized_news[domain]}
                else:
                    print(f"⚠️ [Pulse Scraper] Domain '{domain}' not found in active categories. Returning empty list.")
                    return {domain: []}
            
            return categorized_news

        except Exception as e:
            print(f"❌ [Pulse Scraper] Error: {e}")
            return {"error": str(e)}

        finally:
            await browser.close()
