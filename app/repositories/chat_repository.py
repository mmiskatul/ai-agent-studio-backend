from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent import AgentDocument
from app.models.base import now_utc
from app.models.chat import ChatDocument, ChatMemoryDocument, MessageDocument


class ChatRepository:
    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self.collection = db["chats"]
        self.agents_collection = db["agents"]

    async def create(self, chat: ChatDocument) -> ChatDocument:
        agent = await self._get_agent(chat.agent_id, chat.user_id)

        created_chat = chat.model_copy(
            update={
                "id": chat.id or self._create_id("chat"),
                "current_agent_id": chat.current_agent_id or chat.agent_id,
                "agent_name": chat.agent_name or (agent.name if agent else None),
                "messages": list(chat.messages),
                "created_at": chat.created_at,
                "updated_at": chat.updated_at,
            }
        )
        await self.collection.insert_one(created_chat.to_mongo())
        return created_chat

    async def get_for_agent(self, user_id: str, agent_id: str) -> ChatDocument | None:
        data = await self.collection.find_one(
            {"user_id": user_id, "agent_id": agent_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return ChatDocument.from_mongo(data)

    async def get_owned_chat(
        self,
        user_id: str,
        agent_id: str,
        chat_id: str,
    ) -> ChatDocument | None:
        data = await self.collection.find_one(
            {"_id": chat_id, "user_id": user_id, "agent_id": agent_id},
        )
        return ChatDocument.from_mongo(data)

    async def get_by_id_for_user(self, user_id: str, chat_id: str) -> ChatDocument | None:
        data = await self.collection.find_one({"_id": chat_id, "user_id": user_id})
        return ChatDocument.from_mongo(data)

    async def get_latest_for_session(self, user_id: str, session_id: str) -> ChatDocument | None:
        data = await self.collection.find_one(
            {"user_id": user_id, "session_id": session_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return ChatDocument.from_mongo(data)

    async def list_by_session(self, user_id: str, session_id: str) -> list[ChatDocument]:
        cursor = self.collection.find({"user_id": user_id, "session_id": session_id}).sort(
            [("updated_at", -1), ("created_at", -1)]
        )
        return [chat async for chat in self._iterate_chats(cursor)]

    async def list_by_agent(self, user_id: str, agent_id: str) -> list[ChatDocument]:
        cursor = self.collection.find({"user_id": user_id, "agent_id": agent_id}).sort(
            [("updated_at", -1), ("created_at", -1)]
        )
        return [chat async for chat in self._iterate_chats(cursor)]

    async def list_by_user(self, user_id: str) -> list[ChatDocument]:
        cursor = self.collection.find({"user_id": user_id}).sort([("updated_at", -1), ("created_at", -1)])
        return [chat async for chat in self._iterate_chats(cursor)]

    async def get_latest_for_user(self, user_id: str) -> ChatDocument | None:
        data = await self.collection.find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return ChatDocument.from_mongo(data)

    async def update_chat_title(self, chat_id: str, title: str) -> ChatDocument | None:
        located = await self._locate_chat(chat_id)
        if located is None:
            return None
        chat = located
        chat.title = title
        chat.updated_at = now_utc()
        await self._save_chat(chat)
        return chat

    async def update_chat_agent(
        self,
        chat_id: str,
        *,
        agent_id: str,
        agent_name: str,
    ) -> ChatDocument | None:
        located = await self._locate_chat(chat_id)
        if located is None:
            return None
        chat = located
        chat.agent_id = agent_id
        chat.current_agent_id = agent_id
        chat.agent_name = agent_name
        chat.updated_at = now_utc()
        await self._save_chat(chat)
        return chat

    async def update_chat_summary(self, chat_id: str, summary: str) -> ChatDocument | None:
        located = await self._locate_chat(chat_id)
        if located is None:
            return None
        chat = located
        chat.summary = summary
        chat.updated_at = now_utc()
        await self._save_chat(chat)
        return chat

    async def update_chat_memory(
        self,
        chat_id: str,
        memory: ChatMemoryDocument,
    ) -> ChatDocument | None:
        located = await self._locate_chat(chat_id)
        if located is None:
            return None
        chat = located
        chat.memory = memory
        chat.updated_at = now_utc()
        await self.collection.update_one(
            {"_id": chat_id},
            {
                "$set": {
                    "memory": memory.model_dump(exclude_none=True),
                    "updated_at": chat.updated_at,
                },
                "$unset": {"summary": ""},
            },
        )
        chat.summary = None
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
        cursor = self.collection.find({"_id": {"$in": list(chat_id_set)}})
        async for chat in self._iterate_chats(cursor):
            if not chat.id:
                continue
            counts[chat.id] = sum(
                1
                for message in chat.messages
                if message.sender_type == "user"
                and (
                    since is None
                    or self._normalize_datetime(message.created_at)
                    >= self._normalize_datetime(since)
                )
            )
        return counts

    async def count_messages_by_chat_ids(self, chat_ids: list[str]) -> dict[str, int]:
        if not chat_ids:
            return {}
        chat_id_set = set(chat_ids)
        counts: dict[str, int] = {}
        cursor = self.collection.find({"_id": {"$in": list(chat_id_set)}})
        async for chat in self._iterate_chats(cursor):
            if chat.id in chat_id_set:
                counts[chat.id] = len(chat.messages)
        return counts

    async def list_messages(self, chat_id: str) -> list[MessageDocument]:
        chat = await self._locate_chat(chat_id)
        if chat is None:
            return []
        return sorted(
            chat.messages,
            key=lambda message: self._normalize_datetime(message.created_at),
        )

    async def add_message(self, message: MessageDocument) -> MessageDocument:
        chat = await self._locate_chat(message.chat_id)
        if chat is None:
            raise ValueError("Chat not found")
        created_message = message.model_copy(
            update={
                "id": message.id or self._create_id("msg"),
                "created_at": message.created_at,
                "updated_at": message.updated_at,
            }
        )
        chat.messages.append(created_message)
        chat.updated_at = now_utc()
        await self._save_chat(chat)
        return created_message

    async def get_message(self, message_id: str) -> MessageDocument | None:
        located = await self._locate_message(message_id)
        if located is None:
            return None
        _, message = located
        return message

    async def update_message_content(self, message_id: str, content: str) -> MessageDocument | None:
        located = await self._locate_message(message_id)
        if located is None:
            return None
        chat, message = located
        message.content = content
        message.updated_at = now_utc()
        chat.updated_at = now_utc()
        await self._save_chat(chat)
        return message

    async def delete_message(self, message_id: str) -> bool:
        located = await self._locate_message(message_id)
        if located is None:
            return False
        chat, message = located
        chat.messages = [item for item in chat.messages if item.id != message.id]
        chat.updated_at = now_utc()
        await self._save_chat(chat)
        return True

    async def delete_chat(self, chat_id: str) -> bool:
        result = await self.collection.delete_one({"_id": chat_id})
        return result.deleted_count == 1

    async def get_next_assistant_message(self, chat_id: str, after_created_at) -> MessageDocument | None:
        normalized_after_created_at = self._normalize_datetime(after_created_at)
        messages = await self.list_messages(chat_id)
        assistants = [
            message
            for message in messages
            if message.sender_type == "assistant"
            and self._normalize_datetime(message.created_at) > normalized_after_created_at
        ]
        assistants.sort(key=lambda message: self._normalize_datetime(message.created_at))
        return assistants[0] if assistants else None

    async def get_first_user_message(self, chat_id: str) -> MessageDocument | None:
        messages = await self.list_messages(chat_id)
        users = [message for message in messages if message.sender_type == "user"]
        users.sort(key=lambda message: self._normalize_datetime(message.created_at))
        return users[0] if users else None

    async def delete_for_agent(self, agent_id: str) -> None:
        await self.collection.delete_many({"agent_id": agent_id})

    async def _get_agent(self, agent_id: str, user_id: str) -> AgentDocument | None:
        agent_key = ObjectId(agent_id) if ObjectId.is_valid(agent_id) else agent_id
        data = await self.agents_collection.find_one({"_id": agent_key, "user_id": user_id})
        return AgentDocument.from_mongo(data)

    async def _locate_chat(self, chat_id: str) -> ChatDocument | None:
        data = await self.collection.find_one({"_id": chat_id})
        return ChatDocument.from_mongo(data)

    async def _locate_message(
        self,
        message_id: str,
    ) -> tuple[ChatDocument, MessageDocument] | None:
        data = await self.collection.find_one({"messages.id": message_id})
        chat = ChatDocument.from_mongo(data)
        if chat is None:
            return None
        for message in chat.messages:
            if message.id == message_id:
                return chat, message
        return None

    async def _save_chat(self, chat: ChatDocument) -> None:
        payload = chat.to_mongo()
        payload.pop("_id", None)
        await self.collection.update_one(
            {"_id": chat.id},
            {"$set": payload},
        )

    async def _iterate_chats(self, cursor):
        async for item in cursor:
            chat = ChatDocument.from_mongo(item)
            if chat is not None:
                yield chat

    def _normalize_datetime(self, value: Any) -> datetime:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.min.replace(tzinfo=timezone.utc)
        if not isinstance(value, datetime):
            return datetime.min.replace(tzinfo=timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _create_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"
