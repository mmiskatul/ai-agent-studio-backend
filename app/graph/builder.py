from langgraph.graph import END, StateGraph

from app.graph.nodes.format_response import format_response_node
from app.graph.nodes.load_agents import load_agents_node
from app.graph.nodes.load_context import load_context_node
from app.graph.nodes.route_request import route_request_node
from app.graph.nodes.run_selected_agent import run_selected_agent_node
from app.graph.nodes.save_memory import save_memory_node
from app.graph.nodes.save_messages import save_messages_node
from app.graph.state import ChatGraphState
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.message_repository import MessageRepository
from app.services.llm_service import LLMService
from app.services.memory_service import MemoryService
from app.services.router_service import RouterService


class ChatGraphBuilder:
    def __init__(
        self,
        *,
        agents: AgentRepository,
        chats: ChatRepository,
        messages: MessageRepository,
        router_service: RouterService,
        llm_service: LLMService,
        memory_service: MemoryService,
    ) -> None:
        self._agents = agents
        self._chats = chats
        self._messages = messages
        self._router_service = router_service
        self._llm_service = llm_service
        self._memory_service = memory_service

    def build(self):
        workflow = StateGraph(ChatGraphState)
        workflow.add_node(
            "load_context",
            load_context_node(
                chats=self._chats,
                messages=self._messages,
                memory_service=self._memory_service,
            ),
        )
        workflow.add_node("load_agents", load_agents_node(agents=self._agents))
        workflow.add_node(
            "route_request",
            route_request_node(router_service=self._router_service),
        )
        workflow.add_node(
            "run_selected_agent",
            run_selected_agent_node(chats=self._chats, llm_service=self._llm_service),
        )
        workflow.add_node(
            "save_memory",
            save_memory_node(memory_service=self._memory_service),
        )
        workflow.add_node(
            "save_messages",
            save_messages_node(messages=self._messages),
        )
        workflow.add_node("format_response", format_response_node())

        workflow.set_entry_point("load_context")
        workflow.add_edge("load_context", "load_agents")
        workflow.add_edge("load_agents", "route_request")
        workflow.add_edge("route_request", "run_selected_agent")
        workflow.add_edge("run_selected_agent", "save_memory")
        workflow.add_edge("save_memory", "save_messages")
        workflow.add_edge("save_messages", "format_response")
        workflow.add_edge("format_response", END)
        return workflow.compile()
