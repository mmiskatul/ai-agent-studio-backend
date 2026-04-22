from datetime import datetime

from pydantic import EmailStr

from app.models.base import MongoDocument


class UserDocument(MongoDocument):
    email: EmailStr
    display_name: str | None = None
    profile_image: str | None = None
    hashed_password: str
    is_active: bool = True
    is_email_verified: bool = False
    email_verification_code: str | None = None
    email_verification_expires_at: datetime | None = None
    password_reset_code: str | None = None
    password_reset_expires_at: datetime | None = None
