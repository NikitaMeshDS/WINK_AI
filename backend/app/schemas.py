"""
Pydantic schemas used for request and response models.

Pydantic enforces type hints at runtime and will produce
structured OpenAPI documentation automatically.
"""

from datetime import datetime
from typing import List, Any, Optional

from pydantic import BaseModel, Field


class UploadBase(BaseModel):
    filename: str = Field(..., description="Original filename of the uploaded ZIP archive.")


class UploadResponse(BaseModel):
    """
    Response returned immediately after a successful upload.
    Contains the database identifier and the extracted table data.
    """

    id: int
    data: List[dict]

    class Config:
        orm_mode = True


class UploadInfo(BaseModel):
    """Summary information about a past upload."""

    id: int
    filename: str
    created_at: datetime

    class Config:
        orm_mode = True


class UploadDetail(BaseModel):
    """Detailed result for a particular upload."""

    id: int
    filename: str
    created_at: datetime
    data: List[dict]
    download_url: str

    class Config:
        orm_mode = True