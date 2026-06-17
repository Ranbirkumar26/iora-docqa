"""FastAPI app. API under /api; serves the built web SPA (web/out) at /."""
from pathlib import Path

import httpx
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
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import (
    MAX_FILE_SIZE_MB,
    MAX_FILES_PER_BATCH,
    STORAGE_BUCKET,
    SUPPORTED_EXTENSIONS,
)
from app.core.corpus import corpus_stats
from app.core.ingest import dedupe_check, delete_file, ingest_one
from app.core.jobs import create_job, list_jobs, update_job
from app.core.memory import delete_memory, list_memories
from app.core.orgs import (
    AuthContext,
    VALID_ROLES,
    create_personal_org,
    get_user_org,
    list_org_members,
    normalize_role,
    set_org_member_role,
)
from app.core.outputs import (
    attach_export_to_repository,
    build_conversation_export,
    get_output,
    list_messages,
    list_outputs,
    output_counts,
    save_output,
)
from app.core.qa import ask
from app.core.report import generate_report, get_report, list_reports
from app.core.search import search_chunks
from app.core.summarize import summarize
from app.db.client import anon_client, fresh_anon_client, service_client

app = FastAPI(title="DocQA")
api = APIRouter(prefix="/api")


def _scope_column(ctx: AuthContext) -> str:
    return "organization_id" if ctx.read_scope_uses_org else "user_id"


def _write_scope_column(ctx: AuthContext) -> str:
    return "organization_id" if ctx.write_scope_uses_org else "user_id"


def _require_can_upload(ctx: AuthContext) -> None:
    if not ctx.can_upload:
        raise HTTPException(403, "Authors are read-only and cannot upload documents")


def _require_can_delete(ctx: AuthContext) -> None:
    if not ctx.can_delete:
        raise HTTPException(403, "Authors are read-only and cannot delete documents")


def _require_admin(ctx: AuthContext) -> None:
    if not ctx.can_write_all:
        raise HTTPException(403, "Admin access required")


@app.exception_handler(RuntimeError)
def _runtime_error(request: Request, exc: RuntimeError):
    # e.g. Gemini rate limit -> clean 429 the UI can show
    return JSONResponse(status_code=429, content={"detail": str(exc)})


# ---------- auth ----------
class AuthIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


def _session_payload(res) -> dict:
    session = getattr(res, "session", None)
    user = getattr(res, "user", None)
    if not session or not getattr(session, "access_token", None):
        raise HTTPException(401, "Invalid credentials")
    return {
        "access_token": session.access_token,
        "refresh_token": getattr(session, "refresh_token", None),
        "expires_at": getattr(session, "expires_at", None),
        "expires_in": getattr(session, "expires_in", None),
        "user_id": getattr(user, "id", None),
    }


