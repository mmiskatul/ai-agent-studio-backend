from app.graph.state import ChatGraphState
from app.models.chat import ChatDocument
from app.repositories.chat_repository import ChatRepository
from app.services.llm_service import LLMService


def run_selected_agent_node(*, chats: ChatRepository, llm_service: LLMService):
    async def node(state: ChatGraphState) -> ChatGraphState:
        agent = state["selected_agent"]
        chat = state.get("chat")
        if chat is None or not chat.id:
            chat = await chats.create(
                ChatDocument(
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    agent_id=agent.id or "",
                    current_agent_id=agent.id or "",
                    agent_name=agent.name,
                    title=_build_chat_title(state["user_message"]),
                )
            )
        elif chat.agent_id != (agent.id or ""):
            updated_chat = await chats.update_chat_agent(
                chat.id or "",
                agent_id=agent.id or "",
                agent_name=agent.name,
            )
            if updated_chat is not None:
                chat = updated_chat

        final_response = await llm_service.generate_agent_response(
            agent=agent,
            user_message=state["user_message"],
            memory_summary=state.get("memory_summary", ""),
            memory_facts=state.get("memory_facts", []),
            messages=state.get("messages", []),
        )
        return {
            **state,
            "chat": chat,
            "chat_id": chat.id or "",
            "final_response": final_response,
            "system_summary": (
                f"{agent.name} handled the request using session context and "
                "available memory."
            ),
        }

    return node


def _build_chat_title(content: str) -> str:
    title = " ".join(content.strip().split())
    return title if len(title) <= 80 else f"{title[:77].rstrip()}..."
