from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    await db["users"].create_index("email", unique=True)
    await db["agents"].create_index([("user_id", 1), ("created_at", -1)])
    await db["chats"].create_index([("user_id", 1), ("agent_id", 1)], unique=True)
    await db["messages"].create_index([("chat_id", 1), ("created_at", 1)])
    await db["knowledge"].create_index([("user_id", 1), ("agent_id", 1), ("created_at", -1)])
    await db["knowledge_chunks"].create_index([("knowledge_id", 1), ("chunk_index", 1)])
    await db["knowledge_chunks"].create_index([("user_id", 1), ("agent_id", 1)])
