from uuid import uuid4

from app.graph.state import ChatGraphState
from app.repositories.chat_repository import ChatRepository
from app.repositories.message_repository import MessageRepository
from app.services.memory_service import MemoryService


def load_context_node(
    *,
    chats: ChatRepository,
    messages: MessageRepository,
    memory_service: MemoryService,
):
    async def node(state: ChatGraphState) -> ChatGraphState:
        session_id = state.get("session_id") or f"session_{uuid4().hex}"
        chat_id = state.get("chat_id")
        user_id = state["user_id"]
        chat = await chats.get_by_id_for_user(user_id, chat_id) if chat_id else None
        if chat is None:
            chat = await chats.get_latest_for_session(user_id, session_id)
        memory = await memory_service.load(user_id, session_id)
        recent_messages = (
            await messages.list_by_chat(user_id, chat.id or "", limit=24)
            if chat is not None and chat.id
            else await messages.list_by_session(user_id, session_id, limit=24)
        )
        return {
            **state,
            "session_id": session_id,
            "chat_id": chat.id if chat and chat.id else (chat_id or ""),
            "chat": chat,
            "memory": memory,
            "memory_summary": memory.summary if memory else "",
            "memory_facts": memory.facts if memory else [],
            "messages": recent_messages,
            "tool_results": {},
        }

    return node
