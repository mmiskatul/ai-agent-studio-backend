from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.agents.config import AgentConfig
from app.tools.base import AgentTool
from app.tools.registry import ToolRegistry

AgentFallback = Callable[[AgentConfig, str], str]
AgentLLM = Callable[[AgentConfig, str, list[str]], Awaitable[str | None]]


@dataclass(frozen=True)
class AgentRuntime:
    config: AgentConfig
    tools: list[AgentTool]
    llm: AgentLLM | None = None
    fallback: AgentFallback | None = None

    async def run(self, message: str, history: list[str] | None = None) -> str:
        if not self.config.is_active:
            return f"{self.config.name} is inactive and cannot handle this request."

        history = history or []
        if self.llm is not None:
            output = await self.llm(self.config, message, history)
            if output:
                return output

        output = await self._run_langchain_agent(message, history)
        if output:
            return output

        if self.fallback is not None:
            return self.fallback(self.config, message)

        return (
            f"{self.config.name} could not generate a dynamic response because no LLM runtime "
            "is available. Configure OPENAI_API_KEY and install backend requirements, then try "
            "again."
        )

    async def _run_langchain_agent(self, message: str, history: list[str]) -> str | None:
        try:
            from langchain.agents import create_agent as langchain_create_agent
        except ImportError:
            return None

        try:
            agent = langchain_create_agent(
                model=self._langchain_model_name(),
                tools=self._langchain_tools(),
                system_prompt=self.config.system_prompt,
            )
            messages = self._langchain_messages(message, history)
            if hasattr(agent, "ainvoke"):
                result = await agent.ainvoke({"messages": messages})
            else:
                result = agent.invoke({"messages": messages})
        except Exception:
            return None

        return self._extract_langchain_output(result)

    def _langchain_model_name(self) -> str:
        if ":" in self.config.model:
            return self.config.model
        return f"openai:{self.config.model}"

    def _langchain_tools(self) -> list[Any]:
        try:
            from langchain_core.tools import StructuredTool
        except ImportError:
            return []

        langchain_tools = []
        for configured_tool in self.tools:

            def run_tool(query: str, tool: AgentTool = configured_tool) -> str:
                payload = {
                    "query": query,
                    "text": query,
                    "expression": query,
                    "product": query,
                    "channel": query,
                }
                result = tool.handler(payload)
                if isinstance(result, str):
                    return result
                return "Async tool handlers are not supported in sync LangChain tools yet."

            langchain_tools.append(
                StructuredTool.from_function(
                    func=run_tool,
                    name=configured_tool.name,
                    description=configured_tool.description,
                ),
            )
        return langchain_tools

    def _langchain_messages(self, message: str, history: list[str]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for item in history[-12:]:
            role, _, content = item.partition(":")
            normalized_role = "assistant" if role.strip() == "assistant" else "user"
            if content.strip():
                messages.append({"role": normalized_role, "content": content.strip()})
        messages.append({"role": "user", "content": message})
        return messages

    def _extract_langchain_output(self, result: Any) -> str | None:
        if isinstance(result, str):
            return result.strip() or None
        if isinstance(result, dict):
            messages = result.get("messages")
            if isinstance(messages, list) and messages:
                last_message = messages[-1]
                content = getattr(last_message, "content", None)
                if isinstance(content, str) and content.strip():
                    return content.strip()
            output = result.get("output") or result.get("content")
            if isinstance(output, str) and output.strip():
                return output.strip()
        return None


def create_agent(
    config: AgentConfig,
    tool_registry: ToolRegistry,
    *,
    llm: AgentLLM | None = None,
    fallback: AgentFallback | None = None,
) -> AgentRuntime:
    tools = tool_registry.require_many(config.tools)
    return AgentRuntime(config=config, tools=tools, llm=llm, fallback=fallback)
