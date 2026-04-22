from app.graph.state import ChatGraphState
from app.services.router_service import RouterService


def route_request_node(*, router_service: RouterService):
    async def node(state: ChatGraphState) -> ChatGraphState:
        selected_agent, routing_reason = await router_service.route(
            user_message=state["user_message"],
            agents=state.get("available_agents", []),
            requested_agent_id=state.get("requested_agent_id"),
        )
        return {
            **state,
            "selected_agent": selected_agent,
            "routing_reason": routing_reason,
        }

    return node
