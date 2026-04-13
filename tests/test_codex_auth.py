"""Unit tests for flexloop.ai.codex_auth.CodexAuthReader.

These are pure-filesystem tests using tmp_path fixtures. No network,
no real auth.json, no mocking of json/os/time.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from flexloop.ai.codex_auth import (
    CodexAuthMalformed,
    CodexAuthMissing,
    CodexAuthReader,
    CodexAuthSnapshot,
    CodexAuthWrongMode,
)
from tests.fixtures.auth_json_factory import (
    make_auth_json,
    make_openclaw_auth_profiles,
)


# ---- read_access_token() raise-path tests ----


def test_reader_happy_path_returns_token(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file)
    reader = CodexAuthReader(str(auth_file))
    token = reader.read_access_token()
    assert token == "test-access-token-abc123"


def test_reader_missing_file_raises(tmp_path):
    reader = CodexAuthReader(str(tmp_path / "nonexistent.json"))
    with pytest.raises(CodexAuthMissing, match="not found"):
        reader.read_access_token()


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root can read any file regardless of chmod"
)
def test_reader_permission_denied_raises(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file)
    auth_file.chmod(0o000)
    try:
        reader = CodexAuthReader(str(auth_file))
        with pytest.raises(CodexAuthMissing, match="[Pp]ermission"):
            reader.read_access_token()
    finally:
        auth_file.chmod(0o600)


def test_reader_malformed_json_raises_after_retries(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, raw_override="not valid json {{{")
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthMalformed, match="parse"):
        reader.read_access_token()


def test_reader_torn_read_recovers_on_retry(tmp_path):
    """Simulate a torn read.

    First read returns partial content, second read returns valid content.
    The retry loop should succeed.
    """
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file)
    valid_content = auth_file.read_text()

    call_count = {"n": 0}
    real_read_text = type(auth_file).read_text

    def flaky_read_text(self, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "{incomplete"
        return real_read_text(self, *args, **kwargs)

    with patch.object(type(auth_file), "read_text", flaky_read_text):
        reader = CodexAuthReader(str(auth_file))
        token = reader.read_access_token()

    assert token == "test-access-token-abc123"
    assert valid_content
    assert call_count["n"] == 2, "reader should retry exactly once in this scenario"


def test_reader_retry_policy_is_3_attempts_with_5ms_sleep(tmp_path):
    """Pin the exact retry policy: 3 attempts total, 5ms sleep between."""
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, raw_override="{broken")

    sleep_calls: list[float] = []
    with patch("flexloop.ai.codex_auth.time.sleep", side_effect=sleep_calls.append):
        reader = CodexAuthReader(str(auth_file))
        with pytest.raises(CodexAuthMalformed):
            reader.read_access_token()

    assert len(sleep_calls) == 2, f"expected 2 sleeps, got {len(sleep_calls)}"
    assert all(s == pytest.approx(0.005, abs=1e-6) for s in sleep_calls), (
        f"expected each sleep to be 0.005s, got {sleep_calls}"
    )


def test_reader_missing_auth_mode_raises(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, omit_auth_mode=True)
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthMalformed, match="auth_mode"):
        reader.read_access_token()


def test_reader_api_key_mode_raises(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, auth_mode="api_key")
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthWrongMode, match="chatgpt"):
        reader.read_access_token()


def test_reader_missing_tokens_raises(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, omit_tokens=True)
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthMalformed, match="tokens"):
        reader.read_access_token()


def test_reader_missing_access_token_raises(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, omit_access_token=True)
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthMalformed, match="access_token"):
        reader.read_access_token()


def test_reader_expanduser_on_tilde_path(tmp_path, monkeypatch):
    fake_home = tmp_path / "fake-home"
    fake_home.mkdir()
    (fake_home / ".codex").mkdir()
    make_auth_json(fake_home / ".codex" / "auth.json")

    monkeypatch.setenv("HOME", str(fake_home))
    reader = CodexAuthReader("~/.codex/auth.json")
    token = reader.read_access_token()
    assert token == "test-access-token-abc123"


# ---- snapshot() no-raise-path tests ----


def test_snapshot_happy_path_healthy(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file)
    reader = CodexAuthReader(str(auth_file))

    snap = reader.snapshot()
    assert snap.status == "healthy"
    assert snap.file_exists is True
    assert snap.auth_mode == "chatgpt"
    assert snap.days_since_refresh is not None
    assert snap.days_since_refresh < 1.0
    assert snap.account_email == "operator@example.com"
    assert snap.error is None
    assert snap.error_code is None


def test_snapshot_missing_file_unconfigured(tmp_path):
    reader = CodexAuthReader(str(tmp_path / "nonexistent.json"))
    snap = reader.snapshot()
    assert snap.status == "unconfigured"
    assert snap.file_exists is False
    assert snap.error_code == "missing"
    assert snap.error is not None


def test_snapshot_malformed_json_down(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, raw_override="not valid json")
    reader = CodexAuthReader(str(auth_file))
    snap = reader.snapshot()
    assert snap.status == "down"
    assert snap.error_code == "malformed"
    assert snap.file_exists is True


def test_snapshot_missing_auth_mode_down(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, omit_auth_mode=True)
    reader = CodexAuthReader(str(auth_file))
    snap = reader.snapshot()
    assert snap.status == "down"
    assert snap.error_code == "malformed"


def test_snapshot_missing_tokens_down(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, omit_tokens=True)
    reader = CodexAuthReader(str(auth_file))
    snap = reader.snapshot()
    assert snap.status == "down"
    assert snap.error_code == "malformed"


def test_snapshot_missing_access_token_down(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, omit_access_token=True)
    reader = CodexAuthReader(str(auth_file))
    snap = reader.snapshot()
    assert snap.status == "down"
    assert snap.error_code == "malformed"


@pytest.mark.parametrize(
    "non_object_json",
    ["null", "[]", "42", '"a string"', "true", "3.14"],
)
def test_snapshot_non_object_json_down(tmp_path, non_object_json):
    """Non-dict JSON must not crash snapshot()."""
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, raw_override=non_object_json)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "down"
    assert snap.error_code == "malformed"
    assert "not a JSON object" in (snap.error or "")


def test_snapshot_wrong_mode_preserves_all_metadata_for_ui(tmp_path):
    """Wrong mode should still carry metadata the UI can display."""
    fixed_last_refresh = datetime.now(timezone.utc) - timedelta(days=3, hours=12)
    auth_file = tmp_path / "auth.json"
    make_auth_json(
        auth_file,
        auth_mode="api_key",
        id_token_email="wronguser@example.com",
        last_refresh=fixed_last_refresh,
    )
    reader = CodexAuthReader(str(auth_file))
    snap = reader.snapshot()
    assert snap.status == "down"
    assert snap.error_code == "wrong_mode"
    assert snap.auth_mode == "api_key", (
        "wrong_mode snapshots must carry the actual auth_mode through "
        "the exception's data attribute for UI display"
    )
    assert snap.last_refresh == fixed_last_refresh, (
        "wrong_mode snapshots must carry last_refresh because the file "
        "parsed successfully, only the semantic check failed"
    )
    assert snap.days_since_refresh is not None
    assert 3.4 < snap.days_since_refresh < 3.6, (
        f"expected ~3.5 days, got {snap.days_since_refresh}"
    )
    assert snap.account_email == "wronguser@example.com", (
        "wrong_mode snapshots must decode id_token email from the "
        "parsed data, not drop it"
    )


def test_snapshot_days_since_refresh_fresh(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, last_refresh=datetime.now(timezone.utc))
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "healthy"
    assert 0.0 <= snap.days_since_refresh < 0.01


def test_snapshot_days_since_refresh_exactly_5_days_yellow(tmp_path):
    """Boundary: 5 days exactly -> yellow."""
    auth_file = tmp_path / "auth.json"
    make_auth_json(
        auth_file,
        last_refresh=datetime.now(timezone.utc) - timedelta(days=5),
    )
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "degraded_yellow"
    assert 4.99 < snap.days_since_refresh < 5.01


def test_snapshot_days_since_refresh_exactly_9_days_red(tmp_path):
    """Boundary: 9 days exactly -> red."""
    auth_file = tmp_path / "auth.json"
    make_auth_json(
        auth_file,
        last_refresh=datetime.now(timezone.utc) - timedelta(days=9),
    )
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "degraded_red"
    assert snap.error_code == "stale"


def test_snapshot_days_since_refresh_7_days_yellow(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(
        auth_file,
        last_refresh=datetime.now(timezone.utc) - timedelta(days=7),
    )
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "degraded_yellow"


def test_snapshot_days_since_refresh_12_days_red(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(
        auth_file,
        last_refresh=datetime.now(timezone.utc) - timedelta(days=12),
    )
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "degraded_red"


def test_snapshot_missing_last_refresh_has_none(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, omit_last_refresh=True)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.days_since_refresh is None
    assert snap.status == "healthy"


def test_snapshot_tolerates_malformed_id_token(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file)
    data = json.loads(auth_file.read_text())
    data["tokens"]["id_token"] = "not-a-valid-jwt"
    auth_file.write_text(json.dumps(data))

    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "healthy"
    assert snap.account_email is None


def test_snapshot_id_token_email_missing_claim(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, id_token_email=None)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "healthy"
    assert snap.account_email is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"auth_mode": "api_key"},
        {"omit_tokens": True},
        {"omit_auth_mode": True},
        {"omit_access_token": True},
        {"raw_override": "{broken"},
        {"last_refresh": datetime.now(timezone.utc) - timedelta(days=20)},
    ],
)
def test_snapshot_never_raises_under_any_fixture(tmp_path, kwargs):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file, **kwargs)
    reader = CodexAuthReader(str(auth_file))
    snap = reader.snapshot()
    assert isinstance(snap, CodexAuthSnapshot)
    assert snap.file_path


# ---- OpenClaw auth-profiles.json format tests ----


def test_openclaw_happy_path_returns_token(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file)
    reader = CodexAuthReader(str(auth_file))
    token = reader.read_access_token()
    assert token == "test-access-token-abc123"


def test_openclaw_multiple_profiles_picks_codex(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(
        auth_file,
        extra_profiles={
            "anthropic:default": {
                "type": "api_key",
                "provider": "anthropic",
                "access_token": "sk-ant-wrong-token",
            },
        },
    )
    reader = CodexAuthReader(str(auth_file))
    token = reader.read_access_token()
    assert token == "test-access-token-abc123"


def test_openclaw_no_codex_profile_raises_wrong_mode(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, provider="anthropic")
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthWrongMode, match="no openai-codex profile"):
        reader.read_access_token()


def test_openclaw_wrong_type_raises_wrong_mode(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, profile_type="api_key")
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthWrongMode, match="expected 'oauth'"):
        reader.read_access_token()


def test_openclaw_missing_access_token_raises_malformed(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, omit_access_token=True)
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthMalformed, match="access_token missing"):
        reader.read_access_token()


def test_openclaw_unrecognized_format_raises_malformed(tmp_path):
    """File has neither OpenClaw nor Codex CLI markers."""
    auth_file = tmp_path / "auth.json"
    auth_file.write_text('{"foo": "bar"}')
    reader = CodexAuthReader(str(auth_file))
    with pytest.raises(CodexAuthMalformed, match="unrecognized auth file format"):
        reader.read_access_token()


def test_openclaw_snapshot_healthy(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    future = datetime.now(timezone.utc) + timedelta(days=10)
    expires_at = int(future.timestamp() * 1000)
    make_openclaw_auth_profiles(auth_file, expires_at=expires_at)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "healthy"
    assert snap.auth_mode == "openclaw-oauth"
    assert snap.account_email == "operator@example.com"
    assert snap.days_until_expiry is not None
    assert snap.days_until_expiry > 9.0


def test_openclaw_snapshot_degraded_yellow(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    future = datetime.now(timezone.utc) + timedelta(days=3)
    expires_at = int(future.timestamp() * 1000)
    make_openclaw_auth_profiles(auth_file, expires_at=expires_at)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "degraded_yellow"
    assert snap.days_until_expiry is not None
    assert 2.0 < snap.days_until_expiry < 5.0


def test_openclaw_snapshot_degraded_red(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    future = datetime.now(timezone.utc) + timedelta(hours=12)
    expires_at = int(future.timestamp() * 1000)
    make_openclaw_auth_profiles(auth_file, expires_at=expires_at)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "degraded_red"
    assert snap.days_until_expiry is not None
    assert snap.days_until_expiry < 2.0


def test_openclaw_snapshot_expired_is_down(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    past = datetime.now(timezone.utc) - timedelta(days=1)
    expires_at = int(past.timestamp() * 1000)
    make_openclaw_auth_profiles(auth_file, expires_at=expires_at)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "down"
    assert snap.error_code == "expired"


def test_openclaw_snapshot_epoch_zero_is_down(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, expires_at=0)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "down"


def test_openclaw_snapshot_missing_expires_at_is_healthy(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, omit_expires_at=True)
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "healthy"
    assert snap.days_until_expiry is None


def test_openclaw_snapshot_wrong_mode_preserves_metadata(tmp_path):
    """wrong-mode snapshot for OpenClaw data should still show accountId."""
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, profile_type="api_key")
    snap = CodexAuthReader(str(auth_file)).snapshot()
    assert snap.status == "down"
    assert snap.auth_mode == "api_key"
    assert snap.error_code == "wrong_mode"


def test_format_detection_prefers_openclaw_when_ambiguous(tmp_path):
    """A file with both version+profiles AND auth_mode should be treated as OpenClaw."""
    auth_file = tmp_path / "auth.json"
    data = {
        "version": 1,
        "profiles": {
            "openai-codex:default": {
                "type": "oauth",
                "provider": "openai-codex",
                "access_token": "oc-token",
            }
        },
        "auth_mode": "chatgpt",
    }
    auth_file.write_text(json.dumps(data))
    reader = CodexAuthReader(str(auth_file))
    token = reader.read_access_token()
    assert token == "oc-token"


# ---- read_credential() tests ----


def test_credential_openclaw_returns_account_id(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, account_id="acct_oc_42")
    token, account_id = CodexAuthReader(str(auth_file)).read_credential()
    assert token == "test-access-token-abc123"
    assert account_id == "acct_oc_42"


def test_credential_openclaw_none_when_account_id_missing(tmp_path):
    auth_file = tmp_path / "auth-profiles.json"
    make_openclaw_auth_profiles(auth_file, account_id=None)
    token, account_id = CodexAuthReader(str(auth_file)).read_credential()
    assert token == "test-access-token-abc123"
    assert account_id is None


def test_credential_codex_cli_returns_account_id(tmp_path):
    """Codex CLI stores account_id inside the tokens object."""
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file)
    data = json.loads(auth_file.read_text())
    data["tokens"]["account_id"] = "acct_cli_99"
    auth_file.write_text(json.dumps(data))

    token, account_id = CodexAuthReader(str(auth_file)).read_credential()
    assert token == "test-access-token-abc123"
    assert account_id == "acct_cli_99"


def test_credential_codex_cli_none_when_no_account_id(tmp_path):
    auth_file = tmp_path / "auth.json"
    make_auth_json(auth_file)
    token, account_id = CodexAuthReader(str(auth_file)).read_credential()
    assert token == "test-access-token-abc123"
    assert account_id is None
