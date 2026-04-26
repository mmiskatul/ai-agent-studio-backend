from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.models.agent import AgentDocument
from app.models.base import now_utc
from app.models.chat import ChatDocument, ChatMemoryDocument, MessageDocument
from app.repositories.base import log_slow_mongo_query, start_mongo_timer

CHAT_METADATA_PROJECTION = {"messages": 0}


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

    async def get_for_agent(
        self,
        user_id: str,
        agent_id: str,
        *,
        include_messages: bool = True,
    ) -> ChatDocument | None:
        filters = {"user_id": user_id, "agent_id": agent_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(
            filters,
            self._chat_projection(include_messages),
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        log_slow_mongo_query(
            collection_name="chats",
            operation="get_for_agent",
            started_at=started_at,
            filters=filters,
        )
        return ChatDocument.from_mongo(data)

    async def get_owned_chat(
        self,
        user_id: str,
        agent_id: str,
        chat_id: str,
        *,
        include_messages: bool = True,
    ) -> ChatDocument | None:
        filters = {"_id": chat_id, "user_id": user_id, "agent_id": agent_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(
            filters,
            self._chat_projection(include_messages),
        )
        log_slow_mongo_query(
            collection_name="chats",
            operation="get_owned_chat",
            started_at=started_at,
            filters=filters,
        )
        return ChatDocument.from_mongo(data)

    async def get_by_id_for_user(
        self,
        user_id: str,
        chat_id: str,
        *,
        include_messages: bool = True,
    ) -> ChatDocument | None:
        filters = {"_id": chat_id, "user_id": user_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(filters, self._chat_projection(include_messages))
        log_slow_mongo_query(
            collection_name="chats",
            operation="get_by_id_for_user",
            started_at=started_at,
            filters=filters,
        )
        return ChatDocument.from_mongo(data)

    async def get_latest_for_session(
        self,
        user_id: str,
        session_id: str,
        *,
        include_messages: bool = True,
    ) -> ChatDocument | None:
        filters = {"user_id": user_id, "session_id": session_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(
            filters,
            self._chat_projection(include_messages),
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        log_slow_mongo_query(
            collection_name="chats",
            operation="get_latest_for_session",
            started_at=started_at,
            filters=filters,
        )
        return ChatDocument.from_mongo(data)

    async def list_by_session(
        self,
        user_id: str,
        session_id: str,
        *,
        include_messages: bool = True,
    ) -> list[ChatDocument]:
        filters = {"user_id": user_id, "session_id": session_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters, self._chat_projection(include_messages)).sort(
            [("updated_at", -1), ("created_at", -1)]
        )
        chats = [chat async for chat in self._iterate_chats(cursor)]
        log_slow_mongo_query(
            collection_name="chats",
            operation="list_by_session",
            started_at=started_at,
            filters=filters,
        )
        return chats

    async def list_by_agent(
        self,
        user_id: str,
        agent_id: str,
        *,
        include_messages: bool = True,
    ) -> list[ChatDocument]:
        filters = {"user_id": user_id, "agent_id": agent_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters, self._chat_projection(include_messages)).sort(
            [("updated_at", -1), ("created_at", -1)]
        )
        chats = [chat async for chat in self._iterate_chats(cursor)]
        log_slow_mongo_query(
            collection_name="chats",
            operation="list_by_agent",
            started_at=started_at,
            filters=filters,
        )
        return chats

    async def list_by_user(self, user_id: str, *, include_messages: bool = True) -> list[ChatDocument]:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        cursor = self.collection.find(filters, self._chat_projection(include_messages)).sort(
            [("updated_at", -1), ("created_at", -1)]
        )
        chats = [chat async for chat in self._iterate_chats(cursor)]
        log_slow_mongo_query(
            collection_name="chats",
            operation="list_by_user",
            started_at=started_at,
            filters=filters,
        )
        return chats

    async def get_latest_for_user(
        self,
        user_id: str,
        *,
        include_messages: bool = True,
    ) -> ChatDocument | None:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(
            filters,
            self._chat_projection(include_messages),
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        log_slow_mongo_query(
            collection_name="chats",
            operation="get_latest_for_user",
            started_at=started_at,
            filters=filters,
        )
        return ChatDocument.from_mongo(data)

    async def count_by_user(self, user_id: str) -> int:
        filters = {"user_id": user_id}
        started_at = start_mongo_timer()
        count = await self.collection.count_documents(filters)
        log_slow_mongo_query(
            collection_name="chats",
            operation="count_by_user",
            started_at=started_at,
            filters=filters,
        )
        return count

    async def update_chat_title(self, chat_id: str, title: str) -> ChatDocument | None:
        updated_at = now_utc()
        data = await self.collection.find_one_and_update(
            {"_id": chat_id},
            {"$set": {"title": title, "updated_at": updated_at}},
            return_document=ReturnDocument.AFTER,
        )
        return ChatDocument.from_mongo(data)

    async def get_owned_chat_by_message(
        self,
        user_id: str,
        agent_id: str,
        message_id: str,
    ) -> ChatDocument | None:
        data = await self.collection.find_one(
            {"user_id": user_id, "agent_id": agent_id, "messages.id": message_id},
        )
        return ChatDocument.from_mongo(data)

    async def update_chat_agent(
        self,
        chat_id: str,
        *,
        agent_id: str,
        agent_name: str,
    ) -> ChatDocument | None:
        updated_at = now_utc()
        data = await self.collection.find_one_and_update(
            {"_id": chat_id},
            {
                "$set": {
                    "agent_id": agent_id,
                    "current_agent_id": agent_id,
                    "agent_name": agent_name,
                    "updated_at": updated_at,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return ChatDocument.from_mongo(data)

    async def update_chat_summary(self, chat_id: str, summary: str) -> ChatDocument | None:
        updated_at = now_utc()
        data = await self.collection.find_one_and_update(
            {"_id": chat_id},
            {"$set": {"summary": summary, "updated_at": updated_at}},
            return_document=ReturnDocument.AFTER,
        )
        return ChatDocument.from_mongo(data)

    async def update_chat_memory(
        self,
        chat_id: str,
        memory: ChatMemoryDocument,
    ) -> ChatDocument | None:
        updated_at = now_utc()
        data = await self.collection.find_one_and_update(
            {"_id": chat_id},
            {
                "$set": {
                    "memory": memory.model_dump(exclude_none=True),
                    "updated_at": updated_at,
                },
                "$unset": {"summary": ""},
            },
            return_document=ReturnDocument.AFTER,
        )
        return ChatDocument.from_mongo(data)

    async def count_user_messages_by_chat_ids(
        self,
        chat_ids: list[str],
        since=None,
    ) -> dict[str, int]:
        if not chat_ids:
            return {}
        match_messages: dict[str, object] = {"input": "$messages", "as": "message", "cond": {"$eq": ["$$message.sender_type", "user"]}}
        if since is not None:
            match_messages["cond"] = {
                "$and": [
                    {"$eq": ["$$message.sender_type", "user"]},
                    {"$gte": ["$$message.created_at", self._normalize_datetime(since)]},
                ]
            }

        pipeline = [
            {"$match": {"_id": {"$in": chat_ids}}},
            {
                "$project": {
                    "_id": 1,
                    "count": {
                        "$size": {
                            "$filter": match_messages,
                        }
                    },
                }
            },
        ]

        counts: dict[str, int] = {}
        started_at = start_mongo_timer()
        async for item in self.collection.aggregate(pipeline):
            chat_id = item.get("_id")
            if isinstance(chat_id, str):
                counts[chat_id] = int(item.get("count", 0))
        log_slow_mongo_query(
            collection_name="chats",
            operation="count_user_messages_by_chat_ids",
            started_at=started_at,
            filters={"_id": "chat_ids"},
        )
        return counts

    async def count_messages_by_chat_ids(self, chat_ids: list[str]) -> dict[str, int]:
        if not chat_ids:
            return {}
        pipeline = [
            {"$match": {"_id": {"$in": chat_ids}}},
            {"$project": {"_id": 1, "count": {"$size": "$messages"}}},
        ]
        counts: dict[str, int] = {}
        started_at = start_mongo_timer()
        async for item in self.collection.aggregate(pipeline):
            chat_id = item.get("_id")
            if isinstance(chat_id, str):
                counts[chat_id] = int(item.get("count", 0))
        log_slow_mongo_query(
            collection_name="chats",
            operation="count_messages_by_chat_ids",
            started_at=started_at,
            filters={"_id": "chat_ids"},
        )
        return counts

    async def list_messages(self, chat_id: str) -> list[MessageDocument]:
        filters = {"_id": chat_id}
        started_at = start_mongo_timer()
        data = await self.collection.find_one(filters, {"messages": 1})
        log_slow_mongo_query(
            collection_name="chats",
            operation="list_messages",
            started_at=started_at,
            filters=filters,
        )
        if not data:
            return []
        messages = [
            MessageDocument.model_validate(message)
            for message in data.get("messages", [])
        ]
        return sorted(
            messages,
            key=lambda message: self._normalize_datetime(message.created_at),
        )

    async def add_message(self, message: MessageDocument) -> MessageDocument:
        created_message = message.model_copy(
            update={
                "id": message.id or self._create_id("msg"),
                "created_at": message.created_at,
                "updated_at": message.updated_at,
            }
        )
        result = await self.collection.update_one(
            {"_id": message.chat_id},
            {
                "$push": {"messages": created_message.model_dump(exclude_none=True)},
                "$set": {"updated_at": now_utc()},
            },
        )
        if result.matched_count == 0:
            raise ValueError("Chat not found")
        return created_message

    async def get_message(self, message_id: str) -> MessageDocument | None:
        message = await self._get_projected_message(message_id)
        if message is None:
            return None
        return message

    async def update_message_content(self, message_id: str, content: str) -> MessageDocument | None:
        updated_at = now_utc()
        result = await self.collection.update_one(
            {"messages.id": message_id},
            {
                "$set": {
                    "messages.$.content": content,
                    "messages.$.updated_at": updated_at,
                    "updated_at": updated_at,
                }
            },
        )
        if result.matched_count == 0:
            return None
        return await self._get_projected_message(message_id)

    async def delete_message(self, message_id: str) -> bool:
        result = await self.collection.update_one(
            {"messages.id": message_id},
            {
                "$pull": {"messages": {"id": message_id}},
                "$set": {"updated_at": now_utc()},
            },
        )
        return result.modified_count == 1

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

    async def _get_projected_message(self, message_id: str) -> MessageDocument | None:
        data = await self.collection.find_one(
            {"messages.id": message_id},
            {"messages": {"$elemMatch": {"id": message_id}}},
        )
        if not data:
            return None
        messages = data.get("messages") or []
        if not messages:
            return None
        return MessageDocument.model_validate(messages[0])

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

    def _chat_projection(self, include_messages: bool) -> dict[str, int] | None:
        return None if include_messages else CHAT_METADATA_PROJECTION

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
