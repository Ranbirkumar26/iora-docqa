"""Central config. Loads .env, exposes settings."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- secrets ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")            # fallback LLM (OpenRouter)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")            # fallback LLM (Groq Cloud)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # optional, for claude provider
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")        # optional, for voyage embeddings
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# --- access control ---
# Bootstrap admin emails are the only accounts promoted automatically. Everyone
# else starts as a normal user until an admin changes their role in the app.
APP_ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("APP_ADMIN_EMAILS", "rk26.ftw@gmail.com").split(",")
    if email.strip()
}
DEFAULT_ORGANIZATION_NAME = os.getenv("DEFAULT_ORGANIZATION_NAME", "iORA Workspace")

# Optional signup allowlist. Empty = open signup. Set to a comma-separated list
# of domains (e.g. "acme.com,acme.io") to restrict new accounts to those domains.
APP_ALLOWED_EMAIL_DOMAINS = {
    d.strip().lower().lstrip("@")
    for d in os.getenv("APP_ALLOWED_EMAIL_DOMAINS", "").split(",")
    if d.strip()
}

# Base URL the password-recovery email link redirects back to. Must be listed
# in Supabase Auth -> URL Configuration -> Redirect URLs. Override per env
# (e.g. http://localhost:8000 for local dev).
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://iora-docqa-copy-production.up.railway.app")

# Content-Security-Policy ships report-only by default so it cannot break the
# SPA; set CSP_ENFORCE=true once violation reports look clean to enforce it.
CSP_ENFORCE = os.getenv("CSP_ENFORCE", "").strip().lower() in {"1", "true", "yes", "on"}

# Defense-in-depth: when true, reads run through a user-JWT client so Postgres
# RLS enforces (on top of the application-code user_id filters). Off by default
# until verified live against the RLS policies (a mismatch would empty reads).
RLS_SCOPED_READS = os.getenv("RLS_SCOPED_READS", "").strip().lower() in {"1", "true", "yes", "on"}

# --- LLM fallback chain ---
# Ordered, comma-separated provider names. First is the everyday primary; each
# next is tried when the previous is rate-limited. Providers without a key set
# are skipped, so the chain works incrementally as keys are added.
LLM_CHAIN = os.getenv("LLM_CHAIN", "groq,gemini,qwen")  # qwen | groq | gemini | claude
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "gemini")  # gemini | voyage

# --- models ---
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_EMBED_MODEL = "gemini-embedding-001"
CLAUDE_MODEL = "claude-sonnet-4-6"
VOYAGE_MODEL = "voyage-3.5"

# Qwen via OpenRouter (OpenAI-compatible). Free model; coder-tuned but usable.
# Swap QWEN_MODEL to a general :free Qwen for better prose Q&A.
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen/qwen3-coder:free")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://openrouter.ai/api/v1")

# OpenRouter ranking headers (optional, harmless on other endpoints)
OPENROUTER_REFERER = os.getenv("OPENROUTER_REFERER", "https://docqa-production.up.railway.app")
OPENROUTER_TITLE = os.getenv("OPENROUTER_TITLE", "iORA DocQA")

# Groq (OpenAI-compatible). Fast, generous free tier.
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

# embedding dimension MUST match the active EMBED_PROVIDER + DB schema
# gemini text-embedding-004 -> 768 ; voyage-3.5 -> 1024
EMBED_DIM = 768

# --- mode detection ---
# below this total-corpus token estimate -> stuff full context; above -> RAG
DIRECT_MODE_TOKEN_LIMIT = int(os.getenv("DIRECT_MODE_TOKEN_LIMIT", "10000"))

# --- chunking (approx chars; ~4 chars per token) ---
CHUNK_SIZE_CHARS = 3200      # ~800 tokens
CHUNK_OVERLAP_CHARS = 400    # ~100 tokens

# --- upload limits ---
MAX_FILES_PER_BATCH = 100
MAX_FILE_SIZE_MB = 10
MAX_TOTAL_UPLOAD_MB = int(os.getenv("MAX_TOTAL_UPLOAD_MB", "50"))  # cap per request
SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".xlsx", ".pdf", ".docx"}

# --- storage ---
STORAGE_BUCKET = "user-documents"


def chars_to_tokens(n_chars: int) -> int:
    """Rough token estimate. Good enough for mode detection."""
    return n_chars // 4
