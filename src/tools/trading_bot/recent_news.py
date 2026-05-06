import asyncio
from playwright.async_api import async_playwright
import json
import nest_asyncio

nest_asyncio.apply()

async def extract_pulse_news():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        url = "https://pulse.zerodha.com/"
        print(f"Navigating to {url}...")
        await page.goto(url)

        # --- 1. DYNAMIC KEYWORD EXTRACTION ---
        print("Extracting dynamic keywords from Word Cloud...")

        # Always include these fixed categories
        active_categories = {"nifty", "ipo"}

        # Locate the word cloud links
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

        print(f"Active Categories: {list(active_categories)}")

        # --- 2. INITIALIZE DICTIONARY ---
        # Create a dictionary entry for every active category + a general fallback
        categorized_news = {cat: [] for cat in active_categories}
        categorized_news["general"] = []

        # --- 3. NEWS EXTRACTION ---
        news_items = page.locator("li.box.item")
        count_news = await news_items.count()
        print(f"Found {count_news} news items. Processing...")

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
                        break # Stop after first match to keep it in one primary bucket

                # Fallback if no keywords matched
                if not assigned:
                    categorized_news["general"].append(news_object)

        # Output the result
        print(json.dumps(categorized_news, indent=4))

        await browser.close()
        return categorized_news

top_news = {}
if __name__ == "__main__":
     top_news = asyncio.run(extract_pulse_news())

print(top_news)