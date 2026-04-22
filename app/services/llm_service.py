from logging import getLogger
from typing import Any

from app.core.config import settings
from app.models.agent import AgentDocument
from app.models.message import MessageRecord

logger = getLogger(__name__)


class LLMService:
    async def generate_agent_response(
        self,
        *,
        agent: AgentDocument,
        user_message: str,
        memory_summary: str,
        memory_facts: list[str],
        messages: list[MessageRecord],
    ) -> str:
        prompt = self.build_agent_prompt(
            agent=agent,
            user_message=user_message,
            memory_summary=memory_summary,
            memory_facts=memory_facts,
            messages=messages,
        )
        return await self._invoke_chat_model(
            model=agent.model or agent.llm_engine or settings.default_llm_engine,
            temperature=agent.temperature,
            system_prompt=agent.system_prompt,
            user_prompt=prompt,
            fallback=self._fallback_agent_response(agent, user_message),
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
            "- Be concise but clear.\n"
            "- Use the database system prompt as the highest priority instruction.\n"
            "- Use relevant memory and recent conversation without repeating it unnecessarily.\n"
            "- Do not invent private data, prices, policies, or tool results.\n"
            "- If context is missing, state a practical assumption and continue.\n"
            "- Ask at most one clarifying question, after giving useful help.\n\n"
            "Output:\n"
            "- Return only the assistant response text.\n"
            "- Use readable Markdown when it improves clarity.\n"
            "- Do not wrap the answer in JSON."
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
        return (
            f"{agent.name} received your request and is configured for {agent.role}.\n\n"
            f"Request: {user_message.strip()}\n\n"
            "Here is the best response I can provide from the available agent configuration: "
            f"focus on {agent.description or agent.purpose or agent.role}, use the recent "
            "conversation context, and answer with clear next steps. Please share any missing "
            "details if you want a more specific follow-up."
        )

    def _parse_json_object(self, value: str) -> dict[str, Any] | None:
        import json

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
