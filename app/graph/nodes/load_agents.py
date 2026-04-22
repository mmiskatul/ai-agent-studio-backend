from app.graph.state import ChatGraphState
from app.repositories.agent_repository import AgentRepository


def load_agents_node(*, agents: AgentRepository):
    async def node(state: ChatGraphState) -> ChatGraphState:
        available_agents = await agents.list_active_by_user(state["user_id"])
        return {**state, "available_agents": available_agents}

    return node
