from app.models.agent import AgentDocument
from app.services.llm_service import LLMService


class RouterService:
    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def route(
        self,
        *,
        user_message: str,
        agents: list[AgentDocument],
        requested_agent_id: str | None = None,
    ) -> tuple[AgentDocument, str]:
        active_agents = [agent for agent in agents if agent.is_active and agent.status == "enabled"]
        if not active_agents:
            fallback = self._default_agent()
            return fallback, "No active database agents were available; used safe default agent."

        if requested_agent_id:
            for agent in active_agents:
                if agent.id == requested_agent_id:
                    return agent, f"Agent was explicitly requested: {agent.name}."

        keyword_match = self._keyword_route(user_message, active_agents)
        if keyword_match is not None:
            agent, score = keyword_match
            return agent, f"Matched {score} routing keyword(s) for {agent.name}."

        llm_agent_id = await self._llm.classify_route(
            user_message=user_message,
            agents=active_agents,
        )
        if llm_agent_id:
            for agent in active_agents:
                if agent.id == llm_agent_id:
                    return agent, f"LLM router classified the request for {agent.name}."

        fallback = self._find_default_agent(active_agents)
        return fallback, f"No confident route matched; used fallback agent {fallback.name}."

    def _keyword_route(
        self,
        user_message: str,
        agents: list[AgentDocument],
    ) -> tuple[AgentDocument, int] | None:
        lowered = user_message.lower()
        scored: list[tuple[int, int, AgentDocument]] = []
        for agent in agents:
            keywords = agent.routing_keywords or self._derived_keywords(agent)
            score = sum(1 for keyword in keywords if keyword.lower() in lowered)
            if score > 0:
                scored.append((score, -agent.priority, agent))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        if scored and scored[0][0] >= 1:
            return scored[0][2], scored[0][0]
        return None

    def _derived_keywords(self, agent: AgentDocument) -> list[str]:
        text = " ".join([agent.name, agent.role, agent.description or "", agent.purpose])
        return [token.strip(".,:;!?").lower() for token in text.split() if len(token) > 3]

    def _find_default_agent(self, agents: list[AgentDocument]) -> AgentDocument:
        for agent in agents:
            text = f"{agent.name} {agent.role}".lower()
            if "default" in text or "general" in text:
                return agent
        return sorted(agents, key=lambda agent: agent.priority)[0]

    def _default_agent(self) -> AgentDocument:
        return AgentDocument(
            id="default_agent",
            user_id="system",
            name="Default Agent",
            role="General Assistant",
            purpose="Handles requests when no configured agent is available.",
            description="Safe fallback assistant.",
            system_prompt="Answer helpfully and ask for clarification when needed.",
            model="gpt-4.1-mini",
            temperature=0.4,
            routing_keywords=[],
            priority=999,
            is_active=True,
        )
