from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import token_service
from app.db.mongodb import mongo_database
from app.db.unit_of_work import UnitOfWork
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument

bearer_scheme = HTTPBearer(auto_error=False)


def get_unit_of_work() -> UnitOfWork:
    return UnitOfWork(mongo_database.db)


def get_service_factory(uow: UnitOfWork = Depends(get_unit_of_work)) -> ServiceFactory:
    return ServiceFactory(uow)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    factory: ServiceFactory = Depends(get_service_factory),
) -> UserDocument:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    decoded_access = token_service.decode_access(credentials.credentials)
    if decoded_access is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    user_id, session_version = decoded_access
    user = await factory.auth_service.get_user_by_id(user_id)
    if user is None or user.session_version != session_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    return user
