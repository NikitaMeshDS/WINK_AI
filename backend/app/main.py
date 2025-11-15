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
import logging
from datetime import datetime
from typing import List

import pandas as pd
import requests
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import Base, engine, get_db

import zipfile

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Backend")
# --- End Logging Setup ---

# Create all tables if they do not exist
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Preproduction Table Service",
    description="Upload a film script (.docx or .zip) and receive a structured preproduction table.",
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

ML_API_URL = "http://host.docker.internal:8000"


def process_docx_file(docx_path: str, result_path: str) -> pd.DataFrame:
    """
    Process a .docx script file by calling the ML service.
    """
    logger.info(f"Processing .docx file: {docx_path}. Sending to ML service at {ML_API_URL}")
    
    file_name = os.path.basename(docx_path)

    with open(docx_path, "rb") as f:
        files = {"file": (file_name, f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        # The ML service endpoint is /analyze
        ml_service_url = f"{ML_API_URL}/analyze"
        response = requests.post(ml_service_url, files=files)

    if response.status_code != 200:
        logger.error(f"Error from ML service. Status: {response.status_code}, Body: {response.text}")
        raise HTTPException(status_code=response.status_code, detail=f"Error from ML service: {response.text}")

    logger.info("Successfully received response from ML service.")
    
    try:
        data = response.json()
        # In the ML app, the actual scene data is returned directly, not nested.
        # If the response is {"status": "success", "scenes_processed": N}, we need to call /result
        if isinstance(data, dict) and "scenes_processed" in data:
             logger.info("ML service returned a status object, fetching full results from /result endpoint.")
             result_url = f"{ML_API_URL}/result"
             response = requests.get(result_url)
             if response.status_code != 200:
                 logger.error(f"Error fetching results from ML service. Status: {response.status_code}, Body: {response.text}")
                 raise HTTPException(status_code=response.status_code, detail=f"Error fetching results from ML service: {response.text}")
             data = response.json()

        logger.info(f"Received JSON data from ML service: {json.dumps(data, ensure_ascii=False, indent=2)}")
    except json.JSONDecodeError:
        logger.error(f"Failed to decode JSON from ML service response. Response text: {response.text}")
        raise HTTPException(status_code=500, detail="Invalid JSON response from ML service.")

    df = pd.DataFrame(data)
    df.to_excel(result_path, index=False)
    logger.info(f"Successfully created and saved Excel file to {result_path}")
    return df


@app.post("/upload", response_model=schemas.UploadResponse)
async def upload_script(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> schemas.UploadResponse:
    """
    Handle a new script upload.
    Accepts a .zip or .docx file, processes the script, and returns the result.
    """
    filename = file.filename or "uploaded_file"
    logger.info(f"--- New upload request for file: {filename} ---")

    # Check for allowed file types
    is_zip = filename.lower().endswith(".zip")
    is_docx = filename.lower().endswith(".docx")

    if not is_zip and not is_docx:
        logger.warning(f"Upload rejected: File '{filename}' is not a .zip or .docx archive.")
        raise HTTPException(status_code=400, detail="Only .zip and .docx files are supported.")

    uid = uuid.uuid4().hex
    upload_dir = os.path.join(UPLOAD_ROOT, uid)
    os.makedirs(upload_dir, exist_ok=True)
    saved_file_path = os.path.join(upload_dir, filename)
    
    logger.info(f"Saving uploaded file to: {saved_file_path}")
    with open(saved_file_path, "wb") as f:
        contents = await file.read()
        f.write(contents)
    
    docx_to_process_path = ""

    if is_zip:
        extract_dir = os.path.join(upload_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        logger.info(f"Extracting archive to: {extract_dir}")
        try:
            with zipfile.ZipFile(saved_file_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)
        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP archive uploaded: {filename}")
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="Invalid ZIP archive.")
        
        # Find the .docx file in the extracted archive
        docx_files = [f for f in os.listdir(extract_dir) if f.lower().endswith(".docx")]
        if not docx_files:
            logger.error(f"No .docx file found in the archive: {filename}")
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail="No .docx file found in the zip archive.")
        
        docx_to_process_path = os.path.join(extract_dir, docx_files[0])

    elif is_docx:
        docx_to_process_path = saved_file_path

    # Process the determined .docx file
    result_file = os.path.join(RESULT_ROOT, f"{uid}.xlsx")
    df = process_docx_file(docx_to_process_path, result_file)
    data_json = df.to_dict(orient="records")
    
    logger.info("Saving upload record to the database.")
    record = crud.create_upload(db, filename=filename, result_path=result_file, data_json=data_json)
    logger.info(f"Upload complete. Returning response for ID: {record.id}")
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
    """
    record = crud.get_upload(db, upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found.")
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


# Attempt to serve the built frontend if it exists
from fastapi.staticfiles import StaticFiles

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
