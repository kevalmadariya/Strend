
from src.agent.AgentConfig import AgentConfig
from src.tools.trading_bot import __all__ as trading_tools


def make_trading_bot(unique_id: str = None) -> AgentConfig:
    """Factory for the Trading Bot"""
    tools = trading_tools
    base_prompt = """
    You are a Trading Assistant. 
    1. Analyze market trends.
    2. Execute orders only when parameters are complete.
    """
    print(tools)
    
    return AgentConfig(
        name="trading_bot",
        base_prompt=base_prompt.strip(),
        tools=tools
    )
