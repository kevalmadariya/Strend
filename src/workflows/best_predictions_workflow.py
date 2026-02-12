import asyncio
import os
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from datetime import date
from dateutil.relativedelta import relativedelta
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Import utilities
from src.tools.utils.chartink_scraper import fetch_chartink_data
from src.tools.utils.technical_analysis_utils import calculate_trend, calculate_chart_patterns, calculate_indicators
from src.tools.utils.filtering_utils import filter_stocks
from src.tools.utils.email_utils import make_html_template, send_mail

load_dotenv()

# --- State Definition ---
class PredictionState(TypedDict):
    status: str
    tickers: List[str]
    raw_data: List[Dict]
    analyzed_data: List[Dict]
    filtered_data: List[Dict]
    report_html: str
    pdf_path: str
    email_recipient: str

# --- Nodes ---

async def scrape_node(state: PredictionState) -> PredictionState:
    print("🔵 [Workflow: Scrape] Starting...")
    url = os.getenv("CHARTINK_URL", "https://chartink.com/screener/macd-bullish-crossover")
    
    try:
        headers, rows = await fetch_chartink_data(url, total_pages=2)
        
        tickers = []
        raw_data = []
        
        # Try to find column indices
        symbol_idx = 2 # Default fallback
        price_idx = 6  # Default fallback
        
        if "Symbol" in headers:
            symbol_idx = headers.index("Symbol")
        if "Price" in headers:
            price_idx = headers.index("Price")
            
        for row in rows:
            if len(row) > max(symbol_idx, price_idx):
                t = row[symbol_idx]
                p = row[price_idx]
                tickers.append(t)
                raw_data.append({"ticker": t, "price": p})
                
        print(f"✅ [Workflow: Scrape] Scraped {len(tickers)} stocks.")
        return {"tickers": tickers, "raw_data": raw_data, "status": "scraped"}
        
    except Exception as e:
        print(f"❌ [Workflow: Scrape] Error: {e}")
        return {"tickers": [], "raw_data": [], "status": "failed_scrape"}

async def analyze_node(state: PredictionState) -> PredictionState:
    print(f"🔵 [Workflow: Analyze] Analyzing {len(state['tickers'])} stocks...")
    
    tickers = state["tickers"]
    raw_data = state["raw_data"]
    analyzed_data = []
    
    end_date = date.today()
    start_date = end_date - relativedelta(months=int(os.getenv("ANALYSIS_MONTHS", "6")))
    
    try:
        for i, ticker in enumerate(tickers):
            print(f"   🔎 [{i+1}/{len(tickers)}] Analyzing {ticker}...")
            
            # 1. Trend
            trend = calculate_trend(ticker, start_date, end_date)
            
            # 2. Patterns
            patterns = calculate_chart_patterns(ticker, start_date, end_date)
            
            # 3. Indicators
            indicators = calculate_indicators(ticker, start_date, end_date)
            
            # Get raw price
            raw_item = next((x for x in raw_data if x["ticker"] == ticker), {})
            price = raw_item.get("price", "0")
            
            analyzed_data.append({
                "ticker": ticker,
                "price": price,
                "trend": trend,
                "patterns": patterns,
                "indicators": indicators
            })
            
        print("✅ [Workflow: Analyze] Analysis complete.")
        return {"analyzed_data": analyzed_data, "status": "analyzed"}
        
    except Exception as e:
        print(f"❌ [Workflow: Analyze] Error: {e}")
        return {"analyzed_data": [], "status": "failed_analyze"}

async def filter_node(state: PredictionState) -> PredictionState:
    print("🔵 [Workflow: Filter] Filtering stocks...")
    try:
        filtered = filter_stocks(state["analyzed_data"])
        return {"filtered_data": filtered, "status": "filtered"}
    except Exception as e:
        print(f"❌ [Workflow: Filter] Error: {e}")
        return {"filtered_data": [], "status": "failed_filter"}

async def report_node(state: PredictionState) -> PredictionState:
    print("🔵 [Workflow: Report] Generating artifacts...")
    
    filtered_data = state["filtered_data"]
    
    # 1. HTML
    html_content = make_html_template(filtered_data, title=f"Best Predictions ({date.today()})")
    
    # 2. PDF
    pdf_filename = f"prediction_report_{date.today()}.pdf"
    pdf_path = os.path.abspath(pdf_filename)
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_content(html_content)
            await page.pdf(path=pdf_path)
            await browser.close()
        print(f"✅ [Workflow: Report] PDF saved to {pdf_path}")
    except Exception as e:
        print(f"❌ [Workflow: Report] PDF Generation failed: {e}")
        pdf_path = None
        
    return {"report_html": html_content, "pdf_path": pdf_path, "status": "reported"}

async def email_node(state: PredictionState) -> PredictionState:
    print("🔵 [Workflow: Email] Sending results...")
    recipient = state.get("email_recipient")
    if not recipient:
        print("⚠️ [Workflow: Email] No recipient provided.")
        return {"status": "skipped_email"}
        
    subject = f"Market Predictions Report - {date.today()}"
    body = (
        f"<h2>Weekly Market Predictions</h2>"
        f"<p>Found {len(state['filtered_data'])} stocks matching your criteria (Bullish Trend, Price < limit).</p>"
        f"<p>Please find the detailed report attached.</p>"
    )
    # Check if we have data
    if not state["filtered_data"]:
        body = "<p>No stocks matched the filtering criteria today.</p>"
    
    success = send_mail(recipient, subject, body, state["pdf_path"])
    
    status = "completed" if success else "failed_email"
    return {"status": status}

# --- Graph ---
def create_prediction_workflow():
    workflow = StateGraph(PredictionState)
    
    workflow.add_node("scrape", scrape_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("filter", filter_node)
    workflow.add_node("report", report_node)
    workflow.add_node("email", email_node)
    
    workflow.set_entry_point("scrape")
    
    workflow.add_edge("scrape", "analyze")
    workflow.add_edge("analyze", "filter")
    workflow.add_edge("filter", "report")
    workflow.add_edge("report", "email")
    workflow.add_edge("email", END)
    
    return workflow.compile()

async def run_workflow(recipient: str):
    app = create_prediction_workflow()
    init_state = PredictionState(
        status="init",
        tickers=[], raw_data=[], analyzed_data=[], filtered_data=[],
        report_html="", pdf_path="",
        email_recipient=recipient
    )
    final = await app.ainvoke(init_state)
    return final
