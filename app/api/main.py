"""FastAPI app. API under /api; serves the built web SPA (web/out) at /."""
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    MAX_FILE_SIZE_MB,
    MAX_FILES_PER_BATCH,
    SUPPORTED_EXTENSIONS,
)
from app.core.corpus import corpus_stats
from app.core.ingest import dedupe_check, delete_file, ingest_one
from app.core.jobs import create_job, list_jobs, update_job
from app.core.memory import delete_memory, list_memories
from app.core.orgs import AuthContext, create_personal_org, get_user_org
from app.core.qa import ask
from app.core.report import generate_report, get_report, list_reports
from app.core.summarize import summarize
from app.db.client import anon_client, service_client

app = FastAPI(title="DocQA")
api = APIRouter(prefix="/api")


def _scope_column(ctx: AuthContext) -> str:
    return "organization_id" if ctx.org_enabled else "user_id"


@app.exception_handler(RuntimeError)
def _runtime_error(request: Request, exc: RuntimeError):
    # e.g. Gemini rate limit -> clean 429 the UI can show
    return JSONResponse(status_code=429, content={"detail": str(exc)})


# ---------- auth ----------
class AuthIn(BaseModel):
    email: str
    password: str


def get_auth_context(authorization: str = Header(None)) -> AuthContext:
    """Verify Bearer JWT and return user + active organisation context."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        res = anon_client().auth.get_user(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    if not res or not res.user:
        raise HTTPException(401, "Invalid or expired token")
    return get_user_org(res.user.id, getattr(res.user, "email", None))


@api.post("/auth/signup")
def signup(body: AuthIn):
    # admin create -> email pre-confirmed, no email round-trip needed for demo
    try:
        res = service_client().auth.admin.create_user(
            {"email": body.email, "password": body.password, "email_confirm": True}
        )
        org = create_personal_org(res.user.id, body.email)
    except Exception as e:
        raise HTTPException(400, f"Signup failed: {e}")
    return {
        "user_id": res.user.id,
        "organization_id": org.organization_id,
        "message": "Account created. Now log in.",
    }


@api.post("/auth/login")
def login(body: AuthIn):
    try:
        res = anon_client().auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": res.session.access_token, "user_id": res.user.id}


# ---------- files ----------
@api.post("/upload")
async def upload(
    files: list[UploadFile] = File(...), ctx: AuthContext = Depends(get_auth_context)
):
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(400, f"Max {MAX_FILES_PER_BATCH} files per batch")

    job_id = None
    if ctx.org_enabled:
        job_id = create_job(
            ctx.user_id,
            ctx.organization_id,
            "document_ingestion",
            detail=f"{len(files)} file(s) queued for synchronous ingestion",
        )
    uploaded, replaced, skipped = [], [], []
    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    allowed = ", ".join(sorted(e.lstrip(".") for e in SUPPORTED_EXTENSIONS))

    for uf in files:
        data = await uf.read()
        ext = "." + uf.filename.rsplit(".", 1)[-1].lower() if "." in uf.filename else ""
        if len(data) > max_bytes:
            skipped.append({
                "filename": uf.filename,
                "reason": f"too large ({len(data)/1e6:.1f}MB, max {MAX_FILE_SIZE_MB}MB)",
            })
            continue
        if ext not in SUPPORTED_EXTENSIONS:
            skipped.append({
                "filename": uf.filename,
                "reason": f"type '{ext or '?'}' not supported (allowed: {allowed})",
            })
            continue

        action, info = dedupe_check(ctx.scope_id, uf.filename, data, ctx.org_enabled)
        if action == "skip":
            skipped.append({"filename": uf.filename, "reason": info})
            continue
        if action == "replace":
            delete_file(ctx.scope_id, info, ctx.org_enabled)

        try:
            res = ingest_one(
                ctx.user_id,
                ctx.organization_id,
                uf.filename,
                data,
                ctx.org_enabled,
            )
            (replaced if action == "replace" else uploaded).append(res)
        except Exception as e:
            skipped.append({"filename": uf.filename, "reason": str(e)})

    if job_id:
        update_job(
            job_id,
            "completed",
            metadata={
                "uploaded": len(uploaded),
                "replaced": len(replaced),
                "skipped": len(skipped),
            },
        )
    return {
        "job_id": job_id,
        "uploaded": uploaded,
        "replaced": replaced,
        "skipped": skipped,
        **corpus_stats(ctx.scope_id, ctx.org_enabled),
    }


@api.get("/files")
def list_files(ctx: AuthContext = Depends(get_auth_context)):
    sb = service_client()
    rows = (
        sb.table("files")
        .select("id, filename, file_type, char_count, upload_date, indexed")
        .eq(_scope_column(ctx), ctx.scope_id)
        .order("upload_date", desc=True)
        .execute()
        .data
        or []
    )
    return {"files": rows}


@api.delete("/files/{file_id}")
def delete_file_endpoint(file_id: str, ctx: AuthContext = Depends(get_auth_context)):
    sb = service_client()
    exists = (
        sb.table("files")
        .select("id")
        .eq("id", file_id)
        .eq(_scope_column(ctx), ctx.scope_id)
        .execute()
        .data
    )
    if not exists:
        raise HTTPException(404, "File not found")
    delete_file(ctx.scope_id, file_id, ctx.org_enabled)
    return {"deleted": file_id, **corpus_stats(ctx.scope_id, ctx.org_enabled)}


# ---------- query ----------
class AskIn(BaseModel):
    question: str


@api.post("/ask")
def ask_endpoint(body: AskIn, ctx: AuthContext = Depends(get_auth_context)):
    return ask(ctx.user_id, ctx.organization_id, body.question, ctx.org_enabled)


@api.post("/summarize")
def summarize_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    return summarize(ctx.scope_id, ctx.org_enabled)


@api.post("/report")
def report_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    return generate_report(ctx.user_id, ctx.organization_id, ctx.org_enabled)


@api.get("/reports")
def reports_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.org_enabled:
        return {"reports": []}
    return {"reports": list_reports(ctx.organization_id)}


@api.get("/reports/{report_id}")
def report_detail_endpoint(report_id: str, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.org_enabled:
        raise HTTPException(404, "Report history is not enabled until org schema is applied")
    report = get_report(ctx.organization_id, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@api.get("/jobs")
def jobs_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.org_enabled:
        return {"jobs": []}
    return {"jobs": list_jobs(ctx.organization_id)}


@api.get("/status")
def status(ctx: AuthContext = Depends(get_auth_context)):
    return {
        **corpus_stats(ctx.scope_id, ctx.org_enabled),
        "organization_id": ctx.organization_id,
        "organization_name": ctx.organization_name,
        "org_enabled": ctx.org_enabled,
    }


# ---------- memory ----------
@api.get("/memories")
def list_memories_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    return {"memories": list_memories(ctx.user_id)}


@api.delete("/memories/{mem_id}")
def delete_memory_endpoint(mem_id: str, ctx: AuthContext = Depends(get_auth_context)):
    delete_memory(ctx.user_id, mem_id)
    return {"deleted": mem_id}


@api.get("/health")
def health():
    return {"ok": True}


app.include_router(api)

# Serve the built web SPA (web/out) at /. Mounted last so /api and /docs win.
_WEB_DIR = Path(__file__).resolve().parents[2] / "web" / "out"
if _WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
