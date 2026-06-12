"""Per-user memory: facts the user explicitly asks to remember.

Capture is heuristic (swappable to an LLM intent check later). Memories are
injected into the Q&A system prompt so the assistant can answer about the user.
"""
import re

from app.db.client import service_client, transient_retry

MAX_MEMORIES = 30
MAX_LEN = 200

# explicit "remember this" phrasings -> capture the remainder
_TRIGGERS = [
    r"^remember(?:\s+that)?\s+(.+)",
    r"^note(?:\s+that)?\s+(.+)",
    r"^don'?t\s+forget(?:\s+that)?\s+(.+)",
    r"^keep in mind(?:\s+that)?\s+(.+)",
]
# identity statements worth keeping even without "remember"
_IDENTITY = r"^(my name is\s+.+|i am\s+.+|i'?m\s+.+|i work\s+.+|i prefer\s+.+)"


def detect_remember(question: str) -> str | None:
    """Return the fact to store if the question is a remember-request, else None."""
    s = question.strip()
    for pat in _TRIGGERS:
        m = re.match(pat, s, re.I)
        if m:
            return m.group(1).strip().rstrip(".").strip()
    m = re.match(_IDENTITY, s, re.I)
    if m:
        return m.group(1).strip().rstrip(".").strip()
    return None


@transient_retry()
def add_memory(user_id: str, content: str) -> str | None:
    content = content.strip()[:MAX_LEN]
    if not content:
        return None
    sb = service_client()
    existing = (
        sb.table("memories").select("id, content, created_at").eq("user_id", user_id).execute().data
        or []
    )
    # dedup (case-insensitive)
    if any(e["content"].strip().lower() == content.lower() for e in existing):
        return content
    # cap: drop the oldest when full
    if len(existing) >= MAX_MEMORIES:
        oldest = min(existing, key=lambda e: e["created_at"])
        sb.table("memories").delete().eq("id", oldest["id"]).execute()
    sb.table("memories").insert({"user_id": user_id, "content": content}).execute()
    return content


@transient_retry()
def list_memories(user_id: str) -> list[dict]:
    sb = service_client()
    return (
        sb.table("memories")
        .select("id, content, created_at")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(MAX_MEMORIES)
        .execute()
        .data
        or []
    )


@transient_retry()
def delete_memory(user_id: str, mem_id: str) -> None:
    service_client().table("memories").delete().eq("id", mem_id).eq("user_id", user_id).execute()


def memory_block(user_id: str) -> str:
    """Compact bullet list of saved facts for prompt injection. '' if none."""
    mems = list_memories(user_id)
    if not mems:
        return ""
    lines = "\n".join(f"- {m['content']}" for m in mems)
    return (
        "Known facts about this user. When the question is about the user, answer "
        "directly from these facts and do not mention the documents or any "
        f"'not found' disclaimer:\n{lines}"
    )
