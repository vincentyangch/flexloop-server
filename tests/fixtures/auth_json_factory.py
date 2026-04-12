"""Test helper: materialize a valid-by-default ~/.codex/auth.json on disk.

Used by CodexAuthReader tests, OpenAICodexAdapter tests, and the admin
Config / Health / Codex-status endpoint integration tests.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_DEFAULT_ACCESS_TOKEN = "test-access-token-abc123"
_DEFAULT_ID_TOKEN_EMAIL = "operator@example.com"
_DEFAULT_REFRESH_TOKEN = "test-refresh-token-xyz789"
_DEFAULT_OPENCLAW_ACCOUNT_ID = "operator@example.com"


def _make_id_token(email: str | None) -> str:
    """Build an unsigned JWT with the given email claim.

    Returns a 3-part string of the form `header.payload.sig` where
    `sig` is a placeholder string. The reader never verifies signatures,
    so the placeholder is fine for unit tests.
    """
    header = {"alg": "none", "typ": "JWT"}
    payload: dict[str, Any] = {"sub": "test-subject"}
    if email is not None:
        payload["email"] = email

    def _b64(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    return f"{_b64(header)}.{_b64(payload)}.signature-placeholder"


def make_auth_json(
    path: Path,
    *,
    auth_mode: str | None = "chatgpt",
    access_token: str | None = _DEFAULT_ACCESS_TOKEN,
    id_token_email: str | None = _DEFAULT_ID_TOKEN_EMAIL,
    refresh_token: str | None = _DEFAULT_REFRESH_TOKEN,
    last_refresh: datetime | None = None,
    omit_tokens: bool = False,
    omit_auth_mode: bool = False,
    omit_access_token: bool = False,
    omit_last_refresh: bool = False,
    raw_override: str | None = None,
) -> Path:
    """Write a ~/.codex/auth.json-shaped file to ``path``.

    Defaults produce a fresh, valid ChatGPT-OAuth file. Overrides let
    individual tests produce each failure variant without duplicating
    the boilerplate.

    Args:
        path: Filesystem path to write (usually from a tmp_path fixture).
        auth_mode: Value for the top-level ``auth_mode`` field. Set to
            ``"api_key"`` to produce a CodexAuthWrongMode fixture.
        access_token: Value for ``tokens.access_token``.
        id_token_email: Email claim to embed in the ``tokens.id_token``
            JWT. Pass ``None`` to omit the email claim (tests the
            graceful degradation path). Pass a string to set it.
        refresh_token: Value for ``tokens.refresh_token``.
        last_refresh: ISO timestamp for ``last_refresh``. Defaults to
            "now" (UTC). Pass a value N days in the past to produce
            a stale/aging fixture.
        omit_tokens: If True, omit the entire ``tokens`` object.
            Produces a CodexAuthMalformed fixture.
        omit_auth_mode: If True, omit the top-level ``auth_mode``.
            Produces a CodexAuthMalformed fixture.
        omit_access_token: If True, write a ``tokens`` object that
            lacks ``access_token``. Produces a CodexAuthMalformed fixture.
        omit_last_refresh: If True, omit the top-level ``last_refresh``.
            Reader should still succeed but snapshot.days_since_refresh
            will be None.
        raw_override: If set, writes this literal string to the file
            instead of a JSON-serialized dict. Used for the malformed
            JSON test fixture.

    Returns:
        The same ``path`` that was written (for convenience).
    """
    if raw_override is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw_override)
        return path

    if last_refresh is None:
        last_refresh = datetime.now(timezone.utc)

    data: dict[str, Any] = {}
    if not omit_auth_mode:
        data["auth_mode"] = auth_mode
    if not omit_last_refresh:
        data["last_refresh"] = last_refresh.isoformat()
    if not omit_tokens:
        tokens: dict[str, Any] = {
            "id_token": _make_id_token(id_token_email),
            "refresh_token": refresh_token,
        }
        if not omit_access_token:
            tokens["access_token"] = access_token
        data["tokens"] = tokens

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def make_openclaw_auth_profiles(
    path: Path,
    *,
    provider: str = "openai-codex",
    profile_type: str = "oauth",
    access_token: str | None = _DEFAULT_ACCESS_TOKEN,
    refresh_token: str | None = _DEFAULT_REFRESH_TOKEN,
    expires_at: int | None = None,
    account_id: str | None = _DEFAULT_OPENCLAW_ACCOUNT_ID,
    omit_access_token: bool = False,
    omit_expires_at: bool = False,
    extra_profiles: dict[str, dict[str, Any]] | None = None,
    raw_override: str | None = None,
) -> Path:
    """Write an OpenClaw auth-profiles.json-shaped file to ``path``.

    Defaults produce a valid file with one ``openai-codex`` profile
    whose token expires 7 days from now.
    """
    if raw_override is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw_override)
        return path

    if expires_at is None and not omit_expires_at:
        from datetime import timedelta

        expires_at = int(
            (datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000
        )

    profile: dict[str, Any] = {
        "type": profile_type,
        "provider": provider,
        "refresh_token": refresh_token,
        "accountId": account_id,
    }
    if not omit_access_token:
        profile["access_token"] = access_token
    if not omit_expires_at and expires_at is not None:
        profile["expires_at"] = expires_at

    profiles: dict[str, Any] = {f"{provider}:default": profile}
    if extra_profiles:
        profiles.update(extra_profiles)

    data = {"version": 1, "profiles": profiles}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path
