"""Supabase clients.

- anon client: auth (signup/login, JWT verification)
- service client: trusted backend DB + storage ops, scoped by user_id in code
"""
from functools import lru_cache

from supabase import create_client, Client

from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY


@lru_cache
def anon_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


@lru_cache
def service_client() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
