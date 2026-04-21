from app.agents.config import AgentConfig
from app.agents.configs import DEFAULT_AGENT_CONFIGS
from app.agents.factory import AgentFallback, AgentLLM, create_agent
from app.agents.registry import AgentRegistry
from app.agents.routing import AgentRouter
from app.tools.registry import ToolRegistry, default_tool_registry


class AgentPlatform:
    def __init__(
        self,
        configs: list[AgentConfig],
        tool_registry: ToolRegistry,
        *,
        llm: AgentLLM | None = None,
        fallback: AgentFallback | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.registry = AgentRegistry()
        for config in configs:
            self.registry.register(
                create_agent(config, tool_registry, llm=llm, fallback=fallback),
            )
        self.router = AgentRouter(self.registry)

    async def run(
        self,
        message: str,
        *,
        agent_key: str | None = None,
        history: list[str] | None = None,
    ) -> str:
        agent = self.router.select(message, agent_key=agent_key)
        return await agent.run(message, history)


def build_default_platform(
    *,
    llm: AgentLLM | None = None,
    fallback: AgentFallback | None = None,
) -> AgentPlatform:
    return AgentPlatform(
        configs=DEFAULT_AGENT_CONFIGS,
        tool_registry=default_tool_registry(),
        llm=llm,
        fallback=fallback,
    )
