import asyncio
from collections import Counter
from datetime import datetime, timedelta, timezone

from app.models.base import now_utc
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.repositories.chat_repository import ChatRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.overview import (
    OverviewActivityItem,
    OverviewAgentSummary,
    OverviewCategorySummary,
    OverviewResponse,
    OverviewStats,
)


def as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class OverviewService:
    def __init__(
        self,
        agents: AgentRepository,
        chats: ChatRepository,
        messages: MessageRepository | None = None,
    ) -> None:
        self._agents = agents
        self._chats = chats
        self._messages = messages

    async def get_overview(self, user: UserDocument) -> OverviewResponse:
        user_id = user.id or ""
        agent_summaries, chats = await asyncio.gather(
            self._agents.list_summaries_by_user(user_id),
            self._chats.list_by_user(user_id, include_messages=False),
        )
        agents = [self._normalize_agent_summary(item) for item in agent_summaries]
        chat_ids = [chat.id or "" for chat in chats if chat.id]
        chat_agent_map = {chat.id or "": chat.agent_id for chat in chats if chat.id}
        thirty_days_ago = now_utc() - timedelta(days=30)
        seven_days_ago = now_utc() - timedelta(days=7)

        message_counts_by_chat, query_counts_by_chat = await asyncio.gather(
            self._chats.count_messages_by_chat_ids(chat_ids),
            self._chats.count_user_messages_by_chat_ids(chat_ids, since=thirty_days_ago),
        )

        query_counts_by_agent: dict[str, int] = {}
        for chat_id, count in query_counts_by_chat.items():
            agent_id = chat_agent_map.get(chat_id)
            if agent_id:
                query_counts_by_agent[agent_id] = query_counts_by_agent.get(agent_id, 0) + count

        standalone_query_counts_by_agent: dict[str, int] = {}
        standalone_message_count = 0
        if self._messages is not None:
            standalone_query_counts_by_agent, standalone_message_count = await asyncio.gather(
                self._messages.count_user_messages_by_agent(
                    user_id,
                    since=thirty_days_ago,
                ),
                self._messages.count_messages_by_user(user_id),
            )
            for agent_id, count in standalone_query_counts_by_agent.items():
                query_counts_by_agent[agent_id] = query_counts_by_agent.get(agent_id, 0) + count

        active_agents = sum(1 for agent in agents if agent["status"] == "enabled")
        inactive_agents = len(agents) - active_agents
        recently_updated_agents = sum(
            1 for agent in agents if as_aware_utc(agent["updated_at"]) >= seven_days_ago
        )
        categories = Counter(agent["category"] for agent in agents)

        top_agents = sorted(
            agents,
            key=lambda agent: (
                query_counts_by_agent.get(agent["id"], 0),
                agent["status"] == "enabled",
                as_aware_utc(agent["updated_at"]),
            ),
            reverse=True,
        )[:5]

        recent_activity = [
            OverviewActivityItem(
                type="agent",
                title=f"{agent['name']} updated",
                description=f"{agent['role']} is currently {agent['status']}.",
                created_at=as_aware_utc(agent["updated_at"]),
            )
            for agent in sorted(agents, key=lambda item: as_aware_utc(item["updated_at"]), reverse=True)[
                :5
            ]
        ]

        return OverviewResponse(
            stats=OverviewStats(
                total_agents=len(agents),
                active_agents=active_agents,
                inactive_agents=inactive_agents,
                recently_updated_agents=recently_updated_agents,
                total_chats=len(chats),
                total_messages=sum(message_counts_by_chat.values()) + standalone_message_count,
                queries_30d=sum(query_counts_by_chat.values())
                + sum(standalone_query_counts_by_agent.values()),
            ),
            top_agents=[
                OverviewAgentSummary(
                    id=agent["id"],
                    name=agent["name"],
                    role=agent["role"],
                    status=agent["status"],
                    category=agent["category"],
                    queries_30d=query_counts_by_agent.get(agent["id"], 0),
                    updated_at=as_aware_utc(agent["updated_at"]),
                )
                for agent in top_agents
            ],
            categories=[
                OverviewCategorySummary(name=name, count=count)
                for name, count in sorted(categories.items())
            ],
            recent_activity=recent_activity,
        )

    def _normalize_agent_summary(self, item: dict) -> dict[str, object]:
        return {
            "id": str(item.get("_id") or ""),
            "name": str(item.get("name") or ""),
            "role": str(item.get("role") or ""),
            "status": str(item.get("status") or "disabled"),
            "category": str(item.get("template_type") or "Custom"),
            "updated_at": item.get("updated_at") or now_utc(),
        }
