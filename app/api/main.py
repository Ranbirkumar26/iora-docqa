"""FastAPI app. Auth + upload + ask + summarize + files management."""
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import (
    MAX_FILE_SIZE_MB,
    MAX_FILES_PER_BATCH,
    SUPPORTED_EXTENSIONS,
)
from app.core.corpus import corpus_stats
from app.core.ingest import dedupe_check, delete_file, ingest_one
from app.core.qa import ask
from app.core.summarize import summarize
from app.db.client import anon_client, service_client

app = FastAPI(title="DocQA")


@app.exception_handler(RuntimeError)
def _runtime_error(request: Request, exc: RuntimeError):
    # e.g. Gemini rate limit -> clean 429 the UI can show
    return JSONResponse(status_code=429, content={"detail": str(exc)})


# ---------- auth ----------
class AuthIn(BaseModel):
    email: str
    password: str


def get_user_id(authorization: str = Header(None)) -> str:
    """Verify Bearer JWT via Supabase, return the user's id."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization.split(" ", 1)[1]
    try:
        res = anon_client().auth.get_user(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    if not res or not res.user:
        raise HTTPException(401, "Invalid or expired token")
    return res.user.id


@app.post("/auth/signup")
def signup(body: AuthIn):
    # admin create -> email pre-confirmed, no email round-trip needed for demo
    try:
        res = service_client().auth.admin.create_user(
            {"email": body.email, "password": body.password, "email_confirm": True}
        )
    except Exception as e:
        raise HTTPException(400, f"Signup failed: {e}")
    return {"user_id": res.user.id, "message": "Account created. Now log in."}


@app.post("/auth/login")
def login(body: AuthIn):
    try:
        res = anon_client().auth.sign_in_with_password(
            {"email": body.email, "password": body.password}
        )
    except Exception:
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": res.session.access_token, "user_id": res.user.id}


# ---------- files ----------
@app.post("/upload")
async def upload(
    files: list[UploadFile] = File(...), user_id: str = Depends(get_user_id)
):
    if len(files) > MAX_FILES_PER_BATCH:
        raise HTTPException(400, f"Max {MAX_FILES_PER_BATCH} files per batch")

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

        action, info = dedupe_check(user_id, uf.filename, data)
        if action == "skip":
            skipped.append({"filename": uf.filename, "reason": info})
            continue
        if action == "replace":
            delete_file(user_id, info)  # drop old version + its chunks

        try:
            res = ingest_one(user_id, uf.filename, data)
            (replaced if action == "replace" else uploaded).append(res)
        except Exception as e:
            skipped.append({"filename": uf.filename, "reason": str(e)})

    return {
        "uploaded": uploaded,
        "replaced": replaced,
        "skipped": skipped,
        **corpus_stats(user_id),
    }


@app.get("/files")
def list_files(user_id: str = Depends(get_user_id)):
    sb = service_client()
    rows = (
        sb.table("files")
        .select("id, filename, file_type, char_count, upload_date, indexed")
        .eq("user_id", user_id)
        .order("upload_date", desc=True)
        .execute()
        .data
        or []
    )
    return {"files": rows}


@app.delete("/files/{file_id}")
def delete_file_endpoint(file_id: str, user_id: str = Depends(get_user_id)):
    sb = service_client()
    exists = (
        sb.table("files").select("id").eq("id", file_id).eq("user_id", user_id).execute().data
    )
    if not exists:
        raise HTTPException(404, "File not found")
    delete_file(user_id, file_id)  # storage + row (+ chunks cascade)
    return {"deleted": file_id, **corpus_stats(user_id)}


# ---------- query ----------
class AskIn(BaseModel):
    question: str


@app.post("/ask")
def ask_endpoint(body: AskIn, user_id: str = Depends(get_user_id)):
    return ask(user_id, body.question)


@app.post("/summarize")
def summarize_endpoint(user_id: str = Depends(get_user_id)):
    return summarize(user_id)


@app.get("/status")
def status(user_id: str = Depends(get_user_id)):
    return corpus_stats(user_id)


@app.get("/health")
def health():
    return {"ok": True}
