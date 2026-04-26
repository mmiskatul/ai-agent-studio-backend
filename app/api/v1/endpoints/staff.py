from fastapi import APIRouter, Depends, Response, status

from app.dependencies import get_current_user, get_service_factory
from app.factories.service_factory import ServiceFactory
from app.models.user import UserDocument
from app.schemas.common import ApiResponse
from app.schemas.staff import StaffCreate, StaffResponse, StaffUpdate

router = APIRouter()


@router.get("", response_model=list[StaffResponse])
async def list_staff(
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    return await factory.staff_service.list_staff(current_user)


@router.post("", response_model=ApiResponse[StaffResponse], status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: StaffCreate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    member = await factory.staff_service.create_staff(payload, current_user)
    return ApiResponse(
        message="Staff member created successfully",
        data=member,
    )


@router.patch("/{staff_id}", response_model=ApiResponse[StaffResponse])
async def update_staff(
    staff_id: str,
    payload: StaffUpdate,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    member = await factory.staff_service.update_staff(staff_id, payload, current_user)
    return ApiResponse(
        message="Staff member updated successfully",
        data=member,
    )


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff(
    staff_id: str,
    current_user: UserDocument = Depends(get_current_user),
    factory: ServiceFactory = Depends(get_service_factory),
):
    await factory.staff_service.delete_staff(staff_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
