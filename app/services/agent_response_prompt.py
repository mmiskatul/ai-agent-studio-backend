import json
from dataclasses import dataclass

from app.agents.config import AgentConfig
from app.models.agent import AgentDocument
from app.models.chat import MessageDocument


@dataclass(frozen=True)
class AgentJsonResponse:
    system_summary: str
    response: str


class AgentResponsePromptBuilder:
    json_instructions = (
        "Return only a valid JSON object with exactly these keys: system_summary and response."
    )

    def build(
        self,
        *,
        agent: AgentDocument,
        config: AgentConfig,
        memory_summary: str,
        current_message: str,
        messages: list[MessageDocument],
    ) -> str:
        recent_messages = [
            f"{message.sender_type}: {message.content}"
            for message in messages[-10:]
            if message.content.strip()
        ]
        result_style = self.infer_result_style(current_message)
        return (
            "You are an AI assistant running inside a production-level multi-agent chat system.\n\n"
            "========================\n"
            "AGENT CONTEXT (FROM DATABASE)\n"
            "========================\n"
            f"Agent Name: {agent.name}\n"
            f"Agent Role: {agent.role}\n"
            f"Project Description: {agent.description or agent.purpose}\n\n"
            "Base System Instructions:\n"
            f"{config.system_prompt}\n\n"
            "========================\n"
            "RUNTIME CONTEXT (FROM CHAT SYSTEM)\n"
            "========================\n"
            "User Message:\n"
            f"{current_message.strip()}\n\n"
            "Memory:\n"
            f"{self.format_memory(memory_summary, recent_messages)}\n\n"
            "Result Style:\n"
            f"{result_style}\n\n"
            "========================\n"
            "CORE EXECUTION RULES\n"
            "========================\n"
            "- You MUST strictly follow the selected agent's role and system instructions.\n"
            "- You MUST behave as that agent (tone, purpose, behavior).\n"
            "- You MUST use memory ONLY if it is relevant to the current user message.\n"
            "- You MUST prioritize the latest user message over older context.\n"
            "- You MUST keep consistency with previous conversation.\n"
            "- You MUST NOT hallucinate missing data.\n"
            "- If something is unclear, make a minimal assumption and proceed logically.\n"
            "- You MUST align the response with the requested result style.\n\n"
            "========================\n"
            "DYNAMIC RESPONSE STRUCTURE\n"
            "========================\n"
            "- Do NOT force every answer into points, bullets, or numbered steps.\n"
            "- Choose the response structure dynamically from the user's latest message.\n"
            "- Use a short natural paragraph for greetings, simple questions, and conversation.\n"
            "- Use a ready-to-send draft when the user asks to write a message, email, reply, or script.\n"
            "- Use numbered steps only when the user asks for a process, plan, guide, or sequence.\n"
            "- Use bullets only when scanning multiple options, facts, requirements, or recommendations helps.\n"
            "- Use a table only for comparison, metrics, structured data, or when the user asks for one.\n"
            "- Use headings only for longer answers where sections improve readability.\n"
            "- Keep the answer as short as the task allows; expand only when the user needs detail.\n\n"
            "========================\n"
            "DYNAMIC LENGTH RULES\n"
            "========================\n"
            "- Match the answer length to the user's actual need.\n"
            "- For greetings, confirmations, small talk, or simple yes/no requests, answer in 1-2 short sentences.\n"
            "- For direct questions, give a concise answer first, then add only the minimum helpful detail.\n"
            "- For drafts, provide the ready-to-use draft directly; add explanation only if the user asks.\n"
            "- For troubleshooting, planning, analysis, comparisons, or complex tasks, provide enough detail to be useful.\n"
            "- If the user asks for detail, examples, steps, or explanation, expand naturally.\n"
            "- Do not repeat the user's request unless it helps clarity.\n"
            "- Do not add filler, generic next steps, or long introductions.\n\n"
            "========================\n"
            "MARKDOWN RESPONSE RULES\n"
            "========================\n"
            "- Use plain natural text as the default response style.\n"
            "- Mix in GitHub-Flavored Markdown only for the specific parts of the answer that need structure.\n"
            "- It is valid to combine normal paragraphs with Markdown sections, lists, tables, checklists, "
            "links, inline code, fenced code blocks, bold labels, and tags in the same response.\n"
            "- Do not add a heading just because Markdown is allowed.\n"
            "- Do not turn conversational answers into lists.\n"
            "- Use valid Markdown syntax for structured parts so the frontend can render it with ReactMarkdown and remark-gfm.\n"
            "- Keep all Markdown inside the JSON response string only; never put Markdown outside the JSON object.\n"
            "- Escape new lines in JSON strings with \\n.\n"
            "- Do not use decorative separators, excessive headings, or forced list formatting.\n\n"
            "========================\n"
            "TASK\n"
            "========================\n"
            "You must generate TWO things:\n\n"
            "1. system_summary:\n"
            "   - A short internal summary (1-2 sentences)\n"
            "   - Include:\n"
            "      user intent\n"
            "      agent role used\n"
            "      memory used (if any)\n"
            "      response style applied\n\n"
            "2. response:\n"
            "   - The final answer for the user\n"
            "   - Must follow agent role + tone + style\n"
            "   - Must be clear, natural, and useful\n"
            "   - May be plain text, a paragraph, a draft, bullets, ordered steps, headings, "
            "a table, tags, or another useful structure based on the user request\n"
            "   - Use mixed plain text and clean GitHub-Flavored Markdown inside the JSON string only when useful\n"
            "   - Do not wrap the whole response value in a code block\n\n"
            "========================\n"
            "STRICT OUTPUT RULES (VERY IMPORTANT)\n"
            "========================\n"
            "- You MUST return ONLY a valid JSON object\n"
            "- NO markdown outside the JSON object\n"
            "- NO explanations\n"
            "- NO extra text\n"
            "- NO code block\n"
            "- NO additional keys\n\n"
            "========================\n"
            "OUTPUT FORMAT (MANDATORY)\n"
            "========================\n"
            "{\n"
            '  "system_summary": "short context summary",\n'
            '  "response": "A natural answer first.\\n\\nUse **Markdown** only where it helps, like:\\n\\n- Key point\\n- Another point"\n'
            "}"
        )

    def format_memory(self, memory_summary: str, recent_messages: list[str]) -> str:
        memory_items = []
        if memory_summary.strip():
            memory_items.append(f"Stored summary: {memory_summary.strip()}")
        if recent_messages:
            memory_items.append("Recent messages:\n" + "\n".join(recent_messages))
        return "\n\n".join(memory_items) if memory_items else "No relevant memory yet."

    def infer_result_style(self, message: str) -> str:
        lowered_message = message.lower()
        if any(term in lowered_message for term in ("table", "compare", "comparison")):
            return "natural explanation plus a Markdown table only if it improves clarity"
        if any(term in lowered_message for term in ("steps", "plan", "how to", "guide")):
            return "natural explanation with ordered steps only where useful"
        if any(term in lowered_message for term in ("draft", "write", "message", "email")):
            return "ready-to-use draft in natural text; use light Markdown only for labels or variants"
        if any(term in lowered_message for term in ("summary", "summarize", "brief")):
            return "concise summary using paragraph text or bullets only if useful"
        if any(term in lowered_message for term in ("hello", "hi", "hey")):
            return "very short natural conversational reply"
        if len(message.strip()) <= 80:
            return "short direct answer unless the request clearly needs detail"
        return "dynamic mixed answer; default to natural text and add Markdown only where useful"


def parse_agent_json_response(raw_response: str) -> AgentJsonResponse:
    cleaned_response = _extract_json_object(raw_response.strip())
    try:
        parsed = json.loads(cleaned_response)
    except json.JSONDecodeError:
        return AgentJsonResponse(system_summary="", response=_strip_json_fallback(raw_response))

    if not isinstance(parsed, dict):
        return AgentJsonResponse(system_summary="", response=cleaned_response)

    system_summary = parsed.get("system_summary")
    response = parsed.get("response")
    if not isinstance(response, str) or not response.strip():
        return AgentJsonResponse(system_summary="", response=cleaned_response)

    return AgentJsonResponse(
        system_summary=system_summary.strip() if isinstance(system_summary, str) else "",
        response=response.strip(),
    )


def _extract_json_object(text: str) -> str:
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _strip_json_fallback(text: str) -> str:
    extracted = _extract_json_object(text.strip())
    try:
        parsed = json.loads(extracted)
    except json.JSONDecodeError:
        return text.strip()

    if isinstance(parsed, dict) and isinstance(parsed.get("response"), str):
        return parsed["response"].strip()
    return text.strip()
