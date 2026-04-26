from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    await db["users"].create_index("email", unique=True)
    await db["agents"].create_index([("user_id", 1), ("created_at", -1)])
    await db["agents"].create_index([("user_id", 1), ("name", 1)])
    await db["agents"].create_index([("user_id", 1), ("is_active", 1)])
    await db["agents"].create_index([("user_id", 1), ("is_active", 1), ("priority", 1)])
    await db["chats"].create_index([("user_id", 1), ("updated_at", -1)])
    await db["chats"].create_index([("user_id", 1), ("agent_id", 1), ("updated_at", -1)])
    await db["chats"].create_index([("user_id", 1), ("agent_id", 1)])
    await db["chats"].create_index([("user_id", 1), ("session_id", 1), ("updated_at", -1)])
    await db["chats"].create_index([("user_id", 1), ("messages.id", 1)])
    await db["messages"].create_index([("user_id", 1), ("session_id", 1), ("created_at", 1)])
    await db["messages"].create_index([("user_id", 1), ("chat_id", 1), ("created_at", 1)])
    await db["memory"].create_index([("user_id", 1), ("session_id", 1)], unique=True)
    await db["templates"].create_index("key", unique=True)
    await db["leads"].create_index([("user_id", 1), ("created_at", -1)])
    await db["leads"].create_index([("user_id", 1), ("agent_id", 1), ("created_at", -1)])
    await db["staff"].create_index([("user_id", 1), ("created_at", -1)])
    await db["staff"].create_index([("user_id", 1), ("email", 1)], unique=True)
