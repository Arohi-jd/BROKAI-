from dotenv import load_dotenv

load_dotenv()

import io
import time
import threading
import uuid
from typing import Any, Dict

import pandas as pd
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from pipeline import process_company


jobs_lock = threading.Lock()
jobs: Dict[str, Dict[str, Any]] = {}

app = FastAPI(title="Brokai Lead Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _safe_cell(value: Any) -> str:
    """Convert a DataFrame cell value into a clean string."""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def _flatten_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten nested pipeline output into a frontend-friendly dictionary."""
    profile = result.get("profile", {}) or {}
    contact_card = result.get("contact_card", {}) or {}

    return {
        "company_name": profile.get("company_name", result.get("company_name", "Unknown Company")),
        "location": profile.get("location", result.get("location", "India")),
        "what_they_do": profile.get("what_they_do", "Not available"),
        "size_signals": profile.get("size_signals", "Not available"),
        "digital_presence": profile.get("digital_presence", "Not available"),
        "existing_tools": profile.get("existing_tools", "Not available"),
        "website_url": profile.get("website_url", "Not available"),
        "phone": contact_card.get("phone", "Not found"),
        "email": contact_card.get("email", "Not found"),
        "whatsapp": contact_card.get("whatsapp", "Not found"),
        "source_url": contact_card.get("source_url", ""),
        "outreach_message": result.get("outreach_message", ""),
        "error": result.get("error", ""),
    }


def _build_row_fallback(company_name: str, location: str, error_text: str) -> Dict[str, Any]:
    """Build a safe fallback output row when row processing fails."""
    return {
        "company_name": company_name,
        "location": location,
        "what_they_do": "Not available",
        "size_signals": "Not available",
        "digital_presence": "Not available",
        "existing_tools": "Not available",
        "website_url": "Not available",
        "phone": "Not found",
        "email": "Not found",
        "whatsapp": "Not found",
        "source_url": "",
        "outreach_message": f"Hi! We help businesses like {company_name} automate customer communication with AI. Worth a quick chat?",
        "error": error_text,
    }


def _process_dataframe(df: pd.DataFrame, job_id: str | None = None) -> Dict[str, Any]:
    """Process all rows from a DataFrame and optionally update live job progress."""
    results = []
    first_col = df.columns[0] if len(df.columns) > 0 else None
    second_col = df.columns[1] if len(df.columns) > 1 else None

    for idx, row in df.iterrows():
        company_name = _safe_cell(row.get("Company Name", row.get(first_col, "")))
        location = _safe_cell(row.get("Location", row.get(second_col, "India"))) or "India"

        if not company_name:
            company_name = f"Unknown Company Row {idx + 1}"

        try:
            started_at = time.perf_counter()
            pipeline_result = process_company(company_name=company_name, location=location)
            elapsed = round(time.perf_counter() - started_at, 2)
            if isinstance(pipeline_result, dict):
                existing_error = str(pipeline_result.get("error", "") or "").strip()
                if elapsed > 60 and not existing_error:
                    pipeline_result["error"] = f"Slow processing ({elapsed}s) due to external service latency"
            results.append(_flatten_result(pipeline_result))
        except Exception as exc:
            results.append(_build_row_fallback(company_name, location, f"Row processing failed: {exc}"))

        if job_id:
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]["processed_rows"] = len(results)

    return {"results": results, "total": len(results)}


def _run_job(job_id: str, df: pd.DataFrame) -> None:
    """Run a background processing job and persist status/progress in memory."""
    try:
        processed = _process_dataframe(df, job_id=job_id)
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["results"] = processed.get("results", [])
                jobs[job_id]["total"] = processed.get("total", 0)
                jobs[job_id]["done"] = True
                jobs[job_id]["status"] = "completed"
                jobs[job_id]["finished_at"] = time.time()
    except Exception as exc:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["done"] = True
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = f"Background processing failed: {exc}"
                jobs[job_id]["finished_at"] = time.time()


@app.get("/")
def root() -> Dict[str, str]:
    """Health endpoint returning API running status."""
    return {"status": "Brokai Lead Intelligence API is running"}


@app.post("/process")
async def process(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Read uploaded Excel, process each row through the LangGraph pipeline, and return results."""
    try:
        file_bytes = await file.read()
        excel_buffer = io.BytesIO(file_bytes)
        df = pd.read_excel(excel_buffer)
    except Exception as exc:
        return {"results": [], "total": 0, "error": f"Failed to read Excel file: {exc}"}

    return _process_dataframe(df)


@app.post("/process/start")
async def process_start(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Start background Excel processing and return a job id for progress polling."""
    try:
        file_bytes = await file.read()
        excel_buffer = io.BytesIO(file_bytes)
        df = pd.read_excel(excel_buffer)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to read Excel file: {exc}"}

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {
            "status": "processing",
            "done": False,
            "error": "",
            "total_rows": int(len(df.index)),
            "processed_rows": 0,
            "results": [],
            "total": 0,
            "created_at": time.time(),
            "finished_at": None,
        }

    worker = threading.Thread(target=_run_job, args=(job_id, df), daemon=True)
    worker.start()

    return {
        "ok": True,
        "job_id": job_id,
        "total_rows": int(len(df.index)),
    }


@app.get("/process/status/{job_id}")
def process_status(job_id: str) -> Dict[str, Any]:
    """Return live processing status for a background job id."""
    with jobs_lock:
        job = jobs.get(job_id)

    if not job:
        return {"ok": False, "error": "Job not found", "done": True}

    return {
        "ok": True,
        "job_id": job_id,
        "status": job.get("status", "processing"),
        "done": bool(job.get("done", False)),
        "error": job.get("error", ""),
        "processed_rows": int(job.get("processed_rows", 0)),
        "total_rows": int(job.get("total_rows", 0)),
        "total": int(job.get("total", 0)),
        "results": job.get("results", []) if job.get("done", False) else [],
    }
