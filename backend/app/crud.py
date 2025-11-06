"""
Functions to interact with the database.

Keeping database queries in a separate module makes it easier to
maintain and test your application logic.
"""

from typing import List, Optional
import json

from sqlalchemy.orm import Session

from . import models


def create_upload(
    db: Session, filename: str, result_path: str, data_json: list
) -> models.Upload:
    """Insert a new upload entry into the database."""
    obj = models.Upload(
        filename=filename, result_path=result_path, data_json=json.dumps(data_json)
    )
    db.add(obj)
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