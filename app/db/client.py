"""Supabase clients.

- anon client: auth (signup/login, JWT verification)
- service client: trusted backend DB + storage ops, scoped by user_id in code
"""
import time
from functools import lru_cache, wraps

import httpx
from supabase import create_client, Client

from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY


@lru_cache
def anon_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def fresh_anon_client() -> Client:
    """Return an auth client with no shared in-memory session state."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


@lru_cache
def service_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def transient_retry(attempts: int = 3, base_delay: float = 0.4):
    """Retry on transient network errors (e.g. httpx ReadError / Errno 35).

    Supabase calls occasionally hit flaky sockets; one retry usually succeeds.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last = None
            for i in range(attempts):
                try:
                    return fn(*args, **kwargs)
                except httpx.TransportError as e:  # ReadError, ConnectError, etc.
                    last = e
                    time.sleep(base_delay * (i + 1))
            raise last
        return wrapper
    return decorator
