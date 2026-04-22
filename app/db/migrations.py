from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent import AgentDocument
from app.models.chat import ChatDocument, MessageDocument


async def migrate_legacy_chat_storage(db: AsyncIOMotorDatabase) -> None:
    legacy_chats = db["chats"]
    legacy_messages = db["messages"]
    agents = db["agents"]

    has_legacy_chat = await legacy_chats.find_one({}, projection={"_id": 1})
    if not has_legacy_chat:
        return

    async for raw_agent in agents.find({}):
        agent = AgentDocument.from_mongo(raw_agent)
        if agent is None:
            continue

        existing_chat_ids = {chat.id for chat in agent.chats}
        migrated = False

        async for raw_chat in legacy_chats.find({"agent_id": agent.id, "user_id": agent.user_id}):
            chat_id = str(raw_chat["_id"])
            if chat_id in existing_chat_ids:
                continue

            message_docs: list[MessageDocument] = []
            cursor = legacy_messages.find({"chat_id": chat_id}).sort("created_at", 1)
            async for raw_message in cursor:
                message_docs.append(
                    MessageDocument(
                        id=str(raw_message["_id"]),
                        chat_id=chat_id,
                        sender_type=raw_message["sender_type"],
                        content=raw_message["content"],
                        created_at=raw_message["created_at"],
                        updated_at=raw_message.get("updated_at", raw_message["created_at"]),
                    )
                )

            agent.chats.append(
                ChatDocument(
                    id=chat_id,
                    user_id=raw_chat["user_id"],
                    agent_id=raw_chat["agent_id"],
                    title=raw_chat.get("title"),
                    summary=raw_chat.get("summary"),
                    messages=message_docs,
                    created_at=raw_chat["created_at"],
                    updated_at=raw_chat.get("updated_at", raw_chat["created_at"]),
                )
            )
            migrated = True

        if migrated:
            serialized_chats = [chat.model_dump(mode="json") for chat in agent.chats]
            await agents.update_one(
                {"_id": raw_agent["_id"]},
                {"$set": {"chats": serialized_chats}},
            )
