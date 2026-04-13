"""Read-only consumer of ~/.codex/auth.json.

This module never writes to auth.json, never calls the OpenAI token
refresh endpoint, and never interacts with the PKCE flow. It simply
reads whatever OpenClaw / the Codex CLI has last written and exposes
the access token plus a structured snapshot for UI display and health
checks.
"""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_READ_RETRY_ATTEMPTS = 3
_READ_RETRY_SLEEP_SECONDS = 0.005

_YELLOW_THRESHOLD_DAYS = 5.0
_RED_THRESHOLD_DAYS = 9.0
_EXPIRY_YELLOW_THRESHOLD_DAYS = 5.0
_EXPIRY_RED_THRESHOLD_DAYS = 2.0


class CodexAuthError(Exception):
    """Base class for all reader errors."""


class CodexAuthMissing(CodexAuthError):
    """File does not exist or is unreadable."""


class CodexAuthMalformed(CodexAuthError):
    """File exists but its contents are unparseable or missing required fields."""


class CodexAuthWrongMode(CodexAuthError):
    """File is in a mode other than ChatGPT OAuth mode."""

    def __init__(self, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.data: dict[str, Any] = data or {}


@dataclass(frozen=True)
class CodexAuthSnapshot:
    """A point-in-time view of ~/.codex/auth.json for admin UIs."""

    status: str
    file_exists: bool
    file_path: str

    auth_mode: str | None = None
    last_refresh: datetime | None = None
    days_since_refresh: float | None = None
    days_until_expiry: float | None = None
    account_email: str | None = None

    error: str | None = None
    error_code: str | None = None


class CodexAuthReader:
    """Read ``~/.codex/auth.json`` and expose its access token + metadata."""

    def __init__(self, path: str) -> None:
        self._raw_path = path
        self._resolved_path = os.path.abspath(os.path.expanduser(path))

    def read_access_token(self) -> str:
        """Return the current access token."""
        _, access_token = self._load_and_validate()
        return access_token

    def read_credential(self) -> tuple[str, str | None]:
        """Return ``(access_token, account_id)``.

        ``account_id`` comes from the auth file itself — OpenClaw profiles
        store it as ``accountId``, Codex CLI files store it as
        ``tokens.account_id``.  Returns *None* when the file does not
        contain an account ID (the caller can still try JWT extraction).
        """
        data, access_token = self._load_and_validate()
        auth_mode = data.get("auth_mode")

        if auth_mode == "openclaw-oauth":
            aid = data.get("account_id")
            return access_token, aid if isinstance(aid, str) else None

        # Codex CLI: tokens.account_id
        tokens = data.get("tokens")
        if isinstance(tokens, dict):
            aid = tokens.get("account_id")
            if isinstance(aid, str):
                return access_token, aid

        return access_token, None

    def snapshot(self) -> CodexAuthSnapshot:
        """Return a structured snapshot of the current file state.

        Never raises. Every failure mode from ``_load_and_validate()`` is
        encoded into ``status`` / ``error_code`` / ``error``.
        """
        try:
            data, _ = self._load_and_validate()
        except CodexAuthMissing as e:
            error_code = "permission" if "permission" in str(e).lower() else "missing"
            return CodexAuthSnapshot(
                status="unconfigured",
                file_exists=os.path.exists(self._resolved_path),
                file_path=self._resolved_path,
                error_code=error_code,
                error=str(e),
            )
        except CodexAuthMalformed as e:
            return CodexAuthSnapshot(
                status="down",
                file_exists=os.path.exists(self._resolved_path),
                file_path=self._resolved_path,
                error_code="malformed",
                error=str(e),
            )
        except CodexAuthWrongMode as e:
            data = e.data
            # OpenClaw profiles expose accountId/email and expires_at/expires,
            # unlike Codex CLI auth.json, so those keys let snapshot() preserve
            # the OpenClaw-specific metadata on errors.
            has_openclaw_keys = any(
                k in data for k in ("accountId", "email", "expires_at", "expires")
            )
            if has_openclaw_keys:
                expiry_dt = self._parse_expires_at(
                    data.get("expires_at") or data.get("expires")
                )
                return CodexAuthSnapshot(
                    status="down",
                    file_exists=True,
                    file_path=self._resolved_path,
                    auth_mode=data.get("type"),
                    last_refresh=expiry_dt,
                    days_until_expiry=self._compute_days_until(expiry_dt),
                    account_email=(
                        data.get("accountId") or data.get("email")
                    ),
                    error_code="wrong_mode",
                    error=str(e),
                )
            last_refresh = self._parse_last_refresh(data.get("last_refresh"))
            tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
            email = self._decode_id_token_email(tokens.get("id_token"))
            return CodexAuthSnapshot(
                status="down",
                file_exists=True,
                file_path=self._resolved_path,
                auth_mode=data.get("auth_mode"),
                last_refresh=last_refresh,
                days_since_refresh=self._compute_days_since(last_refresh),
                account_email=email,
                error_code="wrong_mode",
                error=str(e),
            )

        auth_mode = data["auth_mode"]
        if auth_mode == "openclaw-oauth":
            expires_at_ms = data.get("expires_at")
            expiry_dt = self._parse_expires_at(expires_at_ms)
            days_until = self._compute_days_until(expiry_dt)
            account_email = data.get("account_id")
            status, error_code, error = self._classify_expiry_freshness(days_until)

            return CodexAuthSnapshot(
                status=status,
                file_exists=True,
                file_path=self._resolved_path,
                auth_mode=auth_mode,
                last_refresh=expiry_dt,
                days_until_expiry=days_until,
                account_email=account_email,
                error_code=error_code,
                error=error,
            )

        last_refresh = self._parse_last_refresh(data.get("last_refresh"))
        days_since_refresh = self._compute_days_since(last_refresh)
        tokens = data.get("tokens", {})
        email = self._decode_id_token_email(tokens.get("id_token"))
        status, error_code, error = self._classify_freshness(days_since_refresh)

        return CodexAuthSnapshot(
            status=status,
            file_exists=True,
            file_path=self._resolved_path,
            auth_mode=auth_mode,
            last_refresh=last_refresh,
            days_since_refresh=days_since_refresh,
            account_email=email,
            error_code=error_code,
            error=error,
        )

    def _load_and_validate(self) -> tuple[dict[str, Any], str]:
        """Read, parse, and validate the file. Return ``(data, access_token)``."""
        data = self._load_file_with_retry()

        if "version" in data and "profiles" in data:
            return self._validate_openclaw(data)
        if "auth_mode" in data:
            return self._validate_codex_cli(data)

        raise CodexAuthMalformed(
            f"unrecognized auth file format in {self._resolved_path!r}: "
            f"expected 'version'+'profiles' (OpenClaw) or 'auth_mode' (Codex CLI)"
        )

    def _validate_codex_cli(self, data: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Validate a Codex CLI auth.json file."""
        if data["auth_mode"] != "chatgpt":
            raise CodexAuthWrongMode(
                f"auth_mode is {data['auth_mode']!r}, expected 'chatgpt'",
                data=data,
            )
        tokens = data.get("tokens")
        if not isinstance(tokens, dict):
            raise CodexAuthMalformed(
                f"tokens object missing from {self._resolved_path!r}"
            )
        access_token = tokens.get("access_token")
        if not access_token:
            raise CodexAuthMalformed(
                f"tokens.access_token missing from {self._resolved_path!r}"
            )
        return data, access_token

    def _validate_openclaw(self, data: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """Validate an OpenClaw auth-profiles.json file.

        Finds the first profile with ``provider == "openai-codex"``,
        checks its type, and extracts the access token. Returns a
        normalized dict with ``auth_mode = "openclaw-oauth"`` plus the
        original profile fields.
        """
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            raise CodexAuthMalformed(
                f"profiles object missing from {self._resolved_path!r}"
            )

        codex_profile: dict[str, Any] | None = None
        for _key, profile in profiles.items():
            if isinstance(profile, dict) and profile.get("provider") == "openai-codex":
                codex_profile = profile
                break

        if codex_profile is None:
            raise CodexAuthWrongMode(
                f"no openai-codex profile found in {self._resolved_path!r}",
                data=data,
            )

        if codex_profile.get("type") != "oauth":
            raise CodexAuthWrongMode(
                f"openai-codex profile type is {codex_profile.get('type')!r}, "
                f"expected 'oauth'",
                data=codex_profile,
            )

        # Field names differ between OpenClaw versions:
        #   current:  access, refresh, expires, email
        #   legacy:   access_token, refresh_token, expires_at, accountId
        access_token = (
            codex_profile.get("access_token") or codex_profile.get("access")
        )
        if not access_token:
            raise CodexAuthMalformed(
                f"access_token/access missing from openai-codex profile in "
                f"{self._resolved_path!r}"
            )

        normalized: dict[str, Any] = {
            "auth_mode": "openclaw-oauth",
            "account_id": (
                codex_profile.get("accountId") or codex_profile.get("email")
            ),
            "expires_at": (
                codex_profile.get("expires_at") or codex_profile.get("expires")
            ),
        }
        return normalized, access_token

    def _load_file_with_retry(self) -> dict[str, Any]:
        """Read + json.load the file with retry on JSONDecodeError."""
        if not os.path.exists(self._resolved_path):
            raise CodexAuthMissing(f"auth.json not found at {self._resolved_path!r}")

        last_parse_error: Exception | None = None
        for attempt in range(_READ_RETRY_ATTEMPTS):
            try:
                raw = self._read_text()
            except PermissionError as e:
                raise CodexAuthMissing(
                    f"permission denied reading {self._resolved_path!r}: {e}"
                ) from e
            except OSError as e:
                raise CodexAuthMissing(
                    f"could not read {self._resolved_path!r}: {e}"
                ) from e

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                last_parse_error = e
                if attempt < _READ_RETRY_ATTEMPTS - 1:
                    time.sleep(_READ_RETRY_SLEEP_SECONDS)
                    continue
                break

            if not isinstance(parsed, dict):
                raise CodexAuthMalformed(
                    f"{self._resolved_path!r} parsed but is not a JSON "
                    f"object (got {type(parsed).__name__}); expected a dict"
                )
            return parsed

        raise CodexAuthMalformed(
            f"could not parse {self._resolved_path!r} after "
            f"{_READ_RETRY_ATTEMPTS} attempts: {last_parse_error}"
        )

    def _read_text(self) -> str:
        return Path(self._resolved_path).read_text()

    @staticmethod
    def _parse_last_refresh(value: Any) -> datetime | None:
        if not value or not isinstance(value, str):
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _parse_expires_at(value: Any) -> datetime | None:
        """Convert millisecond epoch timestamp to datetime."""
        if value is None or not isinstance(value, (int, float)):
            return None
        if value <= 0:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)

    @staticmethod
    def _compute_days_since(last_refresh: datetime | None) -> float | None:
        if last_refresh is None:
            return None
        now = datetime.now(timezone.utc)
        delta = now - last_refresh
        return delta.total_seconds() / 86400.0

    @staticmethod
    def _compute_days_until(expiry: datetime | None) -> float | None:
        if expiry is None:
            return None
        now = datetime.now(timezone.utc)
        delta = expiry - now
        return delta.total_seconds() / 86400.0

    @staticmethod
    def _decode_id_token_email(id_token: Any) -> str | None:
        """Extract the ``email`` claim from an unsigned JWT. Never raises."""
        if not id_token or not isinstance(id_token, str):
            return None
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        try:
            payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
            payload = json.loads(payload_bytes)
        except (ValueError, json.JSONDecodeError):
            return None
        email = payload.get("email")
        return email if isinstance(email, str) else None

    @staticmethod
    def _classify_expiry_freshness(
        days_until_expiry: float | None,
    ) -> tuple[str, str | None, str | None]:
        if days_until_expiry is None:
            return "healthy", None, None
        if days_until_expiry <= 0:
            return (
                "down",
                "expired",
                f"session expired {abs(days_until_expiry):.1f} days ago",
            )
        if days_until_expiry < _EXPIRY_RED_THRESHOLD_DAYS:
            return (
                "degraded_red",
                None,
                f"session expires in {days_until_expiry:.1f} days",
            )
        if days_until_expiry < _EXPIRY_YELLOW_THRESHOLD_DAYS:
            return (
                "degraded_yellow",
                None,
                f"session expires in {days_until_expiry:.1f} days",
            )
        return "healthy", None, None

    @staticmethod
    def _classify_freshness(
        days_since_refresh: float | None,
    ) -> tuple[str, str | None, str | None]:
        if days_since_refresh is None:
            return "healthy", None, None
        if days_since_refresh < _YELLOW_THRESHOLD_DAYS:
            return "healthy", None, None
        if days_since_refresh < _RED_THRESHOLD_DAYS:
            return (
                "degraded_yellow",
                None,
                f"session aging - {days_since_refresh:.1f} days since refresh",
            )
        return (
            "degraded_red",
            "stale",
            f"session stale - {days_since_refresh:.1f} days since refresh",
        )
