from app.graph.state import ChatGraphState
from app.models.message import MessageRecord
from app.repositories.message_repository import MessageRepository


def save_messages_node(*, messages: MessageRepository):
    async def node(state: ChatGraphState) -> ChatGraphState:
        agent = state["selected_agent"]
        user_message = await messages.create_message(
            MessageRecord(
                user_id=state["user_id"],
                session_id=state["session_id"],
                chat_id=state["chat_id"],
                agent_id=agent.id,
                role="user",
                content=state["user_message"],
                metadata={"routing_reason": state.get("routing_reason", "")},
            )
        )
        assistant_message = await messages.create_message(
            MessageRecord(
                user_id=state["user_id"],
                session_id=state["session_id"],
                chat_id=state["chat_id"],
                agent_id=agent.id,
                role="assistant",
                content=state["final_response"],
                metadata={
                    "system_summary": state.get("system_summary", ""),
                    "markdown": state.get("markdown_response", state.get("final_response", "")),
                    "render_mode": state.get("response_render_mode", "plain"),
                },
            )
        )
        recent = [*state.get("messages", []), user_message, assistant_message]
        return {**state, "messages": recent}

    return node
