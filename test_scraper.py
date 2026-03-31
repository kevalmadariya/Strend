
import asyncio
import sys
from src.tools.utils.chartink_scraper import fetch_chartink_data

import os
from dotenv import load_dotenv
load_dotenv()

# Ensure Proactor on Windows
if os.getenv("ENVIRONMENT_OS", sys.platform) == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def test():
    url = "https://chartink.com/screener/macd-bullish-crossover"
    print(f"Testing scraper with URL: {url}")
    try:
        headers, rows = await fetch_chartink_data(url, total_pages=1)
        print("Scrape successful!")
        print("Headers:", headers)
        print(f"First 3 rows: {rows[:3]}")
    except Exception as e:
        print(f"Scrape failed: {e}")

if __name__ == "__main__":
    asyncio.run(test())
