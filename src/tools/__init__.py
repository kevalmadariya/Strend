import importlib
from typing import List, Callable
from .base import DynamicTool

def load_tools_for_agent(agent_name: str, unique_id: str) -> List[DynamicTool]:
    """
    1. Looks for src.tools.{agent_name}.__init__.py
    2. Imports the module.
    3. Iterates over '__all__' (which contains factory functions).
    4. Calls each factory with 'unique_id' to generate the DynamicTool.
    """
    module_path = f"src.tools.{agent_name}"
    
    try:
        # Dynamically import the module
        # This triggers the code in __init__.py (like router registration)
        module = importlib.import_module(module_path)
        
        # Check if the module exports __all__
        if not hasattr(module, "__all__"):
            print(f"⚠️  Warning: Module '{module_path}' has no '__all__' list.")
            return []
            
        # Extract the list of factory functions
        # Type hint: List[Callable[[str], DynamicTool]]
        tool_factories = module.__all__
        
        # Execute the factories to get the actual Tool instances
        tools = [factory(unique_id) for factory in tool_factories]
        
        print(f"✅ Loaded {len(tools)} tools from {module_path}")
        return tools

    except ImportError:
        print(f"❌ Error: Could not find tool module: '{module_path}'")
        return []
    except Exception as e:
        print(f"❌ Error loading tools for '{agent_name}': {e}")
        return []