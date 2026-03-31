import asyncio
import sys
from playwright.async_api import async_playwright

import os
from dotenv import load_dotenv
load_dotenv()

# Ensure Proactor on Windows used by main process, but re-assert here just incase of standalone utils usage
if os.getenv("ENVIRONMENT_OS", sys.platform) == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def capture_stock_chart(ticker: str) -> bytes:
    """
    Captures a screenshot of the Chartink candlestick chart for the given ticker.
    Returns the image data as bytes.
    """
    url = f"https://chartink.com/stocks-new?from_scan=1&scan_link=scanlink:5aaed7b79143ccbfccbfdd74bc86f3d3&timeframe=daily&symbol={ticker}"
    
    print(f"📸 Capturing chart for: {ticker}")
    
    async with async_playwright() as p:
        try:
            # Launch Browser
            browser = await p.chromium.launch(headless=True)
            # Use larger viewport to ensure chart renders nicely
            page = await browser.new_page(viewport={"width": 1280, "height": 800})

            # Navigate
            print(f"   → Opening URL: {url}")
            await page.goto(url, wait_until="networkidle", timeout=60000)

            # Wait for Chart Container
            # chartink usually has ids like #tv_chart_container or just verify the page loaded
            try:
                # Wait a bit extra for tradingview widget to initialize fully
                await page.wait_for_selector("div.chart-container, iframe, #tv_chart_container", timeout=15000)
                await page.wait_for_timeout(3000) # Give it time to draw candles
            except Exception as e:
                print(f"   ⚠️ Warning: Chart container timed out for {ticker}. Taking screenshot anyway.")

            # Take Screenshot
            # We assume full page is fine, or we could select the specific element
            image_data = await page.screenshot(full_page=True, type='jpeg', quality=80)
            
            await browser.close()
            return image_data

        except Exception as e:
            print(f"   ❌ Failed to capture {ticker}: {e}")
            raise e
