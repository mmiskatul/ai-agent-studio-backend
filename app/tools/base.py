from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

ToolHandler = Callable[[dict[str, Any]], str | Awaitable[str]]


@dataclass(frozen=True)
class AgentTool:
    name: str
    description: str
    handler: ToolHandler

