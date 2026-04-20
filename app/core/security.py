from datetime import datetime, timedelta, timezone

import secrets

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


class PasswordHasher:
    def __init__(self) -> None:
        self._context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash(self, password: str) -> str:
        return self._context.hash(password)

    def verify(self, password: str, hashed_password: str) -> bool:
        return self._context.verify(password, hashed_password)


class TokenService:
    def create_access_token(self, subject: str) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes,
        )
        payload = {"sub": subject, "exp": expires_at, "typ": "access"}
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def create_session_token(self, subject: str) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.jwt_session_token_expire_days)
        payload = {"sub": subject, "exp": expires_at, "typ": "session"}
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    def decode_subject(self, token: str, token_type: str = "access") -> str | None:
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
            if payload.get("typ") != token_type:
                return None
            subject = payload.get("sub")
            return subject if isinstance(subject, str) else None
        except JWTError:
            return None


class EmailCodeGenerator:
    def generate(self) -> str:
        return f"{secrets.randbelow(1_000_000):06d}"


password_hasher = PasswordHasher()
token_service = TokenService()
email_code_generator = EmailCodeGenerator()
