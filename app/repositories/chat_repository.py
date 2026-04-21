from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import now_utc
from app.models.chat import ChatDocument, MessageDocument
from app.repositories.base import BaseRepository


class ChatRepository(BaseRepository[ChatDocument]):
    collection_name = "chats"
    document_class = ChatDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)
        self.messages = db["messages"]

    async def get_for_agent(self, user_id: str, agent_id: str) -> ChatDocument | None:
        data = await self.collection.find_one(
            {"user_id": user_id, "agent_id": agent_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return self.document_class.from_mongo(data)

    async def get_owned_chat(
        self,
        user_id: str,
        agent_id: str,
        chat_id: str,
    ) -> ChatDocument | None:
        if not ObjectId.is_valid(chat_id):
            return None
        data = await self.collection.find_one(
            {"_id": ObjectId(chat_id), "user_id": user_id, "agent_id": agent_id},
        )
        return self.document_class.from_mongo(data)

    async def list_by_agent(self, user_id: str, agent_id: str) -> list[ChatDocument]:
        cursor = self.collection.find({"user_id": user_id, "agent_id": agent_id}).sort(
            [("updated_at", -1), ("created_at", -1)],
        )
        return [self.document_class.from_mongo(item) async for item in cursor]

    async def list_by_user(self, user_id: str) -> list[ChatDocument]:
        cursor = self.collection.find({"user_id": user_id}).sort("created_at", -1)
        return [self.document_class.from_mongo(item) async for item in cursor]

    async def update_chat_title(self, chat_id: str, title: str) -> ChatDocument | None:
        return await self.update_by_id(chat_id, {"title": title})

    async def count_user_messages_by_chat_ids(
        self,
        chat_ids: list[str],
        since=None,
    ) -> dict[str, int]:
        if not chat_ids:
            return {}

        match: dict = {"chat_id": {"$in": chat_ids}, "sender_type": "user"}
        if since is not None:
            match["created_at"] = {"$gte": since}

        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$chat_id", "count": {"$sum": 1}}},
        ]
        results = self.messages.aggregate(pipeline)
        return {item["_id"]: item["count"] async for item in results}

    async def count_messages_by_chat_ids(self, chat_ids: list[str]) -> dict[str, int]:
        if not chat_ids:
            return {}

        pipeline = [
            {"$match": {"chat_id": {"$in": chat_ids}}},
            {"$group": {"_id": "$chat_id", "count": {"$sum": 1}}},
        ]
        results = self.messages.aggregate(pipeline)
        return {item["_id"]: item["count"] async for item in results}

    async def list_messages(self, chat_id: str) -> list[MessageDocument]:
        cursor = self.messages.find({"chat_id": chat_id}).sort("created_at", 1)
        return [MessageDocument.from_mongo(item) async for item in cursor]

    async def add_message(self, message: MessageDocument) -> MessageDocument:
        payload = message.to_mongo()
        payload.pop("_id", None)
        result = await self.messages.insert_one(payload)
        if ObjectId.is_valid(message.chat_id):
            await self.collection.update_one(
                {"_id": ObjectId(message.chat_id)},
                {"$set": {"updated_at": now_utc()}},
            )
        created = await self.messages.find_one({"_id": result.inserted_id})
        return MessageDocument.from_mongo(created)

    async def get_message(self, message_id: str) -> MessageDocument | None:
        if not ObjectId.is_valid(message_id):
            return None
        data = await self.messages.find_one({"_id": ObjectId(message_id)})
        return MessageDocument.from_mongo(data)

    async def update_message_content(self, message_id: str, content: str) -> MessageDocument | None:
        if not ObjectId.is_valid(message_id):
            return None
        await self.messages.update_one(
            {"_id": ObjectId(message_id)},
            {"$set": {"content": content, "updated_at": now_utc()}},
        )
        return await self.get_message(message_id)

    async def delete_message(self, message_id: str) -> bool:
        if not ObjectId.is_valid(message_id):
            return False
        result = await self.messages.delete_one({"_id": ObjectId(message_id)})
        return result.deleted_count == 1

    async def delete_chat(self, chat_id: str) -> bool:
        if not ObjectId.is_valid(chat_id):
            return False
        await self.messages.delete_many({"chat_id": chat_id})
        result = await self.collection.delete_one({"_id": ObjectId(chat_id)})
        return result.deleted_count == 1

    async def get_next_assistant_message(self, chat_id: str, after_created_at) -> MessageDocument | None:
        data = await self.messages.find_one(
            {
                "chat_id": chat_id,
                "sender_type": "assistant",
                "created_at": {"$gt": after_created_at},
            },
            sort=[("created_at", 1)],
        )
        return MessageDocument.from_mongo(data)

    async def get_first_user_message(self, chat_id: str) -> MessageDocument | None:
        data = await self.messages.find_one(
            {"chat_id": chat_id, "sender_type": "user"},
            sort=[("created_at", 1)],
        )
        return MessageDocument.from_mongo(data)

    async def delete_for_agent(self, agent_id: str) -> None:
        chats = self.collection.find({"agent_id": agent_id})
        chat_ids = [str(chat["_id"]) async for chat in chats]
        if chat_ids:
            await self.messages.delete_many({"chat_id": {"$in": chat_ids}})
        if ObjectId.is_valid(agent_id):
            await self.collection.delete_many({"agent_id": agent_id})