def get_auth_context(authorization: str = Header(None)) -> AuthContext:
    """Verify Bearer JWT and return user + active organisation context."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        res = anon_client().auth.get_user(token)
    except httpx.TransportError:
        raise HTTPException(503, "Auth service temporarily unavailable")
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
        res = fresh_anon_client().auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception:
        raise HTTPException(401, "Invalid credentials")
    return _session_payload(res)


@api.post("/auth/refresh")
def refresh(body: RefreshIn):
    try:
        res = fresh_anon_client().auth.refresh_session(body.refresh_token)
    except httpx.TransportError:
        raise HTTPException(503, "Auth service temporarily unavailable")
    except Exception:
        raise HTTPException(401, "Session expired. Please log in again.")
    return _session_payload(res)


# ---------- files ----------
@api.post("/upload")
async def upload(
    files: list[UploadFile] = File(...), ctx: AuthContext = Depends(get_auth_context)
):
    _require_can_upload(ctx)
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

        action, info = dedupe_check(
            ctx.write_scope_id,
            uf.filename,
            data,
            ctx.write_scope_uses_org,
        )
        if action == "skip":
            skipped.append({"filename": uf.filename, "reason": info})
            continue
        if action == "replace":
            delete_file(ctx.write_scope_id, info, ctx.write_scope_uses_org)

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
        **corpus_stats(ctx.scope_id, ctx.read_scope_uses_org),
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
    _require_can_delete(ctx)
    sb = service_client()
    exists = (
        sb.table("files")
        .select("id")
        .eq("id", file_id)
        .eq(_write_scope_column(ctx), ctx.write_scope_id)
        .execute()
        .data
    )
    if not exists:
        raise HTTPException(404, "File not found")
    delete_file(ctx.write_scope_id, file_id, ctx.write_scope_uses_org)
    return {"deleted": file_id, **corpus_stats(ctx.scope_id, ctx.read_scope_uses_org)}


# ---------- query ----------
class AskIn(BaseModel):
    question: str


class SummarizeIn(BaseModel):
    collective: bool = False


class ReportIn(BaseModel):
    collective: bool = False


class ConversationExportIn(BaseModel):
    format: str = "markdown"
    attach: bool = False


class MemberRoleIn(BaseModel):
    role: str


@api.post("/ask")
def ask_endpoint(body: AskIn, ctx: AuthContext = Depends(get_auth_context)):
    return ask(
        ctx.user_id,
        ctx.organization_id,
        body.question,
        ctx.read_scope_uses_org,
        persist=not ctx.is_read_only,
        allow_memory_write=not ctx.is_read_only,
    )


@api.get("/search")
def search_endpoint(
    q: str = "",
    limit: int = 15,
    ctx: AuthContext = Depends(get_auth_context),
):
    """Keyword (full-text) search over the user's own document chunks.

    Read-only — available to every role, including authors. Strictly user-scoped
    (passes None for org so search_chunks filters by user_id only).
    """
    query = q.strip()
    if not query:
        return {"query": "", "results": []}
    capped = max(1, min(limit, 50))
    results = search_chunks(
        ctx.user_id,
        query,
        capped,
        ctx.organization_id if ctx.read_scope_uses_org else None,
    )
    return {"query": query, "results": results}


@api.post("/summarize")
def summarize_endpoint(
    body: SummarizeIn | None = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    if ctx.is_read_only:
        raise HTTPException(
            403,
            "Authors are read-only. Use Ask to query your saved documents.",
        )
    return summarize(
        ctx.user_id,
        ctx.organization_id,
        ctx.read_scope_uses_org,
        collective=bool(body and body.collective),
    )


@api.post("/report")
def report_endpoint(
    body: ReportIn | None = None,
    ctx: AuthContext = Depends(get_auth_context),
):
    if ctx.is_read_only:
        raise HTTPException(403, "Authors are read-only and cannot generate saved reports")
    return generate_report(
        ctx.user_id,
        ctx.organization_id,
        ctx.read_scope_uses_org,
        collective=bool(body and body.collective),
    )


@api.get("/conversation")
def conversation_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    return {
        "messages": list_messages(
            ctx.user_id,
            ctx.organization_id,
            ctx.read_scope_uses_org,
        )
    }


@api.post("/conversation/export")
def conversation_export_endpoint(
    body: ConversationExportIn,
    ctx: AuthContext = Depends(get_auth_context),
):
    export_format = body.format.lower().strip()
    if export_format not in {"markdown", "md", "txt", "text"}:
        raise HTTPException(400, "Export format must be markdown or txt")
    normalized = "txt" if export_format in {"txt", "text"} else "markdown"
    filename, mime_type, content = build_conversation_export(
        ctx.user_id,
        ctx.organization_id,
        ctx.read_scope_uses_org,
        normalized,
    )
    attached_file = None
    if body.attach:
        _require_can_upload(ctx)
        attached_file = attach_export_to_repository(
            ctx.user_id,
            ctx.organization_id,
            filename,
            content,
            ctx.org_enabled,
        )
    if not ctx.is_read_only:
        save_output(
            ctx.user_id,
            ctx.organization_id,
            "conversation_export",
            f"Conversation export: {filename}",
            content,
            ctx.read_scope_uses_org,
            format="text" if normalized == "txt" else "markdown",
            sources=[filename],
            metadata={
                "filename": filename,
                "mime_type": mime_type,
                "attached": bool(body.attach),
                "attached_file": attached_file,
            },
        )
    return {
        "filename": filename,
        "mime_type": mime_type,
        "content": content,
        "attached": bool(body.attach),
        "attached_file": attached_file,
    }


@api.get("/outputs")
def outputs_endpoint(kind: str | None = None, ctx: AuthContext = Depends(get_auth_context)):
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None
    return {
        "outputs": list_outputs(
            ctx.user_id,
            ctx.organization_id,
            ctx.read_scope_uses_org,
            kinds=kinds,
        )
    }


@api.get("/outputs/{output_id}/download")
def output_download_endpoint(output_id: str, ctx: AuthContext = Depends(get_auth_context)):
    output = get_output(ctx.user_id, ctx.organization_id, output_id, ctx.read_scope_uses_org)
    if not output:
        raise HTTPException(404, "Output not found")
    metadata = output.get("metadata") or {}
    filename = metadata.get("download_filename") or f"{output['title']}.txt"
    mime_type = metadata.get("content_type") or "text/plain"
    if output.get("storage_path"):
        data = service_client().storage.from_(STORAGE_BUCKET).download(
            output["storage_path"]
        )
        return Response(
            data,
            media_type=mime_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return Response(
        output["content"].encode("utf-8"),
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.get("/reports")
def reports_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.org_enabled:
        return {"reports": []}
    return {"reports": list_reports(ctx.scope_id, ctx.read_scope_uses_org)}


@api.get("/reports/{report_id}")
def report_detail_endpoint(report_id: str, ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.org_enabled:
        raise HTTPException(404, "Report history is not enabled until org schema is applied")
    report = get_report(ctx.scope_id, report_id, ctx.read_scope_uses_org)
    if not report:
        raise HTTPException(404, "Report not found")
    return report


@api.get("/jobs")
def jobs_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    if not ctx.org_enabled:
        return {"jobs": []}
    return {"jobs": list_jobs(ctx.scope_id, ctx.read_scope_uses_org)}


@api.get("/status")
def status(ctx: AuthContext = Depends(get_auth_context)):
    return {
        **corpus_stats(ctx.scope_id, ctx.read_scope_uses_org),
        **output_counts(ctx.user_id, ctx.organization_id, ctx.read_scope_uses_org),
        "organization_id": ctx.organization_id,
        "organization_name": ctx.organization_name,
        "org_enabled": ctx.org_enabled,
        "user_id": ctx.user_id,
        "role": ctx.role,
        "can_read_all": ctx.can_read_all,
        "can_write_all": ctx.can_write_all,
        "is_read_only": ctx.is_read_only,
        "can_upload": ctx.can_upload,
        "can_delete": ctx.can_delete,
    }


# ---------- organisation members ----------
@api.get("/members")
def members_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    _require_admin(ctx)
    return {"members": list_org_members(ctx.organization_id)}


@api.patch("/members/{member_user_id}")
def update_member_role_endpoint(
    member_user_id: str,
    body: MemberRoleIn,
    ctx: AuthContext = Depends(get_auth_context),
):
    _require_admin(ctx)
    raw_role = (body.role or "").strip().lower()
    if raw_role not in VALID_ROLES:
        raise HTTPException(400, "Role must be user, author, or admin")
    role = normalize_role(body.role)
    try:
        saved = set_org_member_role(ctx.organization_id, member_user_id, role)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not saved:
        raise HTTPException(404, "Member not found")
    return {"member": {**saved, "role": normalize_role(saved.get("role"))}}


# ---------- memory ----------
@api.get("/memories")
def list_memories_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    return {"memories": list_memories(ctx.user_id)}


@api.delete("/memories/{mem_id}")
def delete_memory_endpoint(mem_id: str, ctx: AuthContext = Depends(get_auth_context)):
    if ctx.is_read_only:
        raise HTTPException(403, "Authors are read-only and cannot delete memory")
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
