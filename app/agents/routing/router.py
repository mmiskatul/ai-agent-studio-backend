from app.agents.factory import AgentRuntime
from app.agents.registry import AgentRegistry


class AgentRouter:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def select(self, task: str, agent_key: str | None = None) -> AgentRuntime:
        if agent_key:
            return self._registry.require(agent_key)

        lowered_task = task.lower()
        scored: list[tuple[int, AgentRuntime]] = []
        for agent in self._registry.list():
            searchable = " ".join(
                [
                    agent.config.name,
                    agent.config.description,
                    agent.config.system_prompt,
                    " ".join(agent.config.tools),
                ]
            ).lower()
            score = sum(
                1
                for token in lowered_task.split()
                if len(token) > 2 and token in searchable
            )
            scored.append((score, agent))

        scored.sort(key=lambda item: item[0], reverse=True)
        if scored and scored[0][0] > 0:
            return scored[0][1]

        agents = self._registry.list()
        if not agents:
            raise KeyError("No agents registered")
        return agents[0]
