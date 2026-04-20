from collections import Counter
from datetime import timedelta

from app.models.base import now_utc
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.schemas.overview import (
    OverviewActivityItem,
    OverviewAgentSummary,
    OverviewCategorySummary,
    OverviewResponse,
    OverviewStats,
)


class OverviewService:
    def __init__(self, agents: AgentRepository, chats: ChatRepository) -> None:
        self._agents = agents
        self._chats = chats

    async def get_overview(self, user: UserDocument) -> OverviewResponse:
        user_id = user.id or ""
        agents = await self._agents.list_by_user(user_id)
        chats = await self._chats.list_by_user(user_id)
        chat_ids = [chat.id or "" for chat in chats if chat.id]
        chat_agent_map = {chat.id or "": chat.agent_id for chat in chats if chat.id}
        thirty_days_ago = now_utc() - timedelta(days=30)
        seven_days_ago = now_utc() - timedelta(days=7)

        message_counts_by_chat = await self._chats.count_messages_by_chat_ids(chat_ids)
        query_counts_by_chat = await self._chats.count_user_messages_by_chat_ids(
            chat_ids,
            since=thirty_days_ago,
        )

        query_counts_by_agent: dict[str, int] = {}
        for chat_id, count in query_counts_by_chat.items():
            agent_id = chat_agent_map.get(chat_id)
            if agent_id:
                query_counts_by_agent[agent_id] = query_counts_by_agent.get(agent_id, 0) + count

        active_agents = sum(1 for agent in agents if agent.status == "active")
        inactive_agents = len(agents) - active_agents
        recently_updated_agents = sum(1 for agent in agents if agent.updated_at >= seven_days_ago)
        categories = Counter(agent.template_type or "Custom" for agent in agents)

        top_agents = sorted(
            agents,
            key=lambda agent: (
                query_counts_by_agent.get(agent.id or "", 0),
                agent.status == "active",
                agent.updated_at,
            ),
            reverse=True,
        )[:5]

        recent_activity = [
            OverviewActivityItem(
                type="agent",
                title=f"{agent.name} updated",
                description=f"{agent.role} is currently {agent.status}.",
                created_at=agent.updated_at,
            )
            for agent in sorted(agents, key=lambda item: item.updated_at, reverse=True)[:5]
        ]

        return OverviewResponse(
            stats=OverviewStats(
                total_agents=len(agents),
                active_agents=active_agents,
                inactive_agents=inactive_agents,
                recently_updated_agents=recently_updated_agents,
                total_chats=len(chats),
                total_messages=sum(message_counts_by_chat.values()),
                queries_30d=sum(query_counts_by_chat.values()),
            ),
            top_agents=[
                OverviewAgentSummary(
                    id=agent.id or "",
                    name=agent.name,
                    role=agent.role,
                    status=agent.status,
                    category=agent.template_type or "Custom",
                    queries_30d=query_counts_by_agent.get(agent.id or "", 0),
                    updated_at=agent.updated_at,
                )
                for agent in top_agents
            ],
            categories=[
                OverviewCategorySummary(name=name, count=count)
                for name, count in sorted(categories.items())
            ],
            recent_activity=recent_activity,
        )
