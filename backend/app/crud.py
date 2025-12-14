"""
Functions to interact with the database.

Keeping database queries in a separate module makes it easier to
maintain and test your application logic.
"""

from typing import List, Optional
import json

from sqlalchemy.orm import Session

from . import models


def initiate_upload(db: Session, filename: str) -> models.Upload:
    """Insert a new upload entry with 'processing' status."""
    obj = models.Upload(
        filename=filename,
        status="processing",
        # result_path and data_json are nullable
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_upload_status_and_result(
    db: Session, upload_id: int, status: str, result_path: Optional[str], data_json: Optional[dict]
) -> Optional[models.Upload]:
    """Updates the status and result of an existing upload entry."""
    obj = get_upload(db, upload_id)
    if obj:
        obj.status = status
        obj.result_path = result_path
        obj.data_json = json.dumps(data_json) if data_json else None
        db.commit()
        db.refresh(obj)
    return obj


def get_upload(db: Session, upload_id: int) -> Optional[models.Upload]:
    """Return a single upload or None if it does not exist."""
    return db.query(models.Upload).filter(models.Upload.id == upload_id).first()


def get_uploads(db: Session, skip: int = 0, limit: int = 100) -> List[models.Upload]:
    """Return the most recent uploads in reverse chronological order."""
    return (
        db.query(models.Upload)
        .order_by(models.Upload.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )