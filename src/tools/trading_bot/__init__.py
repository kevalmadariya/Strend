from fastapi import APIRouter
from typing import List, Callable
from src.tools.base import DynamicTool

# Import the 'makeTool' functions from your specific tool files
from .create_market_status import makeTool as create_market_status_tool
from .get_stock_details import makeTool as get_stock_details_tool
from .get_fundamentals_tool import makeTool as get_fundamentals_tool
from .analyze_stock_fundamentals import makeTool as analyze_stock_fundamentals_tool
from .extract_stocks_by_techincal_analysis import makeTool as extract_stocks_by_techincal_analysis_tool
from .get_technicals_tool import makeTool as get_technicals_tool
from .capture_candlestick_chart import makeTool as capture_candlestick_chart_tool
from .watchlist_tool import makeTool as watchlist_tool
from .watchlist_stocks_tool import makeTool as watchlist_stocks_tool
from .news_analysis_tool import makeTool as news_analysis_tool
from .recent_news_tool import makeTool as recent_news_tool
from .compare_nifty_tool import makeTool as compare_nifty_tool
from .get_stocks_all_details import makeTool as get_stocks_all_details_tool
from .add_computed_column import makeTool as add_computed_column_tool
from .execute_query import makeTool as execute_query_tool
from .make_sql_query import makeTool as make_sql_query_tool
from .get_schema import makeTool as get_schema_tool
from .make_temp_database import makeTool as make_temp_database_tool
router = APIRouter(prefix='/planning-tools')

# The loader expects this exact structure:
# A list of functions that accept (unique_id) and return DynamicTool
__all__: List[Callable[[str], DynamicTool]] = [
    get_stock_details_tool(router=router),  # This returns the func(id) wrapper
    create_market_status_tool(router=router), # This returns the func(id) wrapper
    get_fundamentals_tool(router=router),    # This returns the func(id) wrapper
    analyze_stock_fundamentals_tool(router=router), # This returns the func(id) wrapper
    extract_stocks_by_techincal_analysis_tool(router=router), # This returns the func(id) wrapper
    get_technicals_tool(router=router), # This returns the func(id) wrapper
    capture_candlestick_chart_tool(router=router), # This returns the func(id) wrapper
    watchlist_tool(router=router), 
    watchlist_stocks_tool(router=router),
    news_analysis_tool(router=router),
    recent_news_tool(router=router),
    compare_nifty_tool(router=router),
    get_stocks_all_details_tool(router=router),
    add_computed_column_tool(router=router),
    make_sql_query_tool(router=router),
    execute_query_tool(router=router),
    get_schema_tool(router=router),
    make_temp_database_tool(router=router),
]