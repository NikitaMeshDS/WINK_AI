"""
ORM model definitions.

The only table defined here is `Upload`, which tracks every
user submission along with the generated result.  You can extend this
module with additional tables (e.g. for users or configuration) as
needed.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.orm import relationship

from .database import Base


class Upload(Base):
    """Persistence model for an uploaded script and its result."""

    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Path on disk to the generated Excel file
    result_path = Column(String, nullable=False)
    # JSON payload (as string) representing the table for quick access
    data_json = Column(Text, nullable=False)