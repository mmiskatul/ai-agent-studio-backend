from app.graph.state import ChatGraphState
from app.services.memory_service import MemoryService


def save_memory_node(*, memory_service: MemoryService):
    async def node(state: ChatGraphState) -> ChatGraphState:
        agent = state["selected_agent"]
        memory = await memory_service.update(
            user_id=state["user_id"],
            session_id=state["session_id"],
            chat_id=state["chat_id"],
            agent_id=agent.id or "",
            previous_memory=state.get("memory"),
            user_message=state["user_message"],
            assistant_response=state["final_response"],
        )
        return {
            **state,
            "memory": memory,
            "memory_summary": memory.summary,
            "memory_facts": memory.facts,
            "memory_updated": True,
        }

    return node
