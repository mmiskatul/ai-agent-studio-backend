from __future__ import annotations

from typing import Any

from app.tools.base import AgentTool


def _search(payload: dict[str, Any]) -> str:
    query = str(payload.get("query", "")).strip()
    if not query:
        return "Search needs a query."
    return f"Search placeholder for: {query}. Connect a real search provider here."


def _summarizer(payload: dict[str, Any]) -> str:
    text = str(payload.get("text", "")).strip()
    if not text:
        return "Summarizer needs text."
    sentences = [part.strip() for part in text.replace("\n", " ").split(".") if part.strip()]
    return ". ".join(sentences[:3]) + ("." if sentences else "")


def _calculator(payload: dict[str, Any]) -> str:
    expression = str(payload.get("expression", "")).strip()
    allowed = set("0123456789+-*/(). ")
    if not expression or any(char not in allowed for char in expression):
        return "Calculator requires a basic numeric expression."
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception:
        return "Calculator could not evaluate the expression."


def _sales_playbook(payload: dict[str, Any]) -> str:
    product = str(payload.get("product", "the offer")).strip() or "the offer"
    channel = str(payload.get("channel", "the chosen channel")).strip() or "the chosen channel"
    return (
        f"For {product} on {channel}: lead with one clear benefit, show proof, "
        "make price/order steps visible, and follow up on every buyer message."
    )


BUILTIN_TOOLS = [
    AgentTool(name="search", description="Searches external knowledge sources.", handler=_search),
    AgentTool(name="summarizer", description="Summarizes long text.", handler=_summarizer),
    AgentTool(
        name="calculator",
        description="Evaluates basic numeric expressions.",
        handler=_calculator,
    ),
    AgentTool(
        name="sales_playbook",
        description="Returns a compact sales workflow for a product and channel.",
        handler=_sales_playbook,
    ),
]
