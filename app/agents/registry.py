from app.agents.factory import AgentRuntime


class AgentRegistry:
    def __init__(self) -> None:
        self._agents_by_id: dict[str, AgentRuntime] = {}
        self._agents_by_name: dict[str, AgentRuntime] = {}

    def register(self, agent: AgentRuntime) -> None:
        self._agents_by_id[agent.config.id] = agent
        self._agents_by_name[agent.config.name.lower()] = agent

    def clear(self) -> None:
        self._agents_by_id.clear()
        self._agents_by_name.clear()

    def get(self, key: str) -> AgentRuntime | None:
        return self._agents_by_id.get(key) or self._agents_by_name.get(key.lower())

    def require(self, key: str) -> AgentRuntime:
        agent = self.get(key)
        if agent is None:
            raise KeyError(f"Agent not registered: {key}")
        return agent

    def list(self) -> list[AgentRuntime]:
        return list(self._agents_by_id.values())
