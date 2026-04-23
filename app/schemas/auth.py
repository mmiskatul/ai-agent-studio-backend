from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class SignupRequest(RegisterRequest):
    pass


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class SigninRequest(LoginRequest):
    pass


class EmailValidationRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    password: str = Field(min_length=6)


class RefreshTokenRequest(BaseModel):
    session_token: str = Field(min_length=1)


class AuthUserResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    profile_image: str | None = None


class ProfileLatestAgentResponse(BaseModel):
    id: str
    name: str
    created_at: datetime


class ProfileLatestConversationResponse(BaseModel):
    chat_id: str
    agent_id: str
    agent_name: str
    message_count: int
    updated_at: datetime


class ProfileStatsResponse(BaseModel):
    total_agents: int
    active_agents: int
    inactive_agents: int
    total_messages: int


class ProfileResponse(BaseModel):
    id: str
    email: EmailStr
    display_name: str | None = None
    profile_image: str | None = None
    is_active: bool
    is_email_verified: bool
    created_at: datetime
    updated_at: datetime
    stats: ProfileStatsResponse
    latest_agent: ProfileLatestAgentResponse | None = None
    latest_conversation: ProfileLatestConversationResponse | None = None


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    profile_image: str | None = None


class EmailValidationRequiredResponse(BaseModel):
    email: EmailStr
    message: str


class MessageResponse(BaseModel):
    message: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenResponse(BaseModel):
    access_token: str
    session_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
