"""FastAPI app. API under /api; serves the built web SPA (web/out) at /."""
import logging
from dataclasses import replace
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
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import (
    APP_BASE_URL,
    CSP_ENFORCE,
    MAX_FILE_SIZE_MB,
    MAX_FILES_PER_BATCH,
    MAX_TOTAL_UPLOAD_MB,
    STORAGE_BUCKET,
    SUPPORTED_EXTENSIONS,
)
from app.core import mfa
from app.core.account import delete_account
from app.core.audit import list_audit, write_audit
from app.core.corpus import corpus_stats
from app.core.passwords import validate_password
from app.core.ingest import dedupe_check, delete_file, ingest_one
from app.core.jobs import create_job, list_jobs, update_job
from app.core.memory import delete_memory, list_memories
from app.core.orgs import (
    AuthContext,
    VALID_ROLES,
    email_domain_allowed,
    get_user_org,
    is_bootstrap_admin,
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


def _client_ip(request: Request) -> str:
    """Real client IP, honouring the proxy's X-Forwarded-For (Railway terminates TLS)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


def _auth_key(request: Request) -> str:
    """Rate-limit key for authenticated routes: per bearer token, else per IP."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return "tok:" + auth[7:][:48]
    return _client_ip(request)


def _bearer(authorization: str | None) -> str:
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    return ""


limiter = Limiter(key_func=_client_ip)
app.state.limiter = limiter


def _rate_limited(request: Request, exc: RateLimitExceeded):
    # match the API's {"detail": ...} shape so the SPA shows a clean message
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please slow down and try again shortly."},
    )


app.add_exception_handler(RateLimitExceeded, _rate_limited)


_CSP = (
    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
    "img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'"
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
    )
    # report-only by default (CSP_ENFORCE=false) so it can't break the SPA
    csp_header = (
        "Content-Security-Policy" if CSP_ENFORCE else "Content-Security-Policy-Report-Only"
    )
    response.headers.setdefault(csp_header, _CSP)
    return response


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


logger = logging.getLogger("docqa")


@app.exception_handler(Exception)
def _unhandled(request: Request, exc: Exception):
    # last resort: log the trace server-side, return a sanitized 500 to the client
    logger.exception("Unhandled error: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong. Please try again."},
    )


# ---------- auth ----------
class AuthIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordResetRequestIn(BaseModel):
    email: EmailStr


class PasswordUpdateIn(BaseModel):
    password: str


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str


class ResendIn(BaseModel):
    email: EmailStr


class MfaSessionIn(BaseModel):
    refresh_token: str


class MfaVerifyIn(BaseModel):
    factor_id: str
    code: str
    refresh_token: str


class MfaUnenrollIn(BaseModel):
    factor_id: str
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
    ctx = get_user_org(res.user.id, getattr(res.user, "email", None))
    return replace(ctx, access_token=token)


@api.post("/auth/signup")
@limiter.limit("5/minute")
def signup(request: Request, body: AuthIn):
    """Create an account and send a confirmation email.

    Uses the public sign-up flow so Supabase emails a verification link; with
    "Confirm email" enabled the user must verify before logging in. The response
    is generic and never reveals whether an email already has an account. The org
    membership is created lazily on the first authenticated request (get_user_org).
    """
    email = (body.email or "").strip().lower()
    if not email_domain_allowed(email):
        raise HTTPException(403, "Sign-ups are restricted to approved email domains")
    pw_err = validate_password(body.password)
    if pw_err:
        raise HTTPException(400, pw_err)
    try:
        res = fresh_anon_client().auth.sign_up(
            {
                "email": email,
                "password": body.password,
                "options": {"email_redirect_to": APP_BASE_URL},
            }
        )
    except Exception:
        # don't leak existence or provider error detail
        return {
            "needs_confirmation": True,
            "message": "Check your email to confirm your account, then log in.",
        }
    session = getattr(res, "session", None)
    user = getattr(res, "user", None)
    needs_confirmation = session is None
    return {
        "user_id": getattr(user, "id", None),
        "needs_confirmation": needs_confirmation,
        "message": (
            "Check your email to confirm your account, then log in."
            if needs_confirmation
            else "Account created. You can log in now."
        ),
    }


@api.post("/auth/resend")
@limiter.limit("5/minute")
def resend_confirmation(request: Request, body: ResendIn):
    """Re-send the signup confirmation email. Generic response (no enumeration)."""
    email = (body.email or "").strip().lower()
    if email:
        try:
            fresh_anon_client().auth.resend(
                {
                    "type": "signup",
                    "email": email,
                    "options": {"email_redirect_to": APP_BASE_URL},
                }
            )
        except Exception:
            pass
    return {
        "ok": True,
        "message": "If that account needs confirmation, a new email is on its way.",
    }


