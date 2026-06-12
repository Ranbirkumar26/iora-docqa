"""Central config. Loads .env, exposes settings."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- secrets ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")            # fallback LLM when Gemini rate-limits
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")  # optional, for claude provider
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")        # optional, for voyage embeddings
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# --- providers (swap by env without code changes) ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")      # gemini | claude
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "gemini")  # gemini | voyage
# automatic fallback to Qwen when the primary LLM is rate-limited (set QWEN_API_KEY)
LLM_FALLBACK = os.getenv("LLM_FALLBACK", "qwen")        # qwen | "" (disable)

# --- models ---
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_EMBED_MODEL = "gemini-embedding-001"
CLAUDE_MODEL = "claude-sonnet-4-6"
VOYAGE_MODEL = "voyage-3.5"

# Qwen via an OpenAI-compatible endpoint. Default = Alibaba DashScope (intl).
# OpenRouter override: base https://openrouter.ai/api/v1, model qwen/qwen-2.5-72b-instruct
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")
QWEN_BASE_URL = os.getenv(
    "QWEN_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
)

# embedding dimension MUST match the active EMBED_PROVIDER + DB schema
# gemini text-embedding-004 -> 768 ; voyage-3.5 -> 1024
EMBED_DIM = 768

# --- mode detection ---
# below this total-corpus token estimate -> stuff full context; above -> RAG
DIRECT_MODE_TOKEN_LIMIT = int(os.getenv("DIRECT_MODE_TOKEN_LIMIT", "150000"))

# --- chunking (approx chars; ~4 chars per token) ---
CHUNK_SIZE_CHARS = 3200      # ~800 tokens
CHUNK_OVERLAP_CHARS = 400    # ~100 tokens

# --- upload limits ---
MAX_FILES_PER_BATCH = 100
MAX_FILE_SIZE_MB = 10
SUPPORTED_EXTENSIONS = {".txt", ".csv", ".xlsx"}

# --- storage ---
STORAGE_BUCKET = "user-documents"


def chars_to_tokens(n_chars: int) -> int:
    """Rough token estimate. Good enough for mode detection."""
    return n_chars // 4
