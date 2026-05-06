import json
import yfinance as yf
import pandas as pd
from typing import List, Optional
from ..base import DynamicTool, ToolParam

def makeTool(router):
    def func(unique_id):
        async def compare_nifty(tickers: Optional[List[str]] = None, durations: Optional[List[str]] = None, text: Optional[str] = None):
            import re
            
            all_tickers = set(tickers) if tickers else set()
            
            # Extract tickers from text if provided
            if text:
                # Regex to find potential tickers: UPPERCASE words with length >= 3
                found_in_text = re.findall(r'\b[A-Z0-9]{3,}\b', text)
                for t in found_in_text:
                    if t not in ["AND", "FOR", "THE", "WITH", "ARE", "NOT", "YES", "CAN", "YOU", "BUT"]:
                        all_tickers.add(t)

            if not all_tickers:
                 yield "⚠️ No tickers provided. Please specify tickers in the list or mention them in the text.\n"
                 return

            if not durations:
                durations = ['1mo', '3mo', '6mo', '9mo', '12mo']
            
            nifty_cache = {} # duration -> nifty_pct_series
            results_summary = {} # ticker -> list of summary strings
            
            combined_results = {}

            for ticker in all_tickers:
                # Normalize ticker if needed (default to .NS for Indian stocks if no suffix)
                # But we respect user input first. If it fails, maybe retry with .NS?
                # The prompt implies Indian context (Nifty), so likely Indian stocks.
                # If the user provides "RELIANCE", yfinance needs "RELIANCE.NS".
                # We'll use a simple heuristic: if no dot, append .NS.
                ticker_symbol = ticker if "." in ticker else f"{ticker}.NS"
                
                ticker_summaries = []
                ticker_details = {}

                for duration in durations:
                    # 1. Get Nifty Data (Cached)
                    if duration not in nifty_cache:
                        yield f"⏳ Downloading Nifty data for {duration}...\n"
                        try:
                            # Using ^NSEI for Nifty 50
                            nifty_raw = yf.download(tickers='^NSEI', period=duration, interval='1d', auto_adjust=True, progress=False)
                            
                            if nifty_raw.empty:
                                yield f"⚠️ Could not fetch Nifty data for {duration}\n"
                                nifty_cache[duration] = None
                                continue
                            
                            # Handle MultiIndex columns if present (yfinance > 0.2.0)
                            if isinstance(nifty_raw.columns, pd.MultiIndex):
                                nifty_raw.columns = nifty_raw.columns.get_level_values(0)
                            
                            # Calculate percentage change
                            nifty_pct = nifty_raw["Close"].pct_change() * 100
                            nifty_cache[duration] = nifty_pct
                        except Exception as e:
                            yield f"❌ Error fetching Nifty for {duration}: {e}\n"
                            nifty_cache[duration] = None
                            continue

                    nifty_pct = nifty_cache[duration]
                    if nifty_pct is None:
                        continue

                    # 2. Get Stock Data
                    # We don't yield here to avoid spamming unless error
                    try:
                        stock = yf.download(tickers=ticker_symbol, period=duration, interval='1d', auto_adjust=True, progress=False)
                        if stock.empty:
                            yield f"⚠️ No data for {ticker_symbol} in {duration}\n"
                            continue
                        
                        if isinstance(stock.columns, pd.MultiIndex):
                            stock.columns = stock.columns.get_level_values(0)
                        
                        # 3. Build Compare DataFrame
                        compare_df = stock.copy()
                        # Keep only Close
                        compare_df = compare_df[['Close']] 
                        
                        compare_df["prev_Close"] = compare_df["Close"].shift(1)
                        compare_df["percentage_change"] = (compare_df["Close"] - compare_df["prev_Close"]) / compare_df["prev_Close"] * 100
                        compare_df["nifty"] = nifty_pct
                        
                        # Drop NaN (first row usually)
                        compare_df.dropna(subset=["percentage_change", "nifty"], inplace=True)

                        # 4. Logic
                        compare_df["is_same"] = (
                            ((compare_df["percentage_change"] > 0) & (compare_df["nifty"] > 0)) | 
                            ((compare_df["percentage_change"] < 0) & (compare_df["nifty"] < 0))
                        )
                        compare_df["difference"] = compare_df["percentage_change"] - compare_df["nifty"]

                        # 5. Summary
                        total_matches = compare_df["is_same"].sum()
                        total_days = len(compare_df)
                        match_pct = (total_matches * 100 / total_days) if total_days > 0 else 0
                        
                        summary_str = f"total_matches : {total_matches} out of {total_days} with %matching {match_pct:.2f} in duration of {duration}"
                        ticker_summaries.append(summary_str)
                        
                        # Store Detail
                        # Convert DataFrame to dict (JSON compatible)
                        # Index is Timestamp, convert to string
                        compare_df.index = compare_df.index.astype(str)
                        ticker_details[duration] = json.loads(compare_df.to_json(orient="index"))

                    except Exception as e:
                        yield f"❌ Error processing {ticker_symbol} for {duration}: {e}\n"

                # Output summary for this ticker
                if ticker_summaries:
                    summary_block = f"\n🔹 Summary for {ticker_symbol}:\n" + "\n".join(ticker_summaries) + "\n"
                    yield summary_block
                else:
                    yield f"\n⚠️ No data processed for {ticker_symbol}\n"
                
                combined_results[ticker_symbol] = {
                    "summaries": ticker_summaries,
                    # "details": ticker_details
                }
                # yield json.dumps({"status": "success", "data": combined_results})

            # yield json.dumps({"status": "success", "data": combined_results})

        return DynamicTool(
            name="compare_nifty",
            description="Compare stock performance with Nifty 50 across multiple durations (1mo, 3mo, 6mo, 9mo, 12mo). Stats include matching direction days.",
            triggers=["compare nifty", "stock vs nifty", "correlation with nifty"],
            function=compare_nifty,
            parameters=[
                ToolParam(name="tickers", type="array", required=False, description="List of stock tickers (e.g. RELIANCE, TCS)"),
                ToolParam(name="text", type="string", required=False, description="Text containing stock tickers (e.g. 'Compare RELIANCE and TCS')"),
                ToolParam(name="durations", type="array", required=False, description="List of durations (e.g. 1mo, 3mo). Default: 1mo, 3mo, 6mo, 9mo, 12mo")
            ],
            endpoint="/compare-nifty",
            router=router
        )
    return func
