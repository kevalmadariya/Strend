
from src.agent.AgentConfig import AgentConfig
from src.tools.trading_bot import __all__ as trading_tools


def make_trading_bot(unique_id: str = None) -> AgentConfig:
    """Factory for the Trading Bot"""
    tools = trading_tools
    base_prompt = """
    You are a Trading Assistant.
    You can access all tools. 
    give answer according to user ask.
    give anser to the point and make it simple and small.
    """
    print(tools)
    
    return AgentConfig(
        name="trading_bot",
        base_prompt=base_prompt.strip(),
        tools=tools
    )
