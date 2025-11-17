"""
FastAPI application entrypoint.

This module defines the HTTP routes for uploading scripts, viewing
results and downloading the generated Excel workbook. It supports
streaming results from the ML service to the client.
"""

import json
import os
import shutil
import uuid
import logging
from datetime import datetime
from typing import List, Optional, AsyncGenerator, Dict, Any
import asyncio
import httpx

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from . import crud, models, schemas
from .database import Base, engine, get_db

import zipfile
import re
import itertools

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
ML_API_URL = os.environ.get("ML_API_URL", "http://ml-app:8000")


def get_numeric_series_key(series_name: str) -> int:
    """
    Extracts a numeric key from a series name for sorting purposes.
    Prioritizes leading numbers, otherwise returns a high value.
    """
    match = re.match(r'^\d+', series_name)
    if match:
        return int(match.group(0))
    return 9999

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
                    props_list = [p.strip() for p in props_str.split(';') if p.strip()]
                    all_props.update(props_list)

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


def finalize_results(uid: str, show_name: str, all_aggregated_data: Dict[str, Any]) -> str:
    """
    Takes the aggregated data, creates Excel files, and returns the path
    to the final result (either a single Excel file or a ZIP archive).
    """
    output_files_dir = os.path.join(RESULT_ROOT, uid)
    generated_excel_paths = []

    for show_name, show_data in all_aggregated_data.items():
        series_items = sorted(list(show_data.items()), key=lambda x: get_numeric_series_key(x[0]))
        
        for i in range(0, len(series_items), 20):
            chunk = series_items[i:i+20]
            start_series = get_numeric_series_key(chunk[0][0])
            end_series = get_numeric_series_key(chunk[-1][0])
            
            excel_filename = f"{show_name}_серии_{start_series}-{end_series}.xlsx"
            excel_path = os.path.join(output_files_dir, excel_filename)
            
            with pd.ExcelWriter(excel_path) as writer:
                for series_name, scene_data in chunk:
                    df = pd.DataFrame(scene_data)
                    df.to_excel(writer, sheet_name=str(series_name)[:31], index=False)
            generated_excel_paths.append(excel_path)
            logger.info(f"Generated Excel file: {excel_path}")

    if not generated_excel_paths:
        logger.warning("No data was processed, no Excel files generated.")
        return ""

    summary_path = os.path.join(output_files_dir, "Итог.xlsx")
    create_summary_excel(all_aggregated_data, summary_path)
    generated_excel_paths.append(summary_path)

    content_excel_paths = [p for p in generated_excel_paths if not os.path.basename(p).startswith("Итог")]
    summary_excel_path = next((p for p in generated_excel_paths if os.path.basename(p).startswith("Итог")), None)

    if len(content_excel_paths) == 1 and summary_excel_path:
        main_excel_path = content_excel_paths[0]
        try:
            summary_df = pd.read_excel(summary_excel_path)
            with pd.ExcelWriter(main_excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                summary_df.to_excel(writer, sheet_name='Итог', index=False)
            os.remove(summary_excel_path)
            generated_excel_paths = [main_excel_path]
        except Exception as e:
            logger.error(f"Failed to merge summary into {main_excel_path}: {e}")

    if len(generated_excel_paths) == 1:
        return generated_excel_paths[0]
    else:
        final_zip_path = os.path.join(RESULT_ROOT, f"{uid}.zip")
        with zipfile.ZipFile(final_zip_path, 'w') as zipf:
            for file_path in generated_excel_paths:
                zipf.write(file_path, os.path.basename(file_path))
        logger.info(f"Created result zip archive: {final_zip_path}")
        return final_zip_path


@app.post("/initiate-upload", response_model=schemas.UploadInitiatedResponse)
async def initiate_upload(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> schemas.UploadInitiatedResponse:
    """
    Accepts a script file, saves it, and creates a database entry
    with 'processing' status, returning the ID for tracking.
    """
    filename = file.filename or "uploaded_file"
    logger.info(f"--- New upload initiated for file: {filename} ---")

    if not (filename.lower().endswith(".zip") or filename.lower().endswith(".docx")):
        raise HTTPException(status_code=400, detail="Only .zip and .docx files are supported.")

    # Use the upload ID as the directory name to keep files organized
    record = crud.initiate_upload(db, filename=filename)
    uid = str(record.id) # Use DB id as UID for simplicity and direct mapping

    upload_dir = os.path.join(UPLOAD_ROOT, uid)
    os.makedirs(upload_dir, exist_ok=True)
    
    saved_file_path = os.path.join(upload_dir, filename)
    with open(saved_file_path, "wb") as f:
        f.write(await file.read())

    logger.info(f"File '{filename}' saved for upload ID: {uid}. Ready for streaming analysis.")
    
    return schemas.UploadInitiatedResponse(id=record.id, status=record.status)


async def stream_processor(upload_id: int, db: Session):
    """
    The core async generator for processing a file and streaming results.
    """
    record = crud.get_upload(db, upload_id)
    if not record:
        logger.error(f"Stream request for unknown upload_id: {upload_id}")
        yield f"event: error\ndata: {json.dumps({'error': 'Upload not found'})}\n\n"
        return

    uid = str(record.id)
    upload_dir = os.path.join(UPLOAD_ROOT, uid)
    saved_file_path = os.path.join(upload_dir, record.filename)

    if not os.path.exists(saved_file_path):
        logger.error(f"File not found for upload_id: {upload_id}")
        yield f"event: error\ndata: {json.dumps({'error': 'File not found on server'})}\n\n"
        crud.update_upload_status_and_result(db, upload_id, "failed", None, {"error": "File not found"})
        return

    # This directory will hold all generated excel files for this upload
    output_files_dir = os.path.join(RESULT_ROOT, uid)
    os.makedirs(output_files_dir, exist_ok=True)

    all_docx_paths = []
    if record.filename.lower().endswith(".docx"):
        all_docx_paths.append(saved_file_path)
    else: # It's a zip
        extract_dir = os.path.join(upload_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        try:
            with zipfile.ZipFile(saved_file_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)
        except zipfile.BadZipFile:
            yield f"event: error\ndata: {json.dumps({'error': 'Invalid ZIP archive.'})}\\n\n"
            crud.update_upload_status_and_result(db, upload_id, "failed", None, {"error": "Invalid ZIP archive."})
            return
        
        all_docx_paths = glob.glob(os.path.join(extract_dir, '**', '*.docx'), recursive=True)
        if not all_docx_paths:
            yield f"event: error\ndata: {json.dumps({'error': 'No .docx files found in the zip archive.'})}\\n\n"
            crud.update_upload_status_and_result(db, upload_id, "failed", None, {"error": "No .docx files found."})
            return

    shows = {k: list(v) for k, v in itertools.groupby(sorted(all_docx_paths), key=lambda p: os.path.basename(os.path.dirname(p)))}
    if ".":
        root_files = shows.pop(".", [])
        if root_files:
            shows[os.path.splitext(record.filename)[0]] = root_files

    all_aggregated_data = {}
    
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            for show_name, docx_paths in shows.items():
                show_data = {}
                all_aggregated_data[show_name] = show_data

                for docx_path in docx_paths:
                    logger.info(f"Streaming analysis for {docx_path}...")
                    with open(docx_path, "rb") as f:
                        files = {"file": (os.path.basename(docx_path), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
                        
                        async with client.stream("POST", f"{ML_API_URL}/analyze", files=files, timeout=None) as response:
                            if response.status_code != 200:
                                error_body = await response.aread()
                                raise HTTPException(status_code=response.status_code, detail=f"ML service error: {error_body.decode()}")

                            buffer = ""
                            async for line in response.aiter_lines():
                                if line.startswith("data:"):
                                    scene_json = line[len("data:"):].strip()
                                    try:
                                        scene_data = json.loads(scene_json)
                                        
                                        # Group scene into the correct series
                                        series_name = scene_data.get("Серия") or os.path.splitext(os.path.basename(docx_path))[0]
                                        if series_name not in show_data:
                                            show_data[series_name] = []
                                        show_data[series_name].append(scene_data)

                                        # Stream the scene data to the client
                                        yield f"data: {json.dumps(scene_data)}\\n\\n"
                                    except json.JSONDecodeError:
                                        logger.warning(f"Could not decode JSON from stream: {scene_json}")
                                        continue
        
        logger.info(f"Finished streaming analysis for upload {upload_id}.")
        
        # Finalize: create Excel files and update DB
        final_result_path = finalize_results(uid, record.filename, all_aggregated_data)
        crud.update_upload_status_and_result(db, upload_id, "completed", final_result_path, all_aggregated_data)
        
        final_record = crud.get_upload(db, upload_id)
        final_model = schemas.UploadDetail.from_orm(final_record)
        final_model.download_url = f"/download/{upload_id}"
        
        # Use Pydantic's .json() method to correctly serialize datetime objects
        final_json = final_model.json()

        yield f"event: done\ndata: {final_json}\\n\\n"
        logger.info(f"Upload {upload_id} successfully completed and finalized.")

    except Exception as e:
        logger.error(f"An error occurred during streaming for upload {upload_id}: {e}", exc_info=True)
        crud.update_upload_status_and_result(db, upload_id, "failed", None, {"error": str(e)})
        yield f"event: error\ndata: {json.dumps({'error': 'An unexpected error occurred during analysis.', 'details': str(e)})}\\n\\n"


@app.get("/stream-results/{upload_id}")
async def stream_results(upload_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Connects a client to receive real-time analysis results for an upload.
    """
    # Pass the DB session to the generator
    generator = stream_processor(upload_id, db)
    return StreamingResponse(generator, media_type="text/event-stream")


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
    
    data = {}
    if record.data_json:
        try:
            data = json.loads(record.data_json)
        except json.JSONDecodeError:
            data = {"error": "Failed to decode result data."}

    download_url = f"/download/{record.id}" if record.status == "completed" else None
    
    return schemas.UploadDetail(
        id=record.id,
        filename=record.filename,
        created_at=record.created_at,
        status=record.status,
        data=data,
        download_url=download_url,
    )


@app.get("/download/{upload_id}")
def download_result(upload_id: int, db: Session = Depends(get_db)):
    """
    Stream the generated result (Excel or ZIP) to the client.
    """
    record = crud.get_upload(db, upload_id)
    if not record or not record.result_path or record.status != "completed":
        raise HTTPException(status_code=404, detail="Result not found or not completed.")
    
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