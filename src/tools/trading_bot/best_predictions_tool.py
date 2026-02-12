from ..base import DynamicTool, ToolParam
import asyncio
import re
from src.core import multi_processor
from src.workflows.prediction_worker import prediction_worker_wrapper

def makeTool(router):
    def func(unique_id):
        async def best_predictions(
            email: str = "knpatel0707@gmail.com",
            filter_max_price: str = "3000.0",
            filter_required_trend: str = "1",
            analysis_months: str = "6"
        ):
            """
            Starts the 'Best Predictions' analysis workflow in a BACKGROUND PROCESS.
            Logic:
            1. Scrapes Chartink.
            2. Runs parallel analysis (Trend, Patterns) in the worker.
            3. Generates Report & Emails it.
            Check the Server Terminal for progress logs.
            """
            print(f"🔄 [Tool] Triggering Best Predictions for {email}...")

            # --- Input Sanitization & Defaults ---
            # 1. Price: Remove nondigits, default to 5000.0 if failed
            try:
                p_text = str(filter_max_price)
                if not p_text or p_text.lower() == "none":
                    filter_max_price = "5000.0"
                else:
                    # Extract number 3000 from "3000.0" or "Rs 3000"
                    match = re.search(r"(\d+(\.\d+)?)", p_text)
                    filter_max_price = match.group(1) if match else "5000.0"
            except:
                filter_max_price = "5000.0"

            # 2. Trend: Bullish/Up -> 1, Bearish/Down -> 0. Default 1.
            try:
                t_text = str(filter_required_trend).lower()
                if "bull" in t_text or "up" in t_text:
                    filter_required_trend = "1"
                elif "bear" in t_text or "down" in t_text:
                    filter_required_trend = "0"
                else:
                    # Try to find an integer
                    match = re.search(r"(\d+)", t_text)
                    filter_required_trend = match.group(1) if match else "1"
            except:
                 filter_required_trend = "1"

            # 3. Months: Default 6. If "bullish" was passed here by mistake, it falls back to 6.
            try:
                m_text = str(analysis_months).lower()
                if "bull" in m_text: # User might have swapped trend/months
                     analysis_months = "6"
                else:
                    match = re.search(r"(\d+)", m_text)
                    analysis_months = match.group(1) if match else "6"
            except:
                analysis_months = "6"

            print(f"   [Sanitized Config] Price: {filter_max_price}, Trend: {filter_required_trend}, Months: {analysis_months}")
            
            # Access the process_pool from the module
            if multi_processor.process_pool is None:
                return "❌ Error: Process Pool not initialized. Is the server running?"

            loop = asyncio.get_running_loop()
            
            # Fire and forget 
            future = loop.run_in_executor(
                multi_processor.process_pool,
                prediction_worker_wrapper,
                email,
                filter_max_price,
                filter_required_trend,
                analysis_months
            )
            
            def on_complete(fut):
                try:
                    res = fut.result()
                    print(f"✅ Background task completed: {res}")
                except Exception as e:
                    print(f"❌ Background task failed: {e}")
            
            future.add_done_callback(on_complete)

            return (
                f"✅ Analysis started successfully in background process.\n"
                f"   - Target: {email}\n"
                f"   - Filters: Price<{filter_max_price}, Trend>={filter_required_trend} (1=Bullish, 0=Bearish)\n"
                f"   - History: {analysis_months} months\n"
                f"   - Logs: Check your terminal/console for '[Process N]...' outputs.\n"
                f"   - You will receive an email in ~10 minutes."
            )

        return DynamicTool(
            name="best_predictions",
            description="Run advanced analysis (Trend, Pattern, Filter) on potential bullish stocks and email a report.",
            triggers=["find best predictions", "analyze bullish stocks", "send prediction report"],
            function=best_predictions,
            parameters=[
                ToolParam(name="email", type="string", required=False, description="Email address to receive the report."),
                ToolParam(name="filter_max_price", type="string", required=False, description="Maximum stock price filter."),
                ToolParam(name="filter_required_trend", type="string", required=False, description="Required trend intensity (e.g., '1' for Bullish, '0' for Bearish)."),
                ToolParam(name="analysis_months", type="string", required=False, description="Months of historical data to analyze.")
            ],
            endpoint="/best-predictions",
            router=router
        )
    return func
