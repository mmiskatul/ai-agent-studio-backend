from typing import Any, TypedDict

from app.models.agent import AgentDocument
from app.models.chat import ChatDocument
from app.models.memory import MemoryRecord
from app.models.message import MessageRecord


class ChatGraphState(TypedDict, total=False):
    user_id: str
    session_id: str
    chat_id: str
    requested_agent_id: str | None
    user_message: str
    chat: ChatDocument | None
    messages: list[MessageRecord]
    available_agents: list[AgentDocument]
    selected_agent: AgentDocument
    routing_reason: str
    memory: MemoryRecord | None
    memory_summary: str
    memory_facts: list[str]
    tool_results: dict[str, Any]
    final_response: str
    system_summary: str
    memory_updated: bool
    response_json: dict[str, Any]
