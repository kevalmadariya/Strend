from fastapi import APIRouter
from typing import List, Callable
from src.tools.base import DynamicTool

# Import the 'makeTool' factories from each tool file
from .make_temp_database import makeTool as make_temp_database_tool
from .make_sql_query import makeTool as make_sql_query_tool
from .get_schema import makeTool as get_schema_tool
from .execute_query import makeTool as execute_query_tool
from .add_computed_column import makeTool as add_computed_column_tool
from .store_llm_result import makeTool as store_llm_result_tool

router = APIRouter(prefix='/excel-tools')

# The loader expects: List[Callable[[str], DynamicTool]]
# Each factory returns a func(unique_id) -> DynamicTool
__all__: List[Callable[[str], DynamicTool]] = [
    make_temp_database_tool(router=router),
    make_sql_query_tool(router=router),
    get_schema_tool(router=router),
    execute_query_tool(router=router),
    add_computed_column_tool(router=router),
    store_llm_result_tool(router=router),
]
