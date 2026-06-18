"""Password strength policy, shared by signup and password change/reset.

Kept deliberately simple and offline (length + character classes). A breached-
password check (HIBP k-anonymity) can be layered on later behind a flag.
"""
import re

MIN_LENGTH = 8


def validate_password(password: str) -> str | None:
    """Return an error message if the password is too weak, else None."""
    pw = password or ""
    if len(pw) < MIN_LENGTH:
        return f"Password must be at least {MIN_LENGTH} characters"
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        return "Password must include at least one letter and one number"
    return None
