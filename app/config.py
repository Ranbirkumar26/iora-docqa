"""Central config. Loads .env, exposes settings."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- secrets ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")

# --- models ---
CLAUDE_MODEL = "claude-sonnet-4-6"
VOYAGE_MODEL = "voyage-3.5"
EMBED_DIM = 1024  # voyage-3.5 default output dimension

# --- mode detection ---
# below this total-corpus token estimate -> stuff full context; above -> RAG
DIRECT_MODE_TOKEN_LIMIT = 150_000

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
