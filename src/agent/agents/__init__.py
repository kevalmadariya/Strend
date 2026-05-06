from typing import Dict, Callable, Optional
from src.agent.AgentConfig import AgentConfig
from src.agent.agents.trading_agent import make_trading_bot
from src.agent.agents.excel_agent import make_excel_agent

# The Registry
AGENTS_REGISTRY: Dict[str, Callable[[Optional[str]], AgentConfig]] = {
    "trading_bot": make_trading_bot,
    "excel_agent": make_excel_agent,
}

def get_agent_config(agent_name: str, unique_id: str = None) -> AgentConfig:
    """Helper to fetch config based on name"""
    if agent_name not in AGENTS_REGISTRY:
        raise ValueError(f"Agent '{agent_name}' not found in registry. Available: {list(AGENTS_REGISTRY.keys())}")
    
    return AGENTS_REGISTRY[agent_name](unique_id)