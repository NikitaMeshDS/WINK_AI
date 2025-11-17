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
    data: dict

    class Config:
        from_attributes = True


class UploadInitiatedResponse(BaseModel):
    """
    Response returned immediately after an upload is initiated.
    Contains the database identifier and the initial status.
    """
    id: int
    status: str

    class Config:
        from_attributes = True


class UploadInfo(BaseModel):
    """Summary information about a past upload."""

    id: int
    filename: str
    created_at: datetime
    status: str

    class Config:
        from_attributes = True


class UploadDetail(BaseModel):
    """Detailed result for a particular upload."""

    id: int
    filename: str
    created_at: datetime
    status: str
    data: Optional[dict] = None
    download_url: Optional[str] = None

    class Config:
        from_attributes = True