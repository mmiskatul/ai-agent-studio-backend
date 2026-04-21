from app.tools.base import AgentTool
from app.tools.builtin import BUILTIN_TOOLS


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def require_many(self, names: list[str]) -> list[AgentTool]:
        missing = [name for name in names if name not in self._tools]
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Unknown agent tools: {missing_list}")
        return [self._tools[name] for name in names]

    def list_names(self) -> list[str]:
        return sorted(self._tools)


def default_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in BUILTIN_TOOLS:
        registry.register(tool)
    return registry
