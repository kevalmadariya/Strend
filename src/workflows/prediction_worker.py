
import asyncio
import os
import sys
import shutil
import json
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from typing import List, Dict, Any

# Ensure project root is in path even in subprocess
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.tools.utils.chartink_scraper import fetch_chartink_data
from src.tools.utils.technical_analysis_utils import calculate_trend, calculate_chart_patterns, calculate_indicators
from src.tools.utils.chart_capture import capture_stock_chart
from src.tools.utils.fetch_and_store_fundametals import fetch_and_store_fundamentals
from src.tools.utils.news_scraper import scrape_news_from_groww
from src.tools.trading_bot.report_generator import create_report_html
from src.tools.trading_bot.pdf_generator import convert_html_to_pdf
from src.tools.trading_bot.email_sender import send_report_email
from src.core import multi_processor

# --- Sync Wrapper for ProcessPoolExecutor ---
def prediction_worker_wrapper(email, max_price, required_trend, analysis_months):
    """
    This runs INSIDE the new process.
    We convert the parameters (all strings/primitives) into the async workflow.
    """
    print(f"[Process {os.getpid()}] 👷 Prediction Worker Started for {email}")
    
    # Run the async workflow in a new event loop for this process
    try:
        import os
        from dotenv import load_dotenv
        load_dotenv()
        if os.getenv("ENVIRONMENT_OS", sys.platform) == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            
        return asyncio.run(
            execute_prediction_workflow(email, max_price, required_trend, analysis_months)
        )
    except Exception as e:
        print(f"❌ [Process {os.getpid()}] Critical Error: {e}")
        return f"Failed: {e}"

# --- Helper Functions ---
def calculate_fundamental_score(data: Dict) -> int:
    score = 0
    if not data: return 0
    try:
        # Profitability
        if float(data.get("ROE", 0) or 0) > 15: score += 20
        if float(data.get("ROCE", 0) or 0) > 15: score += 20
        
        # Growth
        if float(data.get("Sales Growth", 0) or 0) > 10: score += 15
        if float(data.get("Profit Growth", 0) or 0) > 10: score += 15
        
        # Health
        if float(data.get("Debt/Equity", 100) or 100) < 1: score += 15
        
        # Valuation / Other
        peg = data.get("PEG")
        if peg and float(peg) < 1.5: score += 15
        
    except Exception:
        pass
    return score

