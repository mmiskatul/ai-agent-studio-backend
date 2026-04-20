from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.base import now_utc
from app.models.user import UserDocument
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[UserDocument]):
    collection_name = "users"
    document_class = UserDocument

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        super().__init__(db)

    async def get_by_email(self, email: str) -> UserDocument | None:
        data = await self.collection.find_one({"email": email.lower()})
        return self.document_class.from_mongo(data)

    async def set_email_validation_code(
        self,
        user_id: str,
        code: str,
        expires_at,
    ) -> UserDocument | None:
        return await self.update_by_id(
            user_id,
            {
                "email_verification_code": code,
                "email_verification_expires_at": expires_at,
            },
        )

    async def mark_email_verified(self, user_id: str) -> UserDocument | None:
        return await self.update_by_id(
            user_id,
            {
                "is_email_verified": True,
                "email_verification_code": None,
                "email_verification_expires_at": None,
            },
        )

    async def set_password_reset_code(
        self,
        user_id: str,
        code: str,
        expires_at,
    ) -> UserDocument | None:
        return await self.update_by_id(
            user_id,
            {
                "password_reset_code": code,
                "password_reset_expires_at": expires_at,
            },
        )

    async def update_password(self, user_id: str, hashed_password: str) -> UserDocument | None:
        return await self.update_by_id(
            user_id,
            {
                "hashed_password": hashed_password,
                "password_reset_code": None,
                "password_reset_expires_at": None,
                "updated_at": now_utc(),
            },
        )