@api.post("/auth/mfa/enroll")
@limiter.limit("10/minute", key_func=_auth_key)
def mfa_enroll(
    request: Request,
    body: MfaSessionIn,
    authorization: str = Header(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Begin TOTP enrollment. Returns the QR/secret to display once."""
    try:
        return mfa.enroll(_bearer(authorization), body.refresh_token)
    except Exception:
        raise HTTPException(400, "Could not start MFA enrollment")


@api.post("/auth/mfa/verify")
@limiter.limit("10/minute", key_func=_auth_key)
def mfa_verify(
    request: Request,
    body: MfaVerifyIn,
    authorization: str = Header(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Verify a TOTP code — completes enrollment or upgrades a login to AAL2.

    Returns the upgraded session tokens for the SPA to adopt.
    """
    try:
        session = mfa.verify(
            _bearer(authorization), body.refresh_token, body.factor_id, body.code
        )
    except Exception:
        raise HTTPException(400, "Invalid or expired code")
    if not session.get("access_token"):
        raise HTTPException(400, "Invalid or expired code")
    return session


@api.post("/auth/mfa/unenroll")
def mfa_unenroll(
    body: MfaUnenrollIn,
    authorization: str = Header(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    try:
        mfa.unenroll(_bearer(authorization), body.refresh_token, body.factor_id)
    except Exception:
        raise HTTPException(400, "Could not disable MFA")
    return {"ok": True}


@api.post("/auth/mfa/factors")
def mfa_factors(
    body: MfaSessionIn,
    authorization: str = Header(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    try:
        return {"factors": mfa.list_factors(_bearer(authorization), body.refresh_token)}
    except Exception:
        return {"factors": []}


@api.post("/auth/login")
@limiter.limit("10/minute")
def login(request: Request, body: AuthIn):
    client = fresh_anon_client()
    try:
        res = client.auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except httpx.TransportError:
        raise HTTPException(503, "Auth service temporarily unavailable")
    except Exception:
        raise HTTPException(401, "Invalid credentials")
    payload = _session_payload(res)
    # If the account has a verified second factor, signal the SPA to collect a
    # TOTP code and upgrade the session via /auth/mfa/verify.
    state = mfa.login_mfa_state(client)
    if state:
        payload["mfa_required"] = True
        payload["factor_id"] = state["factor_id"]
    return payload


@api.post("/auth/refresh")
def refresh(body: RefreshIn):
    try:
        res = fresh_anon_client().auth.refresh_session(body.refresh_token)
    except httpx.TransportError:
        raise HTTPException(503, "Auth service temporarily unavailable")
    except Exception:
        raise HTTPException(401, "Session expired. Please log in again.")
    return _session_payload(res)


@api.post("/auth/request-password-reset")
@limiter.limit("5/minute")
def request_password_reset(request: Request, body: PasswordResetRequestIn):
    """Ask Supabase to email a recovery link to the address.

    Always returns the same generic response, so the endpoint cannot be used to
    enumerate which emails have accounts. The reset link is delivered only to the
    address owner's inbox — no token or link is ever returned here.
    """
    email = (body.email or "").strip().lower()
    if email:
        try:
            fresh_anon_client().auth.reset_password_for_email(
                email, {"redirect_to": APP_BASE_URL}
            )
        except Exception:
            # never reveal whether the address exists or why delivery failed
            pass
    return {"ok": True, "message": "If that email has an account, a reset link is on its way."}


@api.post("/auth/update-password")
def update_password(
    body: PasswordUpdateIn, ctx: AuthContext = Depends(get_auth_context)
):
    """Set a new password for the caller.

    The account is identified solely by the verified bearer token (a recovery-link
    session, or a normal logged-in session) — never by anything in the request
    body — so a caller can only ever change their own password. The new secret is
    not logged or echoed back.
    """
    password = body.password or ""
    pw_err = validate_password(password)
    if pw_err:
        raise HTTPException(400, pw_err)
    try:
        service_client().auth.admin.update_user_by_id(
            ctx.user_id, {"password": password}
        )
    except Exception:
        raise HTTPException(
            400, "Could not update password. Request a fresh reset link and try again."
        )
    return {"ok": True}


@api.post("/auth/change-password")
def change_password(
    body: PasswordChangeIn, ctx: AuthContext = Depends(get_auth_context)
):
    """Change password for a logged-in user.

    Re-authenticates with the CURRENT password first, so a stolen session token
    alone cannot silently re-key the account. Account is the verified token's
    user; the new secret is never logged or echoed.
    """
    new_password = body.new_password or ""
    pw_err = validate_password(new_password)
    if pw_err:
        raise HTTPException(400, pw_err)
    # resolve the caller's email to re-authenticate
    try:
        admin_user = service_client().auth.admin.get_user_by_id(ctx.user_id)
        email = getattr(getattr(admin_user, "user", None), "email", None)
    except Exception:
        email = None
    if not email:
        raise HTTPException(400, "Could not verify this account")
    # verify the current password
    try:
        res = fresh_anon_client().auth.sign_in_with_password(
            {"email": email, "password": body.current_password or ""}
        )
        if not getattr(res, "session", None):
            raise ValueError("no session")
    except Exception:
        raise HTTPException(403, "Current password is incorrect")
    # set the new password
    try:
        service_client().auth.admin.update_user_by_id(
            ctx.user_id, {"password": new_password}
        )
    except Exception:
        raise HTTPException(400, "Could not update password")
    return {"ok": True}


@api.post("/auth/logout-all")
def logout_all(
    authorization: str = Header(None),
    ctx: AuthContext = Depends(get_auth_context),
):
    """Revoke all of the caller's sessions across every device.

    Uses the verified bearer token, so it only affects the caller's own account.
    """
    token = (
        authorization.split(" ", 1)[1]
        if authorization and authorization.startswith("Bearer ")
        else ""
    )
    try:
        service_client().auth.admin.sign_out(token, "global")
    except Exception:
        raise HTTPException(400, "Could not sign out all sessions")
    return {"ok": True}


@api.delete("/account")
def delete_account_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    """Permanently delete the caller's account and all their data. Irreversible.

    Scoped to the verified token's user, so it can only ever delete the caller's
    own account — never another user's.
    """
    try:
        delete_account(ctx.user_id)
    except Exception:
        raise HTTPException(500, "Could not fully delete the account. Please try again.")
    return {"deleted": True}


# ---------- files ----------
@api.post("/upload")
@limiter.limit("20/minute", key_func=_auth_key)
async def upload(
    request: Request,
    files: list[UploadFile] = File(...),
    ctx: AuthContext = Depends(get_auth_context),
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
    max_total = MAX_TOTAL_UPLOAD_MB * 1024 * 1024
    total_bytes = 0
    allowed = ", ".join(sorted(e.lstrip(".") for e in SUPPORTED_EXTENSIONS))

    for uf in files:
        data = await uf.read()
        total_bytes += len(data)
        if total_bytes > max_total:
            skipped.append({
                "filename": uf.filename,
                "reason": f"batch exceeds {MAX_TOTAL_UPLOAD_MB}MB total; remaining files skipped",
            })
            break
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
    question: str = Field(min_length=1, max_length=8000)


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
@limiter.limit("30/minute", key_func=_auth_key)
def ask_endpoint(
    request: Request, body: AskIn, ctx: AuthContext = Depends(get_auth_context)
):
    return ask(
        ctx.user_id,
        ctx.organization_id,
        body.question,
        ctx.read_scope_uses_org,
        persist=not ctx.is_read_only,
        allow_memory_write=not ctx.is_read_only,
        token=ctx.access_token,
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
        token=ctx.access_token,
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
    write_audit(
        ctx.organization_id, ctx.user_id, "role_change", member_user_id,
        f"role set to {role}",
    )
    return {"member": {**saved, "role": normalize_role(saved.get("role"))}}


def _is_bootstrap_member(user_id: str) -> bool:
    try:
        res = service_client().auth.admin.get_user_by_id(user_id)
        return is_bootstrap_admin(getattr(getattr(res, "user", None), "email", None))
    except Exception:
        return False


@api.post("/members/{member_user_id}/suspend")
def suspend_member_endpoint(
    member_user_id: str, ctx: AuthContext = Depends(get_auth_context)
):
    _require_admin(ctx)
    if _is_bootstrap_member(member_user_id):
        raise HTTPException(403, "Cannot suspend a bootstrap admin")
    try:
        service_client().auth.admin.update_user_by_id(
            member_user_id, {"ban_duration": "876000h"}
        )
    except Exception:
        raise HTTPException(400, "Could not suspend user")
    write_audit(ctx.organization_id, ctx.user_id, "suspend", member_user_id)
    return {"suspended": member_user_id}


@api.post("/members/{member_user_id}/unsuspend")
def unsuspend_member_endpoint(
    member_user_id: str, ctx: AuthContext = Depends(get_auth_context)
):
    _require_admin(ctx)
    try:
        service_client().auth.admin.update_user_by_id(
            member_user_id, {"ban_duration": "none"}
        )
    except Exception:
        raise HTTPException(400, "Could not reinstate user")
    write_audit(ctx.organization_id, ctx.user_id, "unsuspend", member_user_id)
    return {"unsuspended": member_user_id}


@api.delete("/members/{member_user_id}")
def remove_member_endpoint(
    member_user_id: str, ctx: AuthContext = Depends(get_auth_context)
):
    _require_admin(ctx)
    if _is_bootstrap_member(member_user_id):
        raise HTTPException(403, "Cannot remove a bootstrap admin")
    try:
        delete_account(member_user_id)
    except Exception:
        raise HTTPException(500, "Could not remove user")
    write_audit(ctx.organization_id, ctx.user_id, "remove", member_user_id)
    return {"removed": member_user_id}


@api.get("/audit")
def audit_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    _require_admin(ctx)
    return {"events": list_audit(ctx.organization_id)}


@api.post("/members/{member_user_id}/mfa-reset")
def mfa_reset_endpoint(
    member_user_id: str, ctx: AuthContext = Depends(get_auth_context)
):
    """Admin recovery: clear a locked-out user's MFA factors."""
    _require_admin(ctx)
    try:
        removed = mfa.admin_reset(member_user_id)
    except Exception:
        raise HTTPException(400, "Could not reset MFA for this user")
    write_audit(
        ctx.organization_id, ctx.user_id, "mfa_reset", member_user_id,
        f"removed {removed} factor(s)",
    )
    return {"ok": True, "removed": removed}


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
