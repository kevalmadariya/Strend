from .news_analysis_tool import makeTool as news_analysis_tool
from .recent_news_tool import makeTool as recent_news_tool
from typing import List, Callable
from src.tools.base import DynamicTool

from fastapi import APIRouter
router = APIRouter(prefix='/news_agent')


__all__:List[Callable[[str], DynamicTool]] = [
    news_analysis_tool(router=router), 
    recent_news_tool(router=router)
]

