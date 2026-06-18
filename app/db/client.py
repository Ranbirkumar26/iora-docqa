"""Supabase clients.

- anon client: auth (signup/login, JWT verification)
- service client: trusted backend DB + storage ops, scoped by user_id in code
"""
import time
from functools import lru_cache, wraps

import httpx
from supabase import create_client, Client

from app.config import (
    RLS_SCOPED_READS,
    SUPABASE_ANON_KEY,
    SUPABASE_SERVICE_KEY,
    SUPABASE_URL,
)


@lru_cache
def anon_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def fresh_anon_client() -> Client:
    """Return an auth client with no shared in-memory session state."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


@lru_cache
def service_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


@lru_cache(maxsize=64)
def user_client(access_token: str) -> Client:
    """Client whose PostgREST requests carry the user's JWT, so Postgres RLS
    applies (queries run as the authenticated user). Cached per token (bounded).
    """
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    client.postgrest.auth(access_token)
    return client


def read_client(access_token: str | None = None) -> Client:
    """User-scoped client (RLS-enforced) when RLS_SCOPED_READS is on and a token
    is given, else the service client. For SELECT/RPC reads only — writes/admin
    keep service_client. Off by default until verified live against the policies.
    """
    if RLS_SCOPED_READS and access_token:
        return user_client(access_token)
    return service_client()


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