async def execute_prediction_workflow(email, max_price, required_trend, analysis_months):
    start_time = datetime.now()
    
    # 1. Setup Folders & Checkpoint
    today_str = datetime.now().strftime("%d-%m-%Y")
    base_dir = r"c:\General\Strend"
    today_folder = os.path.join(base_dir, today_str)
    screenshot_folder = os.path.join(today_folder, "ScreenShot")
    os.makedirs(screenshot_folder, exist_ok=True)
    
    checkpoint_path = os.path.join(today_folder, "checkpoint_v2.json")
    checkpoint = {
        "scraped_tickers": {}, # {ticker: price}
        "trend_results": {},   # {ticker: trend_val}
        "tech_results": {},    # {ticker: {patterns, indicators, chart_path}}
        "fund_results": {},    # {ticker: {data, score}}
        "news_results": {},    # {ticker: [news]}
        "skipped_tickers": []  # List of tickers filtered out
    }
    
    if os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)
            print(f"🔄 [Resume] Loaded checkpoint V2.")
        except Exception as e:
            print(f"⚠️ [Resume] Failed to load checkpoint: {e}")

    def save_checkpoint():
        try:
            with open(checkpoint_path, "w", encoding="utf-8") as f:
                json.dump(checkpoint, f, indent=4)
        except Exception as e:
            print(f"⚠️ Checkpoint save failed: {e}")

    # --- STAGE 1: SCRAPE & PRICE FILTER ---
    print("\n🔵 [Stage 1] Scraping & Price Filter")
    if not checkpoint["scraped_tickers"]:
        try:
            url = "https://chartink.com/screener/macd-bullish-crossover"
            headers, rows = await fetch_chartink_data(url, total_pages=2)
            
            symbol_idx = 2
            price_idx = 6
            if "Symbol" in headers: symbol_idx = headers.index("Symbol")
            if "Price" in headers: price_idx = headers.index("Price")
            
            count = 0
            for row in rows:
                if len(row) > max(symbol_idx, price_idx):
                    t = row[symbol_idx]
                    try: p = float(row[price_idx])
                    except: p = 0.0
                    
                    if p <= float(max_price):
                        checkpoint["scraped_tickers"][t] = p
                        count += 1
            
            save_checkpoint()
            print(f"✅ Found {count} tickers under {max_price}")
        except Exception as e:
            print(f"❌ Scrape failed: {e}")
            return f"Scrape failed: {e}"
    else:
        print(f"✅ Using {len(checkpoint['scraped_tickers'])} tickers from checkpoint.")

    all_tickers = list(checkpoint["scraped_tickers"].keys())
    
    # --- STAGE 2: TREND FILTER ---
    print("\n🔵 [Stage 2] Trend Filter")
    calc_start = date.today() - relativedelta(months=int(analysis_months))
    calc_end = date.today()
    
    trend_passed_tickers = []
    
    async def process_trend(t):
        if t in checkpoint["trend_results"]:
            return t, checkpoint["trend_results"][t]
        
        try:
            # Run blocking calculation in thread
            trend_data = await asyncio.to_thread(calculate_trend, t, calc_start, calc_end)
            # Store just the scalar 1 or 0 for filter, or the whole dict? 
            # calculate_trend returns dict usually like {'Trend': x, 'Score': y} 
            # Assuming calculate_trend returns the dict we saw earlier.
            # Wait, let's assume it returns standard dict. 
            # We need to extract the "Bullish/Bearish" logic.
            # Best to store the whole result.
            return t, trend_data
        except Exception as e:
            print(f"❌ Trend error {t}: {e}")
            return t, None

    # Batch process for concurrency
    sem = asyncio.Semaphore(5)
    async def limited_trend(t):
        async with sem:
            return await process_trend(t)

    # Process pending
    tasks = [limited_trend(t) for t in all_tickers if t not in checkpoint["trend_results"]]
    if tasks:
        print(f"   Analyzing trend for {len(tasks)} stocks...")
        results = await asyncio.gather(*tasks)
        for t, res in results:
            if res:
                checkpoint["trend_results"][t] = res
        save_checkpoint()

    # Filter
    for t in all_tickers:
        res = checkpoint["trend_results"].get(t)
        if not res: continue
        
        # Determine 1 or 0
        direction = str(res.get("Trend", "")).lower()
        is_bullish = "bull" in direction or "up" in direction
        req_bullish = str(required_trend) == "1"
        
        match = False
        if req_bullish and is_bullish: match = True
        elif not req_bullish and not is_bullish: match = True
        
        if match:
            trend_passed_tickers.append(t)
            
    print(f"✅ Trend Filter: {len(trend_passed_tickers)} / {len(all_tickers)} passed.")

    # --- STAGE 3: TECHNICALS & CHARTS ---
    print("\n🔵 [Stage 3] Technicals & Charts")
    tech_passed_tickers = trend_passed_tickers # No filter here, just processing
    
    async def process_tech(t):
        if t in checkpoint["tech_results"]:
            return
            
        try:
            # Patterns & Indicators
            patterns = await asyncio.to_thread(calculate_chart_patterns, t, calc_start, calc_end)
            indicators = await asyncio.to_thread(calculate_indicators, t, calc_start, calc_end)
            
            # Chart
            chart_path = ""
            try:
                img_bytes = await capture_stock_chart(t+".NS")
                if not img_bytes: img_bytes = await capture_stock_chart(t)
                if img_bytes:
                    fname = f"{t}.png"
                    fpath = os.path.join(screenshot_folder, fname)
                    with open(fpath, "wb") as f:
                        f.write(img_bytes)
                    chart_path = fname
            except Exception as e:
                print(f"   ⚠️ Chart fail {t}: {e}")

            checkpoint["tech_results"][t] = {
                "patterns": patterns,
                "indicators": indicators,
                "chart": chart_path
            }
        except Exception as e:
            print(f"❌ Tech fail {t}: {e}")

    # Batched
    sem_tech = asyncio.Semaphore(3) # Charts are heavy
    async def limited_tech(t):
        async with sem_tech:
            await process_tech(t)
            save_checkpoint() # Save incrementally

    tasks_tech = [limited_tech(t) for t in tech_passed_tickers if t not in checkpoint["tech_results"]]
    if tasks_tech:
        print(f"   Processing technicals for {len(tasks_tech)} stocks...")
        await asyncio.gather(*tasks_tech)
    
    print(f"✅ Technicals done.")

    # --- STAGE 4: FUNDAMENTALS FILTER ---
    print("\n🔵 [Stage 4] Fundamentals (>50 Score)")
    fund_passed_tickers = []
    
    async def process_fund(t):
        if t in checkpoint["fund_results"]:
            return
            
        try:
            # fetch_and_store_fundamentals expects LIST. 
            # We call it with 1 item to manage loop here.
            # It returns {"status":..., "data": {ticker: {...}}}
            res = await fetch_and_store_fundamentals([t])
            data = res.get("data", {}).get(t, {})
            score = calculate_fundamental_score(data)
            
            checkpoint["fund_results"][t] = {
                "data": data,
                "score": score
            }
        except Exception as e:
            print(f"❌ Fund fail {t}: {e}")
            
    sem_fund = asyncio.Semaphore(3)
    async def limited_fund(t):
        async with sem_fund:
            await process_fund(t)
            save_checkpoint()

    tasks_fund = [limited_fund(t) for t in tech_passed_tickers if t not in checkpoint["fund_results"]]
    if tasks_fund:
        print(f"   Fetching fundamentals for {len(tasks_fund)} stocks...")
        await asyncio.gather(*tasks_fund)
        
    # Filter
    for t in tech_passed_tickers:
        res = checkpoint["fund_results"].get(t)
        if res and res["score"] > 50:
            fund_passed_tickers.append(t)
            
    print(f"✅ Fundamentals Filter: {len(fund_passed_tickers)} / {len(tech_passed_tickers)} passed (Score > 50).")

    # --- STAGE 5: NEWS ---
    print("\n🔵 [Stage 5] News")
    final_tickers = fund_passed_tickers
    
    async def process_news(t):
        if t in checkpoint["news_results"]:
            return
        
        try:
            news = await scrape_news_from_groww(t)
            checkpoint["news_results"][t] = news
        except Exception as e:
            print(f"❌ News fail {t}: {e}")
            checkpoint["news_results"][t] = []

    sem_news = asyncio.Semaphore(3)
    async def limited_news(t):
        async with sem_news:
            await process_news(t)
            save_checkpoint()
            
    tasks_news = [limited_news(t) for t in final_tickers if t not in checkpoint["news_results"]]
    if tasks_news:
        print(f"   Fetching news for {len(tasks_news)} stocks...")
        await asyncio.gather(*tasks_news)
        
    print(f"✅ News done.")

    # --- STAGE 6: REPORT ---
    print("\n🔵 [Stage 6] Reporting")
    
    # Capture Nifty
    try:
        nifty_bytes = await capture_stock_chart("^NSEI")
        if nifty_bytes:
             with open(os.path.join(screenshot_folder, "nifty.png"), "wb") as f:
                 f.write(nifty_bytes)
    except: pass
    
    # Assemble Data for Report
    report_data = []
    strong_list = []
    
    for t in final_tickers:
        price = checkpoint["scraped_tickers"].get(t, 0)
        trend = checkpoint["trend_results"].get(t, {})
        tech = checkpoint["tech_results"].get(t, {})
        fund = checkpoint["fund_results"].get(t, {})
        news = checkpoint["news_results"].get(t, [])
        
        strong_list.append(t)
        
        # Flatten logic for report generator
        # The existing create_report_html expects a DataFrame with specific columns
        # We need to map our structure to that.
        
        row = {
            "ticker": t,
            "Symbol": t,
            "Price": price,
            "technical": {
                **trend,
                **tech.get("patterns", {}),
                **tech.get("indicators", {}),
                "price": price
            },
            "patterns": tech.get("patterns", {}),
            "fundametal_resullt": {
                "details": fund.get("data", {}),
                "rating": f"Score: {fund.get('score', 0)}" 
            },
            "news_results": news
        }
        report_data.append(row)

    if not report_data:
        print("⚠️ No stocks survived all filters. Report will be empty.")
        return "No stocks passed all filters."

    import pandas as pd
    df = pd.DataFrame(report_data)
    strong_str = ", ".join(strong_list)
    
    html_content = create_report_html(df, {}, strong_str, strong_str, today_folder)
    html_path = os.path.join(today_folder, "stock_analysis_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    pdf_path = os.path.join(today_folder, "Final_Stock_Analysis.pdf")
    await convert_html_to_pdf(html_path, pdf_path)
    
    # Email
    print(f"🔵 [Email] Sending to {email}...")
    send_report_email(email, pdf_path, strong_list, [strong_str])
    
    # Cleanup
    if os.path.exists(screenshot_folder):
        shutil.rmtree(screenshot_folder, ignore_errors=True)
        
    duration = datetime.now() - start_time
    print(f"🏁 DONE in {duration}")
    return f"Completed in {duration}"
