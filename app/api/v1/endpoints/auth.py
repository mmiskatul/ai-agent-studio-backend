from fastapi import APIRouter, Depends

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.auth import (
    AccessTokenResponse,
    AuthUserResponse,
    ChangePasswordRequest,
    EmailValidationRequiredResponse,
    EmailValidationRequest,
    ForgotPasswordRequest,
    ForgotPasswordVerifyRequest,
    LoginRequest,
    MessageResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SigninRequest,
    SignupRequest,
    TokenResponse,
)

router = APIRouter()


@router.post("/signup", response_model=EmailValidationRequiredResponse)
async def signup(
    payload: SignupRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> EmailValidationRequiredResponse:
    return await factory.auth_service.register(payload)


@router.post("/register", response_model=EmailValidationRequiredResponse)
async def register(
    payload: RegisterRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> EmailValidationRequiredResponse:
    return await factory.auth_service.register(payload)


@router.post("/verify-email", response_model=TokenResponse)
async def verify_email(
    payload: EmailValidationRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> TokenResponse:
    return await factory.auth_service.verify_email(payload)


@router.post("/signin", response_model=TokenResponse)
async def signin(
    payload: SigninRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> TokenResponse:
    return await factory.auth_service.login(payload)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> TokenResponse:
    return await factory.auth_service.login(payload)


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(
    payload: RefreshTokenRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> AccessTokenResponse:
    return await factory.auth_service.refresh_access_token(payload)


@router.post("/forgot-password", response_model=EmailValidationRequiredResponse)
async def forgot_password(
    payload: ForgotPasswordRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> EmailValidationRequiredResponse:
    return await factory.auth_service.forgot_password(payload)


@router.post("/forgot-password/verify", response_model=MessageResponse)
async def verify_forgot_password(
    payload: ForgotPasswordVerifyRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> MessageResponse:
    return await factory.auth_service.verify_forgot_password(payload)


@router.post("/forgot-password/reset", response_model=MessageResponse)
async def reset_forgot_password(
    payload: ResetPasswordRequest,
    factory: ServiceFactory = Depends(get_service_factory),
) -> MessageResponse:
    return await factory.auth_service.reset_password(payload)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    payload: ChangePasswordRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
) -> MessageResponse:
    return await factory.auth_service.change_password(current_user, payload)


@router.post("/logout-all", response_model=MessageResponse)
async def logout_all(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
) -> MessageResponse:
    return await factory.auth_service.revoke_all_sessions(current_user)

@router.get("/me", response_model=AuthUserResponse)
async def me(current_user: UserDocument = Depends(get_current_user)) -> AuthUserResponse:
    return AuthUserResponse(
        id=current_user.id or "",
        email=current_user.email,
        display_name=current_user.display_name,
        profile_image=current_user.profile_image,
    )


@router.get("/profile", response_model=ProfileResponse)
async def profile(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
) -> ProfileResponse:
    return await factory.auth_service.get_profile(current_user)


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
) -> ProfileResponse:
    return await factory.auth_service.update_profile(current_user, payload)
