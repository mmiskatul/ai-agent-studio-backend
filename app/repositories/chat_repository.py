from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent import AgentDocument
from app.models.base import now_utc
from app.models.chat import ChatDocument, MessageDocument


class ChatRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db["agents"]

    async def create(self, chat: ChatDocument) -> ChatDocument:
        agent = await self._get_agent(chat.agent_id, chat.user_id)
        if agent is None:
            raise ValueError("Agent not found")

        created_chat = chat.model_copy(
            update={
                "id": chat.id or self._create_id("chat"),
                "messages": list(chat.messages),
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
            }
        )
        agent.chats.insert(0, created_chat)
        await self._save_agent_chats(agent)
        return created_chat

    async def get_for_agent(self, user_id: str, agent_id: str) -> ChatDocument | None:
        agent = await self._get_agent(agent_id, user_id)
        if agent is None or not agent.chats:
            return None
        return self._sort_chats(agent.chats)[0]

    async def get_owned_chat(
        self,
        user_id: str,
        agent_id: str,
        chat_id: str,
    ) -> ChatDocument | None:
        agent = await self._get_agent(agent_id, user_id)
        if agent is None:
            return None
        return self._find_chat(agent, chat_id)

    async def list_by_agent(self, user_id: str, agent_id: str) -> list[ChatDocument]:
        agent = await self._get_agent(agent_id, user_id)
        if agent is None:
            return []
        return self._sort_chats(agent.chats)

    async def list_by_user(self, user_id: str) -> list[ChatDocument]:
        cursor = self.collection.find({"user_id": user_id})
        chats: list[ChatDocument] = []
        async for item in cursor:
            agent = AgentDocument.from_mongo(item)
            if agent is None:
                continue
            chats.extend(agent.chats)
        return self._sort_chats(chats)

    async def get_latest_for_user(self, user_id: str) -> ChatDocument | None:
        chats = await self.list_by_user(user_id)
        return chats[0] if chats else None

    async def update_chat_title(self, chat_id: str, title: str) -> ChatDocument | None:
        located = await self._locate_chat(chat_id)
        if located is None:
            return None
        agent, chat = located
        chat.title = title
        chat.updated_at = now_utc()
        await self._save_agent_chats(agent)
        return chat

    async def update_chat_summary(self, chat_id: str, summary: str) -> ChatDocument | None:
        located = await self._locate_chat(chat_id)
        if located is None:
            return None
        agent, chat = located
        chat.summary = summary
        chat.updated_at = now_utc()
        await self._save_agent_chats(agent)
        return chat

    async def count_user_messages_by_chat_ids(
        self,
        chat_ids: list[str],
        since=None,
    ) -> dict[str, int]:
        if not chat_ids:
            return {}
        chat_id_set = set(chat_ids)
        counts: dict[str, int] = {}
        cursor = self.collection.find({"chats.id": {"$in": list(chat_id_set)}})
        async for item in cursor:
            agent = AgentDocument.from_mongo(item)
            if agent is None:
                continue
            for chat in agent.chats:
                if chat.id not in chat_id_set:
                    continue
                counts[chat.id] = sum(
                    1
                    for message in chat.messages
                    if message.sender_type == "user"
                    and (since is None or message.created_at >= since)
                )
        return counts

    async def count_messages_by_chat_ids(self, chat_ids: list[str]) -> dict[str, int]:
        if not chat_ids:
            return {}
        chat_id_set = set(chat_ids)
        counts: dict[str, int] = {}
        cursor = self.collection.find({"chats.id": {"$in": list(chat_id_set)}})
        async for item in cursor:
            agent = AgentDocument.from_mongo(item)
            if agent is None:
                continue
            for chat in agent.chats:
                if chat.id in chat_id_set:
                    counts[chat.id] = len(chat.messages)
        return counts

    async def list_messages(self, chat_id: str) -> list[MessageDocument]:
        located = await self._locate_chat(chat_id)
        if located is None:
            return []
        _, chat = located
        return sorted(chat.messages, key=lambda message: message.created_at)

    async def add_message(self, message: MessageDocument) -> MessageDocument:
        located = await self._locate_chat(message.chat_id)
        if located is None:
            raise ValueError("Chat not found")
        agent, chat = located
        created_message = message.model_copy(
            update={
                "id": message.id or self._create_id("msg"),
                "created_at": message.created_at,
                "updated_at": message.updated_at,
            }
        )
        chat.messages.append(created_message)
        chat.updated_at = now_utc()
        await self._save_agent_chats(agent)
        return created_message

    async def get_message(self, message_id: str) -> MessageDocument | None:
        located = await self._locate_message(message_id)
        if located is None:
            return None
        _, _, message = located
        return message

    async def update_message_content(self, message_id: str, content: str) -> MessageDocument | None:
        located = await self._locate_message(message_id)
        if located is None:
            return None
        agent, chat, message = located
        message.content = content
        message.updated_at = now_utc()
        chat.updated_at = now_utc()
        await self._save_agent_chats(agent)
        return message

    async def delete_message(self, message_id: str) -> bool:
        located = await self._locate_message(message_id)
        if located is None:
            return False
        agent, chat, message = located
        chat.messages = [item for item in chat.messages if item.id != message.id]
        chat.updated_at = now_utc()
        await self._save_agent_chats(agent)
        return True

    async def delete_chat(self, chat_id: str) -> bool:
        located = await self._locate_chat(chat_id)
        if located is None:
            return False
        agent, _ = located
        agent.chats = [chat for chat in agent.chats if chat.id != chat_id]
        await self._save_agent_chats(agent)
        return True

    async def get_next_assistant_message(self, chat_id: str, after_created_at) -> MessageDocument | None:
        messages = await self.list_messages(chat_id)
        assistants = [
            message
            for message in messages
            if message.sender_type == "assistant" and message.created_at > after_created_at
        ]
        assistants.sort(key=lambda message: message.created_at)
        return assistants[0] if assistants else None

    async def get_first_user_message(self, chat_id: str) -> MessageDocument | None:
        messages = await self.list_messages(chat_id)
        users = [message for message in messages if message.sender_type == "user"]
        users.sort(key=lambda message: message.created_at)
        return users[0] if users else None

    async def delete_for_agent(self, agent_id: str) -> None:
        if not ObjectId.is_valid(agent_id):
            return
        await self.collection.update_one(
            {"_id": ObjectId(agent_id)},
            {"$set": {"chats": [], "updated_at": now_utc()}},
        )

    async def _get_agent(self, agent_id: str, user_id: str) -> AgentDocument | None:
        if not ObjectId.is_valid(agent_id):
            return None
        data = await self.collection.find_one({"_id": ObjectId(agent_id), "user_id": user_id})
        return AgentDocument.from_mongo(data)

    async def _locate_chat(self, chat_id: str) -> tuple[AgentDocument, ChatDocument] | None:
        data = await self.collection.find_one({"chats.id": chat_id})
        agent = AgentDocument.from_mongo(data)
        if agent is None:
            return None
        chat = self._find_chat(agent, chat_id)
        if chat is None:
            return None
        return agent, chat

    async def _locate_message(
        self,
        message_id: str,
    ) -> tuple[AgentDocument, ChatDocument, MessageDocument] | None:
        data = await self.collection.find_one({"chats.messages.id": message_id})
        agent = AgentDocument.from_mongo(data)
        if agent is None:
            return None
        for chat in agent.chats:
            for message in chat.messages:
                if message.id == message_id:
                    return agent, chat, message
        return None

    async def _save_agent_chats(self, agent: AgentDocument) -> None:
        serialized_chats = [chat.model_dump(mode="json") for chat in agent.chats]
        await self.collection.update_one(
            {"_id": ObjectId(agent.id)},
            {"$set": {"chats": serialized_chats, "updated_at": now_utc()}},
        )

    def _find_chat(self, agent: AgentDocument, chat_id: str) -> ChatDocument | None:
        for chat in agent.chats:
            if chat.id == chat_id:
                return chat
        return None

    def _sort_chats(self, chats: list[ChatDocument]) -> list[ChatDocument]:
        return sorted(chats, key=lambda chat: (chat.updated_at, chat.created_at), reverse=True)

    def _create_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"
