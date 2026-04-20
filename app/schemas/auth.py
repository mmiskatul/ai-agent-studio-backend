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


class RefreshTokenRequest(BaseModel):
    session_token: str = Field(min_length=1)


class AuthUserResponse(BaseModel):
    id: str
    email: EmailStr


class EmailValidationRequiredResponse(BaseModel):
    email: EmailStr
    message: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenResponse(BaseModel):
    access_token: str
    session_token: str
    token_type: str = "bearer"
    user: AuthUserResponse
