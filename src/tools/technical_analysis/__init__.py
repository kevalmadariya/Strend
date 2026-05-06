from .extract_stocks_by_techincal_analysis import makeTool as extract_stocks_by_techincal_analysis_tool
from .get_stocks_all_details import makeTool as get_stocks_all_details_tool
from .compare_nifty_tool import makeTool as compare_nifty_tool
from typing import List, Callable
from src.tools.base import DynamicTool

from fastapi import APIRouter
router = APIRouter(prefix='/technical_analysis_agent')


__all__:List[Callable[[str], DynamicTool]] = [
    compare_nifty_tool(router=router),
    extract_stocks_by_techincal_analysis_tool(router=router),
    get_stocks_all_details_tool(router=router)
]