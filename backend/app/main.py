"""
FastAPI application entrypoint.

This module defines the HTTP routes for uploading scripts, viewing
results and downloading the generated Excel workbook.  It also
initialises the database and serves the built frontend as static
files when available.
"""

import json
import os
import shutil
import uuid
from datetime import datetime
from typing import List

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import Base, engine, get_db
from .ml_stub import process_script

import zipfile

# Create all tables if they do not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Preproduction Table Service",
    description="Upload a zipped film script and receive a structured preproduction table.",
)

# Allow requests from any origin during development.  In production you
# should restrict allowed origins to the domains serving your
# frontend.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories for file storage
UPLOAD_ROOT = "uploads"
RESULT_ROOT = "results"
os.makedirs(UPLOAD_ROOT, exist_ok=True)
os.makedirs(RESULT_ROOT, exist_ok=True)


@app.post("/upload", response_model=schemas.UploadResponse)
async def upload_script(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> schemas.UploadResponse:
    """
    Handle a new script upload.

    Expects a ZIP file uploaded as form data.  The file is saved to a
    unique directory, extracted, passed to the processing stub and then
    persisted in the database along with the generated result.

    Returns the upload identifier and the table contents as JSON.
    """
    filename = file.filename or "uploaded.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only ZIP archives are supported.")
    uid = uuid.uuid4().hex
    upload_dir = os.path.join(UPLOAD_ROOT, uid)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, filename)
    # Save the uploaded file to disk
    with open(file_path, "wb") as f:
        contents = await file.read()
        f.write(contents)
    # Extract the archive
    extract_dir = os.path.join(upload_dir, "extracted")
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            zip_ref.extractall(extract_dir)
    except zipfile.BadZipFile:
        # Clean up and return an error if the archive is invalid
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Invalid ZIP archive.")
    # Create result directory and process the script
    result_file = os.path.join(RESULT_ROOT, f"{uid}.xlsx")
    df = process_script(extract_dir, result_file)
    data_json = df.to_dict(orient="records")
    # Persist to database
    record = crud.create_upload(db, filename=filename, result_path=result_file, data_json=data_json)
    return schemas.UploadResponse(id=record.id, data=data_json)


@app.get("/history", response_model=List[schemas.UploadInfo])
def list_uploads(db: Session = Depends(get_db)) -> List[schemas.UploadInfo]:
    """Return a list of previous uploads ordered by creation time."""
    uploads = crud.get_uploads(db)
    return uploads


@app.get("/result/{upload_id}", response_model=schemas.UploadDetail)
def get_result(upload_id: int, db: Session = Depends(get_db)) -> schemas.UploadDetail:
    """
    Retrieve the processed table for a given upload.

    If the upload does not exist an HTTP 404 error is raised.  The
    response includes a download URL for the Excel file.
    """
    record = crud.get_upload(db, upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found.")
    # Convert JSON string back to list of dicts
    try:
        data = json.loads(record.data_json)
    except json.JSONDecodeError:
        data = []
    download_url = f"/download/{record.id}"
    return schemas.UploadDetail(
        id=record.id,
        filename=record.filename,
        created_at=record.created_at,
        data=data,
        download_url=download_url,
    )


@app.get("/download/{upload_id}")
def download_excel(upload_id: int, db: Session = Depends(get_db)):
    """
    Stream the generated Excel workbook to the client.
    """
    record = crud.get_upload(db, upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found.")
    return FileResponse(record.result_path, filename=os.path.basename(record.result_path))


# Attempt to serve the built frontend if it exists.  This enables
# running a single container that serves both the API and the static
# assets produced by Vite.  When the `dist` folder isn't present
# (e.g. during development), the middleware silently fails and only
# API routes remain available.

from fastapi.staticfiles import StaticFiles  # type: ignore

# Compute the path to the built frontend.  `__file__` points to
# `backend/app/main.py`, so moving up one directory gives `/app/app` in
# the container.  The built frontend is located at `/app/frontend/dist`.
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")