"""Web app: upload a pro forma cap table and a deck, get the workbook and one-page PDF.

    uvicorn captable_app.web:app --port 8000

The app is open: there is no login. Uploaded files
and results live in a per-job folder that is deleted after JOB_TTL_MINUTES. Jobs are held in this
process's memory, so run a single worker.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from . import web_ui as ui  # noqa: E402
from . import notify  # noqa: E402
from .pipeline import RunResult, analyze  # noqa: E402

log = logging.getLogger("captable_app.web")
logging.basicConfig(level=logging.INFO)

JOBS_DIR = os.environ.get("JOBS_DIR") or os.path.join(tempfile.gettempdir(), "captable-jobs")
MAX_UPLOAD_MB = float(os.environ.get("MAX_UPLOAD_MB", "200"))
JOB_TTL_MINUTES = float(os.environ.get("JOB_TTL_MINUTES", "60"))
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public")
LOGO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "TEN_Capital_logo_footer.png")
AI_AVAILABLE = bool(os.environ.get("ANTHROPIC_API_KEY"))
AI_DEFAULT = AI_AVAILABLE and os.environ.get("AI_REVIEW_DEFAULT", "true").lower() in ("1", "true", "yes")

@asynccontextmanager
async def lifespan(_app):
    os.makedirs(JOBS_DIR, exist_ok=True)
    threading.Thread(target=_janitor, daemon=True).start()
    yield


app = FastAPI(title="Investor Ownership Calculator", docs_url=None, redoc_url=None, openapi_url=None,
              lifespan=lifespan)
# Public, unauthenticated assets (favicons) served from the project's public/ directory.
app.mount("/public", StaticFiles(directory=PUBLIC_DIR), name="public")


# ------------------------------------------------------------------------------------ jobs

@dataclass
class Job:
    id: str
    dir: str
    cap_path: str
    deck_path: str
    params: dict
    created: float = field(default_factory=time.time)
    status: str = "queued"            # queued / running / done / error
    progress: list[str] = field(default_factory=list)
    result: Optional[RunResult] = None
    error: Optional[str] = None
    email_note: Optional[str] = None


JOBS: dict[str, Job] = {}
LOCK = threading.Lock()


def _run_job(job: Job) -> None:
    job.status = "running"
    try:
        job.result = analyze(job.cap_path, job.deck_path, os.path.join(job.dir, "out"),
                             progress=job.progress.append, **job.params)
    except Exception as e:
        log.exception("job %s failed", job.id)
        job.error = f"{type(e).__name__}: {e}"
        if notify.is_configured():
            r = notify.send_failure(job.error, os.path.basename(job.cap_path), os.path.basename(job.deck_path), job.id)
            job.email_note = r.note
        job.status = "error"
        return
    if notify.is_configured():
        job.progress.append("Emailing results")
        r = notify.send_results(job.result, job.id, JOB_TTL_MINUTES)
        job.email_note = r.note
        if not r.sent:
            log.warning("job %s: %s", job.id, r.note)
    job.status = "done"


def _start(cap_path: str, deck_path: str, params: dict, job_dir: str) -> Job:
    job = Job(os.path.basename(job_dir), job_dir, cap_path, deck_path, params)
    with LOCK:
        JOBS[job.id] = job
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return job


def _janitor() -> None:
    while True:
        cutoff = time.time() - JOB_TTL_MINUTES * 60
        with LOCK:
            old = [j for j in JOBS.values() if j.created < cutoff and j.status in ("done", "error")]
            for j in old:
                JOBS.pop(j.id, None)
        for j in old:
            shutil.rmtree(j.dir, ignore_errors=True)
        if os.path.isdir(JOBS_DIR):   # folders orphaned by a restart
            for name in os.listdir(JOBS_DIR):
                p = os.path.join(JOBS_DIR, name)
                if name not in JOBS and os.path.getmtime(p) < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
        time.sleep(300)




def _job(job_id: str) -> Job:
    job = JOBS.get(job_id) if re.fullmatch(r"[0-9a-f]{32}", job_id) else None
    if job is None:
        raise HTTPException(404, "Job not found or expired.")
    return job


# ------------------------------------------------------------------------------------ parsing

def _money(v: str, name: str) -> Optional[float]:
    v = (v or "").strip()
    if not v:
        return None
    try:
        x = float(re.sub(r"[,$\s]", "", v))
    except ValueError:
        raise HTTPException(400, f"{name}: '{v}' is not a number.")
    if x < 0:
        raise HTTPException(400, f"{name} must not be negative.")
    return x


def _params(investor, check_size, share_price, commitments_in_before, uncounted_commitments,
            placeholder, pre_money, ai_review) -> dict:
    if commitments_in_before not in ("", "yes", "no"):
        raise HTTPException(400, "Commitments must be yes, no or blank.")
    if placeholder not in ("release", "keep"):
        raise HTTPException(400, "Plug-row treatment must be release or keep.")
    return dict(investor=(investor or "").strip()[:80] or None,
                check_size=_money(check_size, "Check size"), share_price=_money(share_price, "Share price"),
                commitments_in_before=commitments_in_before or None,
                uncounted_commitments=_money(uncounted_commitments, "Uncounted commitments"),
                placeholder_mode=placeholder, pre_money=_money(pre_money, "Pre-money"),
                ai_review=bool(ai_review) and AI_AVAILABLE)


async def _save(upload: UploadFile, dest_dir: str, allowed: tuple[str, ...]) -> str:
    name = os.path.basename(upload.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"{name or 'File'}: expected {' or '.join(allowed)}.")
    safe = re.sub(r"[^A-Za-z0-9._ -]+", "_", name)[:120] or f"upload{ext}"
    path = os.path.join(dest_dir, safe)
    size, limit = 0, MAX_UPLOAD_MB * 1024 * 1024
    with open(path, "wb") as fh:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise HTTPException(413, f"{name} exceeds {MAX_UPLOAD_MB:g} MB.")
            fh.write(chunk)
    return path


# ------------------------------------------------------------------------------------ routes

@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return ui.index_page(AI_AVAILABLE, AI_DEFAULT, notify.recipients() if notify.is_configured() else None,
                         JOB_TTL_MINUTES, MAX_UPLOAD_MB)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(os.path.join(PUBLIC_DIR, "favicon.ico"), media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=604800"})


@app.get("/static/logo.png", include_in_schema=False)
def logo():
    return FileResponse(LOGO, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})


@app.post("/analyze")
async def analyze_upload(cap_table: UploadFile = File(...), deck: UploadFile = File(...),
                         investor: str = Form(""), check_size: str = Form(""), share_price: str = Form(""),
                         commitments_in_before: str = Form(""), uncounted_commitments: str = Form(""),
                         placeholder: str = Form("release"), pre_money: str = Form(""),
                         ai_review: Optional[str] = Form(None)):
    params = _params(investor, check_size, share_price, commitments_in_before, uncounted_commitments,
                     placeholder, pre_money, ai_review)
    job_dir = os.path.join(JOBS_DIR, uuid.uuid4().hex)
    os.makedirs(os.path.join(job_dir, "in"))
    try:
        cap_path = await _save(cap_table, os.path.join(job_dir, "in"), (".xlsx",))
        deck_path = await _save(deck, os.path.join(job_dir, "in"), (".pdf", ".pptx"))
    except HTTPException:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    job = _start(cap_path, deck_path, params, job_dir)
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@app.post("/jobs/{job_id}/rerun")
def rerun(job_id: str, investor: str = Form(""), check_size: str = Form(""), share_price: str = Form(""),
          commitments_in_before: str = Form(""), uncounted_commitments: str = Form(""),
          placeholder: str = Form("release"), pre_money: str = Form(""), ai_review: Optional[str] = Form(None)):
    src = _job(job_id)
    params = _params(investor, check_size, share_price, commitments_in_before, uncounted_commitments,
                     placeholder, pre_money, ai_review)
    job_dir = os.path.join(JOBS_DIR, uuid.uuid4().hex)
    os.makedirs(os.path.join(job_dir, "in"))
    cap = shutil.copy2(src.cap_path, os.path.join(job_dir, "in"))
    deck = shutil.copy2(src.deck_path, os.path.join(job_dir, "in"))
    job = _start(cap, deck, params, job_dir)
    return RedirectResponse(f"/jobs/{job.id}", status_code=303)


@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    j = _job(job_id)
    return JSONResponse({"status": j.status, "progress": j.progress[-1:] or ["Queued"], "log": j.progress})


@app.get("/jobs/{job_id}/download/{kind}")
def download(job_id: str, kind: str):
    j = _job(job_id)
    if j.status != "done" or j.result is None:
        raise HTTPException(409, "Not ready.")
    r = j.result
    paths = {"xlsx": r.xlsx, "pdf": r.pdf,
             "ai": os.path.splitext(r.xlsx)[0] + "_ai_review.json"}
    path = paths.get(kind)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "File not available.")
    return FileResponse(path, filename=os.path.basename(path))


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str):
    j = _job(job_id)
    if j.status in ("queued", "running"):
        return ui.running_page(j.id, j.progress, bool(j.params.get("ai_review")), notify.is_configured())
    if j.status == "error":
        return ui.error_page(j.error or "", j.email_note)
    return ui.result_page(j.id, j.result, j.params, j.email_note, JOB_TTL_MINUTES, AI_AVAILABLE, AI_DEFAULT)
