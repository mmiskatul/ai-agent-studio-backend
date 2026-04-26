from typing import Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ApiResponse(BaseModel, Generic[DataT]):
    success: bool = True
    message: str
    data: DataT | None = None
    errors: list[str] = Field(default_factory=list)
