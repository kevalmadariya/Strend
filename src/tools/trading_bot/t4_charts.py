import asyncio
import os
import pandas as pd
from datetime import date
from playwright.async_api import async_playwright

from Config.filepath import get_today_folder


def run_screenshot_process(technique="MACD_Bullish"):
    async def capture_chart(ticker, folder_path):
        """
        Captures a screenshot for a specific ticker.
        """
        url = f"https://chartink.com/stocks-new?from_scan=1&scan_link=scanlink:5aaed7b79143ccbfccbfdd74bc86f3d3&timeframe=daily&symbol={ticker}"
        
        output_filename = f"{ticker}.png"
        full_path = os.path.join(folder_path, output_filename)

        print(f"\n⏳ Processing: {ticker}")

        async with async_playwright() as p:
            try:
                # Launch Browser
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1280, "height": 800})

                # Navigate
                print(f"   → Opening URL for {ticker}...")
                await page.goto(url, wait_until="networkidle")

                # Wait for Chart Container
                try:
                    await page.wait_for_selector("div.chart-container, iframe, #tv_chart_container", timeout=10000)
                    print("   → Chart element detected, rendering...")
                    await page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"   ⚠️ Warning: Chart container timed out for {ticker}. Taking screenshot anyway.")

                # Take Screenshot
                await page.screenshot(path=full_path, full_page=True)
                print(f"   ✅ Screenshot saved: {full_path}")

                await browser.close()
                return True

            except Exception as e:
                print(f"   ❌ Failed to capture {ticker}: {e}")
                return False

    async def main_process():
        # 1. Setup Paths and Dates
        today_str = get_today_folder() + "/" + technique + "/"
        base_dir = today_str
        screenshot_dir = os.path.join(base_dir, "ScreenShot")

        # Ensure Screenshot Directory Exists
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
            print(f"📁 Created directory: {screenshot_dir}")

        # 2. Load the CSV
        SCAN_TITLE = "MACD_Bullish"
        csv_filename = f"final_{SCAN_TITLE}.csv"
        csv_path = os.path.join(base_dir, csv_filename)

        if not os.path.exists(csv_path):
            print(f"❌ Error: CSV file not found at {csv_path}")
            return

        print(f"📊 Loading data from: {csv_path}")
        df = pd.read_csv(csv_path)

        if 'Symbol' not in df.columns:
            print("❌ Error: CSV must contain a 'Symbol' column.")
            return

        print(f"🔹 Found {len(df)} stocks to process.")
        print("-" * 40)

        success_count = 0
        for index, row in df.iterrows():
            ticker = row['Symbol']

            # Await screenshot capture
            result = await capture_chart(ticker, screenshot_dir)

            if result:
                success_count += 1

            await asyncio.sleep(1)

        print("-" * 40)
        print(f"🎉 Process Complete. {success_count}/{len(df)} screenshots captured successfully.")
        print(f"📂 Files saved in: {screenshot_dir}")

    # Run the async process
    return asyncio.run(main_process())

