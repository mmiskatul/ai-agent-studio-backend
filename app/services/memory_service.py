from app.models.memory import MemoryRecord
from app.repositories.memory_repository import MemoryRepository
from app.services.llm_service import LLMService


class MemoryService:
    def __init__(self, memories: MemoryRepository, llm_service: LLMService) -> None:
        self._memories = memories
        self._llm = llm_service

    async def load(self, user_id: str, session_id: str) -> MemoryRecord | None:
        return await self._memories.get_for_session(user_id, session_id)

    async def update(
        self,
        *,
        user_id: str,
        session_id: str,
        chat_id: str,
        agent_id: str,
        previous_memory: MemoryRecord | None,
        user_message: str,
        assistant_response: str,
    ) -> MemoryRecord:
        previous_summary = previous_memory.summary if previous_memory else ""
        previous_facts = previous_memory.facts if previous_memory else []
        summary, facts = await self._llm.summarize_memory(
            previous_summary=previous_summary,
            previous_facts=previous_facts,
            user_message=user_message,
            assistant_response=assistant_response,
        )
        preferences = previous_memory.preferences if previous_memory else []
        return await self._memories.upsert_session_memory(
            user_id=user_id,
            session_id=session_id,
            chat_id=chat_id,
            summary=summary,
            facts=facts,
            preferences=preferences,
            last_agent_id=agent_id,
        )
