import asyncio
from ..base import DynamicTool
from ..base import ToolParam
from src.tools.utils.pulse_scraper import extract_pulse_news
import json

def makeTool(router):
    """
    Factory function for the Recent News Tool (Pulse by Zerodha).
    """
    def func(unique_id):
        
        async def fetch_market_news(domain: str = None):
            """
            Fetches recent market news from Pulse. Optional 'domain' to filter (e.g. 'ipo', 'nifty').
            """
            yield f"🌍Fetching recent market news...\n"
            if domain:
                yield f"🔎 Filter: {domain}"
            
            try:
                # Call the scraper
                news_data = await extract_pulse_news(domain)
                
                # Check for error
                if "error" in news_data:
                    yield f"❌ Error fetching news: {news_data['error']} \n"
                    return

                # Calculate total items
                total_items = sum(len(items) for items in news_data.values())
                yield f"✅ Successfully fetched {total_items} news items.\n"
                
                # Yield the final JSON result
                yield json.dumps({
                    "status" : "success",
                    "data" : news_data
                })

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"❌ Error in recent_news_tool: {str(e)}"

        return DynamicTool(
            name="recent_news_tool",
            description="Get genral recent market news related to nifty, ipo, etc.",
            triggers=["Get recent news", "Check market news", "Pulse news"],
            function=fetch_market_news,
            parameters=[
                ToolParam(
                    name="domain", 
                    type="string", 
                    description="Optional category to filter (e.g. 'ipo', 'nifty', 'general'). returns all if omitted.", 
                    required=False
                )
            ],
            endpoint="/recent-news",
            router=router
        )

    return func
