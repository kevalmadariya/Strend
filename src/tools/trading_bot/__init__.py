from fastapi import APIRouter
from typing import List, Callable
from src.tools.base import DynamicTool

# Import the 'makeTool' functions from your specific tool files
from .create_market_status import makeTool as create_market_status_tool
# from .other_tool import makeTool as ...

router = APIRouter(prefix='/planning-tools')

# The loader expects this exact structure:
# A list of functions that accept (unique_id) and return DynamicTool
__all__: List[Callable[[str], DynamicTool]] = [
    create_market_status_tool(router=router), # This returns the func(id) wrapper
]