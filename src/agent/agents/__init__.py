from typing import Dict, Callable, Optional
from src.agent.AgentConfig import AgentConfig
from src.agent.agents.trading_agent import make_trading_bot
from src.agent.agents.fundamental_analysis_agent import make_fundamental_analysis_agent
from src.agent.agents.news_agent import make_news_agent
from src.agent.agents.technical_analysis_agent import make_technical_analysis_agent
from src.agent.agents.watchlist_agent import make_watchlist_agent
# The Registry
AGENTS_REGISTRY: Dict[str, Callable[[Optional[str]], AgentConfig]] = {
    "trading_bot": make_trading_bot,
    "fundamental_analysis_agent": make_fundamental_analysis_agent,
    "news_agent": make_news_agent,
    "technical_analysis_agent": make_technical_analysis_agent,
    "watchlist_agent": make_watchlist_agent,
}

def get_agent_config(agent_name: str, unique_id: str = None) -> AgentConfig:
    """Helper to fetch config based on name"""
    if agent_name not in AGENTS_REGISTRY:
        raise ValueError(f"Agent '{agent_name}' not found in registry. Available: {list(AGENTS_REGISTRY.keys())}")
    
    return AGENTS_REGISTRY[agent_name](unique_id)