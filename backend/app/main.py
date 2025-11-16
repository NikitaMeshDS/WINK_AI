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

# ML service URL, configurable via environment variables
ML_API_URL = os.environ.get("ML_API_URL", "http://host.docker.internal:8000")


import glob
import itertools


def get_data_from_docx(docx_path: str) -> dict:
    """
    Process a single .docx script file by sending it to the ML service
    and returning the extracted data.
    """
    logger.info(f"Sending {docx_path} to ML service for analysis...")
    
    try:
        with open(docx_path, "rb") as f:
            files = {"file": (os.path.basename(docx_path), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
            response = requests.post(f"{ML_API_URL}/analyze", files=files, timeout=300) # 5-minute timeout
        
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        
        data = response.json()
        logger.info(f"Successfully received data from ML service for {docx_path}")
        return data

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to connect to ML service: {e}")
        raise HTTPException(status_code=503, detail=f"ML service is unavailable: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing with ML service: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing file with ML service: {e}")

def create_summary_excel(all_data: dict, output_path: str):
    """Create a summary Excel file with unique actors and props."""
    logger.info("Creating summary file...")
    all_actors = set()
    all_props = set()

    for show_name, show_data in all_data.items():
        for series_name, series_data in show_data.items():
            for scene in series_data:
                actors = scene.get("Актеры", [])
                if isinstance(actors, list):
                    all_actors.update(actors)
                
                props_str = scene.get("Реквизит", "")
                if props_str and isinstance(props_str, str):
                    props_list = [p.strip() for p in props_str.split(',') if p.strip()]
                    all_props.update(props_list)

    # Pad lists to the same length for DataFrame creation
    actors_list = sorted(list(all_actors))
    props_list = sorted(list(all_props))
    max_len = max(len(actors_list), len(props_list))
    
    actors_padded = actors_list + [''] * (max_len - len(actors_list))
    props_padded = props_list + [''] * (max_len - len(props_list))

    summary_df = pd.DataFrame({
        'Актеры': actors_padded,
        'Реквизит': props_padded
    })
    
    summary_df.to_excel(output_path, index=False)
    logger.info(f"Summary file created at: {output_path}")


@app.post("/upload", response_model=schemas.UploadResponse)
async def upload_script(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> schemas.UploadResponse:
    """
    Handle a new script upload.
    - Accepts a .zip or .docx file.
    - If zip contains multiple folders, creates a zip output with one Excel per folder.
    - If a folder/show has >20 series, splits it into multiple Excel files.
    - Creates a summary Excel file with all unique actors and props.
    """
    filename = file.filename or "uploaded_file"
    logger.info(f"--- New upload request for file: {filename} ---")

    if not (filename.lower().endswith(".zip") or filename.lower().endswith(".docx")):
        raise HTTPException(status_code=400, detail="Only .zip and .docx files are supported.")

    uid = uuid.uuid4().hex
    upload_dir = os.path.join(UPLOAD_ROOT, uid)
    os.makedirs(upload_dir, exist_ok=True)
    
    # This directory will hold all generated excel files for this upload
    output_files_dir = os.path.join(RESULT_ROOT, uid)
    os.makedirs(output_files_dir, exist_ok=True)

    saved_file_path = os.path.join(upload_dir, filename)
    with open(saved_file_path, "wb") as f:
        f.write(await file.read())

    all_docx_paths = []
    if filename.lower().endswith(".docx"):
        all_docx_paths.append(saved_file_path)
    else: # It's a zip
        extract_dir = os.path.join(upload_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(saved_file_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Invalid ZIP archive.")
        
        all_docx_paths = glob.glob(os.path.join(extract_dir, '**', '*.docx'), recursive=True)
        if not all_docx_paths:
            raise HTTPException(status_code=400, detail="No .docx files found in the zip archive.")

    # Group docx paths by their parent directory (show name)
    shows = {k: list(v) for k, v in itertools.groupby(sorted(all_docx_paths), key=lambda p: os.path.basename(os.path.dirname(p)))}
    # For single docx file or files in root of zip
    if ".":
        root_files = shows.pop(".", [])
        if root_files:
            shows[os.path.splitext(filename)[0]] = root_files

    all_aggregated_data = {}
    generated_excel_paths = []

    for show_name, docx_paths in shows.items():
        show_data = {}
        for docx_path in docx_paths:
            series_data = get_data_from_docx(docx_path)
            show_data.update(series_data)
        
        all_aggregated_data[show_name] = show_data
        
        series_items = sorted(list(show_data.items()), key=lambda x: int(x[0].split(" ")[1]))
        
        # Split into chunks of 20 series per Excel file
        for i in range(0, len(series_items), 20):
            chunk = series_items[i:i+20]
            start_series = chunk[0][0].split(" ")[1]
            end_series = chunk[-1][0].split(" ")[1]
            
            excel_filename = f"{show_name}_серии_{start_series}-{end_series}.xlsx"
            excel_path = os.path.join(output_files_dir, excel_filename)
            
            with pd.ExcelWriter(excel_path) as writer:
                for series_name, scene_data in chunk:
                    df = pd.DataFrame(scene_data)
                    df.to_excel(writer, sheet_name=series_name[:31], index=False)
            generated_excel_paths.append(excel_path)
            logger.info(f"Generated Excel file: {excel_path}")

    # Create the final summary file
    summary_path = os.path.join(output_files_dir, "Итог.xlsx")
    create_summary_excel(all_aggregated_data, summary_path)
    generated_excel_paths.append(summary_path)

    # Decide final result path (single excel or zip)
    final_result_path = ""
    if len(generated_excel_paths) == 1:
        final_result_path = generated_excel_paths[0]
    else:
        final_result_path = os.path.join(RESULT_ROOT, f"{uid}.zip")
        with zipfile.ZipFile(final_result_path, 'w') as zipf:
            for file_path in generated_excel_paths:
                zipf.write(file_path, os.path.basename(file_path))
        logger.info(f"Created result zip archive: {final_result_path}")

    # Save to DB and return response
    record = crud.create_upload(db, filename=filename, result_path=final_result_path, data_json=all_aggregated_data)
    logger.info(f"Upload complete. Returning response for ID: {record.id}")
    return schemas.UploadResponse(id=record.id, data=all_aggregated_data)


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
        data = {}
    download_url = f"/download/{record.id}"
    return schemas.UploadDetail(
        id=record.id,
        filename=record.filename,
        created_at=record.created_at,
        data=data,
        download_url=download_url,
    )


@app.get("/download/{upload_id}")
def download_result(upload_id: int, db: Session = Depends(get_db)):
    """
    Stream the generated result (Excel or ZIP) to the client.
    """
    record = crud.get_upload(db, upload_id)
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found.")
    
    original_filename_base = os.path.splitext(record.filename)[0]
    
    if record.result_path.lower().endswith(".zip"):
        download_filename = f"{original_filename_base}_результат.zip"
        media_type = "application/zip"
    else:
        download_filename = f"{original_filename_base}_результат.xlsx"
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
    return FileResponse(record.result_path, filename=download_filename, media_type=media_type)


# Attempt to serve the built frontend if it exists
from fastapi.staticfiles import StaticFiles

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="static")
