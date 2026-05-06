from .get_fundamentals_tool import makeTool as get_fundamentals_tool
from .analyze_stock_fundamentals import makeTool as analyze_stock_fundamentals_tool

from typing import List, Callable
from src.tools.base import DynamicTool
from fastapi import APIRouter
router = APIRouter(prefix='/fundamental_agent')
    
__all__: List[Callable[[str], DynamicTool]] = [
    get_fundamentals_tool(router=router),
    analyze_stock_fundamentals_tool(router=router),
]