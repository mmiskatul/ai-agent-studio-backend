from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_indexes(db: AsyncIOMotorDatabase) -> None:
    await db["users"].create_index("email", unique=True)
    await db["agents"].create_index([("user_id", 1), ("created_at", -1)])
    await db["agents"].create_index([("user_id", 1), ("name", 1)])
    await db["agents"].create_index([("user_id", 1), ("is_active", 1)])
    await db["chats"].create_index([("user_id", 1), ("updated_at", -1)])
    await db["chats"].create_index([("user_id", 1), ("agent_id", 1), ("updated_at", -1)])
    await db["chats"].create_index([("user_id", 1), ("agent_id", 1)])
    await db["chats"].create_index([("user_id", 1), ("messages.id", 1)])
