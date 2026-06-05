import json
from dataclasses import dataclass
from logging import getLogger
from typing import Any

from app.core.config import settings
from app.models.agent import AgentDocument
from app.models.message import MessageRecord

logger = getLogger(__name__)


@dataclass(frozen=True)
class StructuredAgentResponse:
    system_summary: str
    response: str
    markdown: str
    render_mode: str


class LLMService:
    async def generate_agent_response(
        self,
        *,
        agent: AgentDocument,
        user_message: str,
        memory_summary: str,
        memory_facts: list[str],
        messages: list[MessageRecord],
    ) -> StructuredAgentResponse:
        prompt = self.build_agent_prompt(
            agent=agent,
            user_message=user_message,
            memory_summary=memory_summary,
            memory_facts=memory_facts,
            messages=messages,
        )
        raw_response = await self._invoke_chat_model(
            model=agent.model or agent.llm_engine or settings.default_llm_engine,
            temperature=agent.temperature,
            system_prompt=agent.system_prompt,
            user_prompt=prompt,
            fallback=self._fallback_agent_response(agent, user_message),
        )
        return self._parse_structured_agent_response(
            raw_response=raw_response,
            agent=agent,
            user_message=user_message,
        )

    async def classify_route(
        self,
        *,
        user_message: str,
        agents: list[AgentDocument],
    ) -> str | None:
        if not agents:
            return None
        options = "\n".join(
            f"- id={agent.id}; name={agent.name}; role={agent.role}; description={agent.description or agent.purpose}"
            for agent in agents
        )
        prompt = (
            "Select exactly one agent id for the user request. Return only the id.\n\n"
            f"Available agents:\n{options}\n\n"
            f"User request: {user_message}"
        )
        response = await self._invoke_chat_model(
            model=settings.default_llm_engine,
            temperature=0,
            system_prompt="You are a strict routing classifier.",
            user_prompt=prompt,
            fallback="",
        )
        selected_id = response.strip()
        valid_ids = {agent.id for agent in agents if agent.id}
        return selected_id if selected_id in valid_ids else None

    async def summarize_memory(
        self,
        *,
        previous_summary: str,
        previous_facts: list[str],
        user_message: str,
        assistant_response: str,
    ) -> tuple[str, list[str]]:
        prompt = (
            "Update long-term memory for a chatbot session.\n"
            "Return concise JSON with keys summary and facts. Facts must be an array of short strings.\n\n"
            f"Previous summary: {previous_summary or 'None'}\n"
            f"Previous facts: {previous_facts or []}\n"
            f"User message: {user_message}\n"
            f"Assistant response: {assistant_response[:2000]}"
        )
        response = await self._invoke_chat_model(
            model=settings.default_llm_engine,
            temperature=0.1,
            system_prompt="You maintain concise, relevant user memory.",
            user_prompt=prompt,
            fallback="",
        )
        parsed = self._parse_json_object(response)
        if not parsed:
            summary = self._trim_summary(previous_summary, user_message)
            return summary, previous_facts[:12]
        summary = str(parsed.get("summary") or previous_summary or "").strip()
        facts = parsed.get("facts")
        clean_facts = [str(item).strip() for item in facts if str(item).strip()] if isinstance(facts, list) else []
        return summary[:1200], clean_facts[:12]

    def build_agent_prompt(
        self,
        *,
        agent: AgentDocument,
        user_message: str,
        memory_summary: str,
        memory_facts: list[str],
        messages: list[MessageRecord],
    ) -> str:
        recent_conversation = "\n".join(
            f"{message.sender_type}: {message.content}" for message in messages[-12:]
        )
        facts = "\n".join(f"- {fact}" for fact in memory_facts) or "None"
        return (
            f"You are {agent.name}\n\n"
            "Role:\n"
            f"{agent.role}\n\n"
            "Purpose:\n"
            f"{agent.description or agent.purpose}\n\n"
            "Configured Fallback Language:\n"
            f"{agent.language or 'EN'}\n\n"
            "Memory Summary:\n"
            f"{memory_summary or 'None'}\n\n"
            "Memory Facts:\n"
            f"{facts}\n\n"
            "Conversation:\n"
            f"{recent_conversation or 'None'}\n\n"
            "User Message:\n"
            f"{user_message}\n\n"
            "Rules:\n"
            "- Stay within the assigned role and purpose.\n"
            "- Be accurate and helpful.\n"
            "- Do not expose internal reasoning.\n"
            "- Use tools only when needed.\n"
            "- Default to a clean, brief, client-ready answer.\n"
            "- Keep the tone polished, direct, and easy to scan.\n"
            "- Prefer short paragraphs or very short bullets over long explanations.\n"
            "- Do not sound robotic, academic, or over-structured.\n"
            "- Do not force one fixed template for every answer.\n"
            "- First understand the user's intent, then choose the best response format dynamically.\n"
            "- For direct/simple questions, answer directly in plain text or short bullets without unnecessary headings.\n"
            "- For explanation or teaching, use clear sections only if helpful; otherwise use natural paragraphs.\n"
            "- For technical guidance, architecture, roadmap, or analysis, use structured headings and bullets where useful.\n"
            "- For rewriting, chatting, email, proposal, or message writing, produce a human, natural, ready-to-use answer; do not make it look like a report unless requested.\n"
            "- For code/debugging, explain briefly, then provide code or concrete steps in proper code fences when useful.\n"
            "- If the question is small, keep the answer small. If the question is deep, make the answer detailed.\n"
            "- Do not add filler, long introductions, repeated context, or unnecessary closing lines.\n"
            "- If one strong paragraph solves the request, use one strong paragraph.\n"
            "- Only expand when the user clearly asks for more detail, multiple options, or a process.\n"
            "- Use the database system prompt as the highest priority instruction.\n"
            "- Use relevant memory and recent conversation without repeating it unnecessarily.\n"
            "- Do not invent private data, prices, policies, or tool results.\n"
            "- If context is missing, state a practical assumption and continue.\n"
            "- Ask at most one clarifying question, after giving useful help.\n"
            "- You must answer in the same language as the user's latest message unless the user explicitly asks to switch languages.\n"
            f"- Use {agent.language or 'EN'} only as the fallback language when the user's language is unclear.\n"
            "- Keep the full answer in one language and do not mix languages unless the user asks for that.\n\n"
            "Output requirements:\n"
            "- Return only one valid JSON object.\n"
            "- Do not wrap the JSON in a code block.\n"
            "- Do not add extra keys.\n"
            "- Use this exact schema:\n"
            '{\n'
            '  "system_summary": "short internal summary for title/memory",\n'
            '  "response": "plain user-facing answer",\n'
            '  "markdown": "frontend-friendly markdown version of the same answer",\n'
            '  "render_mode": "plain|markdown|question_flow"\n'
            '}\n\n'
            "Field rules:\n"
            "- system_summary: one short sentence that names the real topic and what the agent handled.\n"
            "- response: a clean, brief, client-facing answer in natural text. Default to readable plain text.\n"
            "- response should usually be 1 short paragraph or a few short bullets unless the request genuinely needs more.\n"
            "- markdown: GitHub-Flavored Markdown for frontend rendering, but keep it minimal and clean.\n"
            "- markdown must follow the user's actual question flow instead of any fixed template.\n"
            "- If the user asked multiple questions, requested a process, or the answer has distinct parts, split markdown by those question-driven parts.\n"
            "- If the user asked one simple question, keep markdown minimal and natural instead of forcing sections.\n"
            "- Use headings, bullets, numbered steps, tables, blockquotes, and code fences only when they fit the content.\n"
            "- Do not force labels like Summary, Overview, Conclusion, or Next Steps unless they are genuinely useful.\n"
            "- Avoid more than 2 short sections unless the request clearly requires them.\n"
            "- Avoid long bullet lists unless the user explicitly asks for a list or step-by-step breakdown.\n"
            "- render_mode must be:\n"
            "  plain for short conversational answers,\n"
            "  markdown for structured answers,\n"
            "  question_flow when the markdown is organized around the user's questions or sub-questions.\n"
            "- Both response and markdown must say the same core thing, just formatted differently for frontend use."
        )

    async def _invoke_chat_model(
        self,
        *,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
        fallback: str,
    ) -> str:
        if not settings.openai_api_key:
            return fallback

        openai_response = await self._invoke_openai_responses(
            model=model,
            temperature=temperature,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        if openai_response:
            return openai_response

        langchain_response = await self._invoke_langchain_chat(
            model=model,
            temperature=temperature,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        if langchain_response:
            return langchain_response

        return fallback

    async def _invoke_openai_responses(
        self,
        *,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.exception("OpenAI SDK is not installed")
            return ""

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        try:
            response = await client.responses.create(
                model=self._openai_model_name(model),
                instructions=system_prompt,
                input=user_prompt,
                temperature=temperature,
            )
        except Exception:
            logger.exception("OpenAI Responses API invocation failed", extra={"model": model})
            return ""

        output_text = getattr(response, "output_text", None)
        return output_text.strip() if isinstance(output_text, str) and output_text.strip() else ""

    async def _invoke_langchain_chat(
        self,
        *,
        model: str,
        temperature: float,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError:
            logger.exception("langchain-openai is not installed")
            return ""
        try:
            llm = ChatOpenAI(
                model=self._openai_model_name(model),
                temperature=temperature,
                api_key=settings.openai_api_key,
            )
            result = await llm.ainvoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except Exception:
            logger.exception("LangChain chat invocation failed", extra={"model": model})
            return ""
        content = getattr(result, "content", "")
        return content.strip() if isinstance(content, str) and content.strip() else ""

    def _openai_model_name(self, model: str) -> str:
        return model.split(":", 1)[1] if model.startswith("openai:") else model

    def _fallback_agent_response(self, agent: AgentDocument, user_message: str) -> str:
        return json.dumps(
            {
                "system_summary": (
                    f"{agent.name} handled a request about "
                    f"{self._trim_summary('', user_message)[:120].strip() or agent.role}."
                ),
                "response": (
                    f"{agent.name} is ready to help with {agent.description or agent.purpose or agent.role}. "
                    "Share the exact task or a bit more detail, and the next reply can be more specific."
                ),
                "markdown": (
                    f"{agent.name} is ready to help with "
                    f"{agent.description or agent.purpose or agent.role}. "
                    "Share the exact task or a bit more detail, and the next reply can be more specific."
                ),
                "render_mode": "plain",
            }
        )

    def _parse_json_object(self, value: str) -> dict[str, Any] | None:
        if not value.strip().startswith("{"):
            return None
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _trim_summary(self, previous_summary: str, user_message: str) -> str:
        text = " ".join([previous_summary.strip(), user_message.strip()]).strip()
        return text[:1200]

    def _parse_structured_agent_response(
        self,
        *,
        raw_response: str,
        agent: AgentDocument,
        user_message: str,
    ) -> StructuredAgentResponse:
        parsed = self._parse_json_object(self._extract_json_payload(raw_response))
        if isinstance(parsed, dict):
            response = str(parsed.get("response") or "").strip()
            markdown = str(parsed.get("markdown") or "").strip()
            render_mode = str(parsed.get("render_mode") or "").strip().lower()
            system_summary = str(parsed.get("system_summary") or "").strip()
            if response:
                final_markdown = markdown or response
                final_render_mode = (
                    render_mode if render_mode in {"plain", "markdown", "question_flow"} else
                    self._infer_render_mode(final_markdown, response)
                )
                return StructuredAgentResponse(
                    system_summary=system_summary or self._build_system_summary(agent, user_message),
                    response=response,
                    markdown=final_markdown,
                    render_mode=final_render_mode,
                )

        fallback_text = raw_response.strip() or self._fallback_text(agent, user_message)
        return StructuredAgentResponse(
            system_summary=self._build_system_summary(agent, user_message),
            response=fallback_text,
            markdown=fallback_text,
            render_mode=self._infer_render_mode(fallback_text, fallback_text),
        )

    def _extract_json_payload(self, value: str) -> str:
        text = value.strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return text
        return text[start : end + 1]

    def _build_system_summary(self, agent: AgentDocument, user_message: str) -> str:
        topic = " ".join(user_message.strip().split())
        if len(topic) > 100:
            topic = f"{topic[:97].rstrip()}..."
        if not topic:
            topic = agent.role
        return f"{topic} handled by {agent.name} as {agent.role}."

    def _fallback_text(self, agent: AgentDocument, user_message: str) -> str:
        parsed = self._parse_json_object(self._fallback_agent_response(agent, user_message))
        if isinstance(parsed, dict):
            return str(parsed.get("response") or "").strip()
        return user_message.strip()

    def _infer_render_mode(self, markdown: str, response: str) -> str:
        markdown_text = markdown.strip()
        if any(marker in markdown_text for marker in ("## ", "### ", "- ", "1. ", "|", "```")):
            if any(token in markdown_text.lower() for token in ("question", "q1", "q2")):
                return "question_flow"
            return "markdown"
        if "\n\n" in markdown_text and markdown_text != response.strip():
            return "markdown"
        return "plain"
