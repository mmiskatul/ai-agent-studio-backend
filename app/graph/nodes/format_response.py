from app.graph.state import ChatGraphState
from app.models.base import now_utc


def format_response_node():
    async def node(state: ChatGraphState) -> ChatGraphState:
        agent = state["selected_agent"]
        response_json = {
            "session_id": state["session_id"],
            "chat_id": state["chat_id"],
            "agent": {
                "id": agent.id or "",
                "name": agent.name,
                "role": agent.role,
            },
            "system_summary": state.get("system_summary", ""),
            "response": state.get("final_response", ""),
            "routing_reason": state.get("routing_reason", ""),
            "memory_updated": state.get("memory_updated", False),
            "metadata": {
                "model": agent.model or agent.llm_engine,
                "timestamp": now_utc().isoformat(),
            },
        }
        return {**state, "response_json": response_json}

    return node
