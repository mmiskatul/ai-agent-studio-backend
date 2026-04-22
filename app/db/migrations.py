from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.agent import AgentDocument
from app.models.chat import ChatDocument, MessageDocument


async def migrate_legacy_chat_storage(db: AsyncIOMotorDatabase) -> None:
    chats = db["chats"]
    legacy_messages = db["messages"]
    agents = db["agents"]

    async for raw_agent in agents.find({}):
        agent = AgentDocument.from_mongo(raw_agent)
        if agent is None:
            continue

        for embedded_chat in agent.chats:
            if not embedded_chat.id:
                continue

            existing_embedded_chat = await chats.find_one({"_id": embedded_chat.id}, projection={"_id": 1})
            if existing_embedded_chat:
                continue

            normalized_chat = ChatDocument(
                id=embedded_chat.id,
                user_id=embedded_chat.user_id,
                agent_id=embedded_chat.agent_id,
                agent_name=agent.name,
                title=embedded_chat.title,
                summary=embedded_chat.summary,
                messages=embedded_chat.messages,
                created_at=embedded_chat.created_at,
                updated_at=embedded_chat.updated_at,
            )
            await chats.insert_one(normalized_chat.to_mongo())

    has_legacy_chat = await chats.find_one({"messages": {"$exists": False}}, projection={"_id": 1})
    if not has_legacy_chat:
        return

    async for raw_chat in chats.find({"messages": {"$exists": False}}):
        chat_id = str(raw_chat["_id"])
        existing_normalized_chat = await chats.find_one(
            {"_id": chat_id, "messages": {"$exists": True}},
            projection={"_id": 1},
        )
        if existing_normalized_chat:
            continue

        agent = AgentDocument.from_mongo(
            await agents.find_one({"_id": raw_chat.get("agent_id"), "user_id": raw_chat.get("user_id")})
        )

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

        normalized_chat = ChatDocument(
            id=chat_id,
            user_id=raw_chat["user_id"],
            agent_id=str(raw_chat["agent_id"]) if raw_chat.get("agent_id") is not None else "",
            agent_name=agent.name if agent is not None else raw_chat.get("agent_name"),
            title=raw_chat.get("title"),
            summary=raw_chat.get("summary"),
            messages=message_docs,
            created_at=raw_chat["created_at"],
            updated_at=raw_chat.get("updated_at", raw_chat["created_at"]),
        )
        await chats.insert_one(normalized_chat.to_mongo())
