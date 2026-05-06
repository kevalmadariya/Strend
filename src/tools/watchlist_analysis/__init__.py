from .watchlist_stocks_tool import makeTool as watchlist_stocks_tool
from .watchlist_tool import makeTool as watchlist_tool
from typing import List, Callable
from src.tools.base import DynamicTool
from fastapi import APIRouter
router = APIRouter(prefix='/watchlist_agent')

__all__:List[Callable[[str], DynamicTool]] = [
    watchlist_stocks_tool(router=router),
    watchlist_tool(router=router)
]