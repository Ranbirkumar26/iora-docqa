"""TOTP multi-factor auth via gotrue.

gotrue MFA is session-bound (not a service-role op), so each call hydrates a
per-request client with the caller's tokens. Admin reset uses the gotrue admin
REST endpoint directly because the Python client's admin MFA methods are stubbed
(NotImplementedError) in this version.

NOTE: the end-to-end TOTP round-trip (real authenticator codes) must be verified
against a live Supabase project; unit tests here cover the wiring only.
"""
import httpx

from app.config import SUPABASE_SERVICE_KEY, SUPABASE_URL
from app.db.client import fresh_anon_client


def _session_client(access_token: str, refresh_token: str):
    client = fresh_anon_client()
    client.auth.set_session(access_token, refresh_token)
    return client


def enroll(access_token: str, refresh_token: str) -> dict:
    """Begin TOTP enrollment. Returns the QR/secret to show once."""
    res = _session_client(access_token, refresh_token).auth.mfa.enroll(
        {"factor_type": "totp"}
    )
    totp = getattr(res, "totp", None)
    return {
        "factor_id": getattr(res, "id", None),
        "qr_code": getattr(totp, "qr_code", None),
        "secret": getattr(totp, "secret", None),
        "uri": getattr(totp, "uri", None),
    }


def verify(access_token: str, refresh_token: str, factor_id: str, code: str) -> dict:
    """Verify a TOTP code (completes enrollment, or upgrades a login to AAL2).

    Returns the upgraded session tokens so the caller can replace its session.
    """
    res = _session_client(access_token, refresh_token).auth.mfa.challenge_and_verify(
        {"factor_id": factor_id, "code": code}
    )
    return {
        "access_token": getattr(res, "access_token", None),
        "refresh_token": getattr(res, "refresh_token", None),
        "expires_at": getattr(res, "expires_at", None),
    }


def unenroll(access_token: str, refresh_token: str, factor_id: str) -> None:
    _session_client(access_token, refresh_token).auth.mfa.unenroll(
        {"factor_id": factor_id}
    )


def _factor_dicts(res) -> list[dict]:
    factors = getattr(res, "all", None) or getattr(res, "totp", None) or []
    out = []
    for f in factors:
        out.append(
            {
                "id": getattr(f, "id", None),
                "status": getattr(f, "status", None),
                "friendly_name": getattr(f, "friendly_name", None),
                "factor_type": getattr(f, "factor_type", None),
            }
        )
    return out


def list_factors(access_token: str, refresh_token: str) -> list[dict]:
    res = _session_client(access_token, refresh_token).auth.mfa.list_factors()
    return _factor_dicts(res)


def login_mfa_state(client) -> dict | None:
    """Given a client holding a fresh post-login session, return {factor_id} when
    a second factor is required (AAL1 now, AAL2 expected), else None."""
    try:
        aal = client.auth.mfa.get_authenticator_assurance_level()
        if (
            getattr(aal, "next_level", None) == "aal2"
            and getattr(aal, "current_level", None) != "aal2"
        ):
            factors = client.auth.mfa.list_factors()
            verified = [
                f
                for f in _factor_dicts(factors)
                if f.get("status") == "verified"
            ]
            if verified:
                return {"factor_id": verified[0]["id"]}
    except Exception:
        return None
    return None


def admin_reset(user_id: str) -> int:
    """Delete all of a user's MFA factors (admin recovery for a locked-out user).

    Uses the gotrue admin REST API directly (client admin-MFA methods are stubbed).
    Returns the number of factors removed.
    """
    base = f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{user_id}/factors"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    removed = 0
    with httpx.Client(timeout=10) as c:
        resp = c.get(base, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        factors = data.get("factors", []) if isinstance(data, dict) else data
        for f in factors or []:
            fid = f.get("id") if isinstance(f, dict) else None
            if not fid:
                continue
            c.delete(f"{base}/{fid}", headers=headers)
            removed += 1
    return removed
