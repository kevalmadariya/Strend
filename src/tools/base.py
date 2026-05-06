from pydantic import BaseModel
from typing import List, Union, Callable, Generator, AsyncGenerator, Awaitable, Any, Dict, Optional

class ToolParam(BaseModel):
    name: str
    type: str
    description: str
    enums: List[str] = []
    required: bool = False
    items: Optional[Dict[str, str]] = None

    def to_property(self):
        prop = {
            "type": self.type,
            "description": self.description,
        }
        if self.enums:
            prop["enum"] = self.enums
        if self.items:
            prop["items"] = self.items
        return prop

class DynamicTool(BaseModel):
    name: str
    description: str
    #optional
    triggers: List[str] = []
    parameters: List[ToolParam]
    # Supports Sync/Async Functions and Generators
    function: Union[
        Callable[..., str],
        Callable[..., Awaitable[str]],
        Callable[..., Generator[Any, None, str]],
        Callable[..., AsyncGenerator[str, None]],
    ]
    endpoint: str = None
    router: Any = None # Stores the APIRouter reference if needed

    class Config:
        arbitrary_types_allowed = True

    def to_openai_schema(self):
        """Converts internal tool definition to OpenAI/LLM function schema"""
        properties = {}
        required_fields = []

        for param in self.parameters:
            properties[param.name] = param.to_property()
            if param.required:
                required_fields.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_fields,
                },
            },
        }