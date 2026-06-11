"""LLM provider switch. Pick via LLM_PROVIDER env (gemini | claude)."""
from app.config import LLM_PROVIDER

if LLM_PROVIDER == "claude":
    from app.llm.claude import complete
else:
    from app.llm.gemini import complete

__all__ = ["complete"]
