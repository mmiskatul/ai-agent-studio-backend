from datetime import datetime

from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_agents: int
    active_agents: int
    inactive_agents: int
    recently_updated_agents: int
    total_chats: int
    total_messages: int
    queries_30d: int
    total_leads: int = 0
    total_staff: int = 0


class OverviewAgentSummary(BaseModel):
    id: str
    name: str
    role: str
    status: str
    category: str
    queries_30d: int
    updated_at: datetime


class OverviewCategorySummary(BaseModel):
    name: str
    count: int


class OverviewActivityItem(BaseModel):
    type: str
    title: str
    description: str
    created_at: datetime


class OverviewResponse(BaseModel):
    stats: OverviewStats
    top_agents: list[OverviewAgentSummary]
    categories: list[OverviewCategorySummary]
    recent_activity: list[OverviewActivityItem]
