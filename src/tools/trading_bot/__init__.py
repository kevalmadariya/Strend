from fastapi import APIRouter
from typing import List, Callable
from src.tools.base import DynamicTool

# Import the 'makeTool' functions from your specific tool files
from .create_market_status import makeTool as create_market_status_tool
from .get_stock_details import makeTool as get_stock_details_tool
from .get_fundamentals_tool import makeTool as get_fundamentals_tool
from .analyze_stock_fundamentals import makeTool as analyze_stock_fundamentals_tool
from .extract_stocks_by_techincal_analysis import makeTool as extract_stocks_by_techincal_analysis_tool
from .get_trend_and_chart_patter import makeTool as get_trend_charts_patterns_tool
from .get_rsi_macd_adx import makeTool as get_rsi_macd_adx_tool
from .capture_candlestick_chart import makeTool as capture_candlestick_chart_tool
# from .other_tool import makeTool as ...

router = APIRouter(prefix='/planning-tools')

# The loader expects this exact structure:
# A list of functions that accept (unique_id) and return DynamicTool
__all__: List[Callable[[str], DynamicTool]] = [
    get_stock_details_tool(router=router),  # This returns the func(id) wrapper
    create_market_status_tool(router=router), # This returns the func(id) wrapper
    get_fundamentals_tool(router=router),    # This returns the func(id) wrapper
    analyze_stock_fundamentals_tool(router=router), # This returns the func(id) wrapper
    extract_stocks_by_techincal_analysis_tool(router=router), # This returns the func(id) wrapper
    get_trend_charts_patterns_tool(router=router), # This returns the func(id) wrapper
    get_rsi_macd_adx_tool(router=router), # This returns the func(id) wrapper
    capture_candlestick_chart_tool(router=router), # This returns the func(id) wrapper
]