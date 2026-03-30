from typing import Dict
from src.agent.bot import PlanningAgent  # adjust import path

# Keep one bot instance per conversation
# key = (user_id, agent_name, conversation_id)
_AGENT_SESSIONS: Dict[str, PlanningAgent] = {}


def _make_session_key(user_id: int, agent_name: str, conversation_id: int) -> str:
    return f"{user_id}:{agent_name}:{conversation_id}"


async def invoke_agent(
    user_id: int,
    agent_name: str,
    conversation_id: int,
    user_message: str
) -> str:
    """
    Invoke agent for a given websocket message.
    Maintains conversation state.
    """
    session_key = _make_session_key(user_id, agent_name, conversation_id)

    if session_key not in _AGENT_SESSIONS:
        _AGENT_SESSIONS[session_key] = PlanningAgent(agent_name=agent_name, unique_id=conversation_id)

    bot = _AGENT_SESSIONS[session_key]
    async for chunk in bot.run(user_message):
        yield chunk


def cleanup_agent_session(user_id: int, agent_name: str, conversation_id: int):
    """Cleanup memory when websocket disconnects"""
    session_key = _make_session_key(user_id, agent_name, conversation_id)
    _AGENT_SESSIONS.pop(session_key, None)
