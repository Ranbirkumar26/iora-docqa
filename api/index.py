"""Vercel Python entrypoint.

Vercel looks for an ASGI/WSGI app object in api/*.py. Reuse the existing
FastAPI app so the backend implementation stays in one place.
"""
from app.api.main import app
