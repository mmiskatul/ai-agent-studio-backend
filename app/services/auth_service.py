import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from app.core.config import settings
from app.core.security import email_code_generator, password_hasher, token_service
from app.models.user import UserDocument
from app.repositories.agent_repository import AgentRepository
from app.utils.ids import create_id
from app.repositories.chat_repository import ChatRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AccessTokenResponse,
    ChangePasswordRequest,
    EmailValidationRequiredResponse,
    EmailValidationRequest,
    ForgotPasswordRequest,
    ForgotPasswordVerifyRequest,
    LoginRequest,
    MessageResponse,
    ProfileLatestAgentResponse,
    ProfileLatestConversationResponse,
    ProfileResponse,
    ProfileStatsResponse,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.services.email_service import email_sender


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        agents: AgentRepository | None = None,
        chats: ChatRepository | None = None,
    ) -> None:
        self._users = users
        self._agents = agents
        self._chats = chats

    async def register(self, payload: RegisterRequest) -> EmailValidationRequiredResponse:
        email = payload.email.lower()
        existing = await self._users.get_by_email(email)
        if existing is not None and existing.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )

        code = email_code_generator.generate()
        expires_at = self._code_expiry()

        if existing is None:
            user = await self._users.create(
                UserDocument(
                    id=create_id("user"),
                    email=email,
                    hashed_password=password_hasher.hash(payload.password),
                    email_verification_code=code,
                    email_verification_expires_at=expires_at,
                ),
            )
        else:
            user = await self._users.update_password(
                existing.id or "",
                password_hasher.hash(payload.password),
            )
            user = await self._users.set_email_validation_code(user.id or "", code, expires_at)

        await email_sender.send_validation_code(email, code, "account signup")
        return self._email_validation_response(user, code, "Email validation code sent")

    async def verify_email(self, payload: EmailValidationRequest) -> TokenResponse:
        user = await self._users.get_by_email(payload.email.lower())
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        self._assert_valid_code(
            submitted_code=payload.code,
            stored_code=user.email_verification_code,
            expires_at=user.email_verification_expires_at,
        )

        verified_user = await self._users.mark_email_verified(user.id or "")
        if verified_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return self._token_response(verified_user)

    async def login(self, payload: LoginRequest) -> TokenResponse:
        user = await self._users.get_by_email(payload.email.lower())
        if user is None or not password_hasher.verify(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_email_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email validation is required before sign in",
            )
        return self._token_response(user)

    async def forgot_password(
        self,
        payload: ForgotPasswordRequest,
    ) -> EmailValidationRequiredResponse:
        email = payload.email.lower()
        user = await self._users.get_by_email(email)
        code = email_code_generator.generate()

        if user is not None:
            user = await self._users.set_password_reset_code(user.id or "", code, self._code_expiry())
            await email_sender.send_validation_code(email, code, "password reset")

        return self._email_validation_response(
            user,
            code if user is not None else None,
            "If the email exists, a password reset validation code was generated",
            email=email,
        )

    async def verify_forgot_password(
        self,
        payload: ForgotPasswordVerifyRequest,
    ) -> MessageResponse:
        user = await self._users.get_by_email(payload.email.lower())
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        self._assert_valid_code(
            submitted_code=payload.code,
            stored_code=user.password_reset_code,
            expires_at=user.password_reset_expires_at,
        )

        return MessageResponse(message="Reset code verified")

    async def reset_password(self, payload: ResetPasswordRequest) -> MessageResponse:
        user = await self._users.get_by_email(payload.email.lower())
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        self._assert_valid_code(
            submitted_code=payload.code,
            stored_code=user.password_reset_code,
            expires_at=user.password_reset_expires_at,
        )

        updated_user = await self._users.update_password(
            user.id or "",
            password_hasher.hash(payload.password),
        )
        if updated_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        await self._users.update_by_id(user.id or "", {"session_version": user.session_version + 1})
        return MessageResponse(message="Password updated successfully")

    async def change_password(self, user: UserDocument, payload: ChangePasswordRequest) -> MessageResponse:
        if not password_hasher.verify(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        updated_user = await self._users.update_by_id(
            user.id or "",
            {
                "hashed_password": password_hasher.hash(payload.new_password),
                "session_version": user.session_version + 1,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        if updated_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return MessageResponse(message="Password changed successfully. All active sessions have been signed out.")

    async def revoke_all_sessions(self, user: UserDocument) -> MessageResponse:
        updated_user = await self._users.update_by_id(
            user.id or "",
            {
                "session_version": user.session_version + 1,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        if updated_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return MessageResponse(message="All active sessions have been signed out")

    async def refresh_access_token(self, payload: RefreshTokenRequest) -> AccessTokenResponse:
        decoded_session = token_service.decode_session(payload.session_token)
        if decoded_session is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")
        user_id, session_version = decoded_session

        user = await self.get_user_by_id(user_id)
        if user is None or not user.is_active or session_version != user.session_version:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

        return AccessTokenResponse(access_token=token_service.create_access_token(user.id or "", session_version=user.session_version))
    async def get_user_by_id(self, user_id: str) -> UserDocument | None:
        return await self._users.get_by_id(user_id)

    async def get_profile(self, user: UserDocument) -> ProfileResponse:
        agent_summaries, chats = await asyncio.gather(
            self._agents.list_summaries_by_user(user.id or "")
            if self._agents
            else asyncio.sleep(0, result=[]),
            self._chats.list_by_user(user.id or "", include_messages=False)
            if self._chats
            else asyncio.sleep(0, result=[]),
        )
        agents = [self._normalize_agent_summary(item) for item in agent_summaries]
        message_counts_by_chat = (
            await self._chats.count_messages_by_chat_ids([chat.id or "" for chat in chats if chat.id])
            if self._chats
            else {}
        )
        latest_agent = agents[0] if agents else None
        latest_chat = chats[0] if chats else None

        return ProfileResponse(
            id=user.id or "",
            email=user.email,
            display_name=user.display_name,
            profile_image=user.profile_image,
            is_active=user.is_active,
            is_email_verified=user.is_email_verified,
            created_at=user.created_at,
            updated_at=user.updated_at,
            stats=ProfileStatsResponse(
                total_agents=len(agents),
                active_agents=sum(1 for agent in agents if agent["status"] == "enabled"),
                inactive_agents=sum(1 for agent in agents if agent["status"] != "enabled"),
                total_messages=sum(message_counts_by_chat.values()),
            ),
            latest_agent=(
                ProfileLatestAgentResponse(
                    id=latest_agent["id"],
                    name=latest_agent["name"],
                    created_at=latest_agent["created_at"],
                )
                if latest_agent
                else None
            ),
            latest_conversation=(
                ProfileLatestConversationResponse(
                    chat_id=latest_chat.id or "",
                    agent_id=latest_chat.agent_id,
                    agent_name=next(
                        (agent["name"] for agent in agents if agent["id"] == latest_chat.agent_id),
                        "Unknown Agent",
                    ),
                    message_count=message_counts_by_chat.get(latest_chat.id or "", 0),
                    updated_at=latest_chat.updated_at,
                )
                if latest_chat
                else None
            ),
        )

    async def update_profile(
        self,
        user: UserDocument,
        payload: ProfileUpdateRequest,
    ) -> ProfileResponse:
        updated_user = await self._users.update_by_id(
            user.id or "",
            {
                "display_name": payload.display_name.strip() if payload.display_name else None,
                "profile_image": payload.profile_image,
            },
        )
        if updated_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return await self.get_profile(updated_user)

    def _token_response(self, user: UserDocument) -> TokenResponse:
        access_token = token_service.create_access_token(subject=user.id or "", session_version=user.session_version)
        session_token = token_service.create_session_token(subject=user.id or "", session_version=user.session_version)
        return TokenResponse(
            access_token=access_token,
            session_token=session_token,
            user={
                "id": user.id or "",
                "email": user.email,
                "display_name": user.display_name,
                "profile_image": user.profile_image,
            },
        )

    def _email_validation_response(
        self,
        user: UserDocument | None,
        code: str | None,
        message: str,
        email: str | None = None,
    ) -> EmailValidationRequiredResponse:
        return EmailValidationRequiredResponse(
            email=email or user.email,
            message=message,
        )

    def _normalize_agent_summary(self, item: dict) -> dict[str, object]:
        return {
            "id": str(item.get("_id") or ""),
            "name": str(item.get("name") or ""),
            "status": str(item.get("status") or "disabled"),
            "created_at": item.get("created_at") or datetime.now(timezone.utc),
        }

    def _code_expiry(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(minutes=settings.email_code_expire_minutes)

    def _assert_valid_code(
        self,
        submitted_code: str,
        stored_code: str | None,
        expires_at: datetime | None,
    ) -> None:
        now = datetime.now(timezone.utc)
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if stored_code is None or expires_at is None or expires_at < now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Validation code expired")

        if submitted_code != stored_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid validation code")
