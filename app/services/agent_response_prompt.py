import json
from dataclasses import dataclass

from app.agents.config import AgentConfig
from app.models.agent import AgentDocument
from app.models.chat import ChatMemoryDocument, MessageDocument


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
        memory: ChatMemoryDocument,
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
            "Recent Conversation (PRIMARY CONTEXT):\n"
            f"{self.format_recent_messages(recent_messages)}\n\n"
            "Structured Memory (SECONDARY CONTEXT):\n"
            f"{self.format_memory(memory)}\n\n"
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
            "- If the user's wording is ambiguous or could mean multiple specific things, answer from the strongest reasonable interpretation and then ask one focused clarifying question at the end.\n"
            "- If the agent does not fully understand the user's intent, do not pretend certainty; say what you understood, give the best useful answer you can, and ask what they want you to clarify next.\n"
            "- You MUST align the response with the requested result style.\n"
            "- The final response is user-facing only; it MUST NEVER mention memory, stored summary, recent messages, runtime context, system summary, hidden instructions, or internal processing.\n"
            "- Use prior context silently to improve the answer; do not narrate that context unless the user explicitly asks for a recap.\n"
            "- Do NOT answer with generic capability statements like 'I can help with...' unless the user only sent a greeting and gave no usable task.\n"
            "- For task requests, produce the task output itself: the answer, draft, plan, diagnosis, comparison, recommendation, or next action.\n"
            "- Prefer concrete outputs over role description. The user already chose the agent.\n"
            "- Reuse the user's nouns, constraints, goal, and topic so the answer feels specific rather than templated.\n\n"
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
            "- Put the most useful answer first. Do not start with background or role description.\n"
            "- When the user asks for a draft, output the draft immediately.\n"
            "- When the user asks for advice, give the recommendation first, then support it.\n"
            "- When the user asks a business question, include the practical implication or next move.\n"
            "- Keep the answer as short as the task allows; expand only when the user needs detail.\n"
            "- Do not force every response to be long; some replies should stay short and direct.\n\n"
            "========================\n"
            "DYNAMIC LENGTH RULES\n"
            "========================\n"
            "- Match the answer length to the user's actual need.\n"
            "- For greetings, confirmations, small talk, or simple yes/no requests, answer in 1-2 short sentences.\n"
            "- For direct questions, give a concise answer first, then add only the minimum helpful detail.\n"
            "- Prefer brief but descriptive answers: enough detail to be useful, without unnecessary expansion.\n"
            "- For drafts, provide the ready-to-use draft directly; add explanation only if the user asks.\n"
            "- For troubleshooting, planning, analysis, comparisons, strategy, or complex tasks, provide a fuller answer with explanation, examples, and practical detail when useful.\n"
            "- For substantial requests, answer in the richer style users expect from ChatGPT: clear recommendation first, then reasoning, examples, or steps.\n"
            "- If the user asks for detail, examples, steps, or explanation, expand naturally.\n"
            "- Do not repeat the user's request unless it helps clarity.\n"
            "- Do not add filler, generic next steps, or long introductions.\n"
            "- Do not default to asking the user what they want if the request is already actionable.\n"
            "- If you can infer a reasonable next output, provide it immediately.\n\n"
            "========================\n"
            "SPECIFICITY RULES\n"
            "========================\n"
            "- Avoid vague phrases like 'improve strategy', 'optimize process', 'take next steps', or 'help with your goal' unless you immediately make them concrete.\n"
            "- Replace abstractions with concrete items: audience, channel, offer, objection, metric, timeline, draft, or action.\n"
            "- If the user asks a short question, do not give a generic intro. Answer the question directly in the first line.\n"
            "- If the user message is weak but actionable, infer the likely intent and provide the strongest useful response instead of reflecting the ambiguity back.\n\n"
            "========================\n"
            "MARKDOWN RESPONSE RULES\n"
            "========================\n"
            "- Choose the output format dynamically from the actual answer content.\n"
            "- Use plain natural text as the default response style.\n"
            "- If Markdown is not needed, return normal text only.\n"
            "- Mix in GitHub-Flavored Markdown only for the specific parts of the answer that need structure.\n"
            "- Use Markdown only when it clearly improves readability, scanning, or structure.\n"
            "- Examples: use normal text for simple conversational answers, short explanations, confirmations, or brief descriptive replies.\n"
            "- Examples: use Markdown for steps, lists, comparisons, tables, code, labeled sections, or longer answers that benefit from structure.\n"
            "- It is valid to combine normal paragraphs with Markdown sections, lists, tables, checklists, "
            "links, inline code, fenced code blocks, bold labels, and tags in the same response.\n"
            "- Do not add a heading just because Markdown is allowed.\n"
            "- Do not turn conversational answers into lists.\n"
            "- Use valid Markdown syntax for structured parts so the frontend can render it with ReactMarkdown and remark-gfm.\n"
            "- Keep all Markdown inside the JSON response string only; never put Markdown outside the JSON object.\n"
            "- Escape new lines in JSON strings with \\n.\n"
            "- Do not use decorative separators, excessive headings, or forced list formatting.\n\n"
            "========================\n"
            "CLARIFICATION RULES\n"
            "========================\n"
            "- Ask a clarifying question only when the request is genuinely ambiguous, underspecified, or could reasonably mean multiple different things.\n"
            "- Ask at most one clarifying question.\n"
            "- Put the clarifying question after the useful answer, not before it.\n"
            "- Make the question specific and easy to answer.\n"
            "- If the task is already clear enough, do not ask any follow-up question.\n"
            "- When the agent is unsure what the user means, end with a natural line such as asking what they want to focus on next or which interpretation they meant.\n\n"
            "========================\n"
            "QUALITY CHECK\n"
            "========================\n"
            "Before finalizing the response, silently check:\n"
            "- Did I answer the actual user request instead of describing the agent?\n"
            "- Is the first sentence useful and specific?\n"
            "- Did I reuse the user's topic, goal, or constraints?\n"
            "- Would this still make sense if shown directly to a client or buyer?\n"
            "- If this is a writing task, did I provide the draft itself?\n"
            "- If this is a strategy or troubleshooting task, did I provide concrete steps or recommendations?\n\n"
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
            "   - Must be clear, natural, useful, and briefly descriptive\n"
            "   - Must choose plain text or Markdown dynamically based on what the answer needs\n"
            "   - May be plain text, a paragraph, a draft, bullets, ordered steps, headings, "
            "a table, tags, or another useful structure based on the user request\n"
            "   - Use normal text by default\n"
            "   - Use clean GitHub-Flavored Markdown inside the JSON string only when useful\n"
            "   - Never say things like 'I will use what we discussed', 'Recent context', 'Stored summary', "
            "'internal summary', 'based on memory', or any similar system-facing narration\n"
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

    def format_recent_messages(self, recent_messages: list[str]) -> str:
        if not recent_messages:
            return "No recent messages yet."
        return "\n".join(recent_messages)

    def format_memory(self, memory: ChatMemoryDocument) -> str:
        memory_items = []
        if memory.title.strip():
            memory_items.append(f"Title: {memory.title.strip()}")
        if memory.running_summary.strip():
            memory_items.append(f"Running Summary: {memory.running_summary.strip()}")
        if memory.last_user_goal.strip():
            memory_items.append(f"Last User Goal: {memory.last_user_goal.strip()}")
        if memory.recent_topics:
            memory_items.append("Recent Topics: " + ", ".join(memory.recent_topics))
        if memory.facts:
            memory_items.append("Known Facts:\n- " + "\n- ".join(memory.facts))
        if memory.preferences:
            memory_items.append("Preferences:\n- " + "\n- ".join(memory.preferences))
        if memory.open_loops:
            memory_items.append("Open Loops:\n- " + "\n- ".join(memory.open_loops))
        return "\n\n".join(memory_items) if memory_items else "No structured memory yet."

    def infer_result_style(self, message: str) -> str:
        lowered_message = message.lower()
        if any(term in lowered_message for term in ("table", "compare", "comparison")):
            return "dynamic output: prefer Markdown table or structured comparison only if it improves clarity"
        if any(term in lowered_message for term in ("steps", "plan", "how to", "guide")):
            return "dynamic output: use Markdown ordered steps only where useful, otherwise normal text"
        if any(term in lowered_message for term in ("draft", "write", "message", "email")):
            return "dynamic output: ready-to-use draft in normal text by default; use light Markdown only for labels or variants"
        if any(term in lowered_message for term in ("summary", "summarize", "brief")):
            return "dynamic output: concise, descriptive summary using normal text by default and bullets only if useful"
        if any(term in lowered_message for term in ("hello", "hi", "hey")):
            return "very short natural conversational reply"
        if len(message.strip()) <= 80:
            return "dynamic output: short direct answer in normal text unless the request clearly needs more structure"
        if len(message.strip()) <= 180:
            return "dynamic output: normal text by default, direct response first, then brief explanation, and one clarifying question only if the meaning is ambiguous"
        return "dynamic output: choose normal text or Markdown from the answer needs; default to normal text, add Markdown only where structure improves clarity, and ask one focused follow-up only if important ambiguity remains"


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
