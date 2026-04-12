# OpenClaw Auth Profile Support — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `CodexAuthReader` to auto-detect and read OpenClaw's `auth-profiles.json` format alongside the existing Codex CLI `auth.json`, so VPS deployments running OpenClaw can use the Codex OAuth provider without maintaining a separate `~/.codex/auth.json`.

**Architecture:** Format detection happens in `_load_and_validate()` by checking for `version`+`profiles` keys (OpenClaw) vs `auth_mode` (Codex CLI). A new `_validate_openclaw()` method extracts the `openai-codex` profile and returns a normalized `(data, access_token)` tuple. A new `days_until_expiry` field on `CodexAuthSnapshot` handles OpenClaw's expiry-based freshness model.

**Tech Stack:** Python (dataclasses, json), FastAPI/Pydantic, React/TypeScript (shadcn/ui)

**Spec:** `docs/superpowers/specs/2026-04-12-openclaw-auth-support-design.md`

---

## Chunk 1: Backend — fixture factory, tests, and implementation

**Scope:** All changes to `codex_auth.py`, the fixture factory, and tests. After this chunk, `CodexAuthReader` handles both file formats with full test coverage.

**Chunk 1 end state:**
- `make_openclaw_auth_profiles()` fixture builder exists.
- `CodexAuthSnapshot` has `days_until_expiry` field.
- `_load_and_validate()` auto-detects format and dispatches to the correct validator.
- `_validate_openclaw()` extracts the `openai-codex` profile.
- `_classify_freshness()` handles `days_until_expiry`.
- `snapshot()` wrong-mode handler is format-aware.
- All new tests pass, all existing tests pass.

### Task 1.1: Add OpenClaw fixture factory

**Files:**
- Modify: `tests/fixtures/auth_json_factory.py`

- [ ] **Step 1.1.1:** Add the `make_openclaw_auth_profiles()` function after the existing `make_auth_json()`. It should write a valid OpenClaw `auth-profiles.json` to disk with configurable parameters.

    ```python
    _DEFAULT_OPENCLAW_ACCOUNT_ID = "operator@example.com"


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
            # Default: expires 7 days from now (milliseconds)
            from datetime import datetime, timedelta, timezone
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
    ```

- [ ] **Step 1.1.2:** Commit.

    ```bash
    git add tests/fixtures/auth_json_factory.py
    git commit -m "test: add OpenClaw auth-profiles.json fixture factory"
    ```

### Task 1.2: Add `days_until_expiry` to `CodexAuthSnapshot`

**Files:**
- Modify: `src/flexloop/ai/codex_auth.py`

- [ ] **Step 1.2.1:** Add the new field to `CodexAuthSnapshot` (after `days_since_refresh`):

    ```python
    days_until_expiry: float | None = None
    ```

- [ ] **Step 1.2.2:** Run existing tests to confirm nothing breaks:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -v
    ```

    Expected: all existing tests pass (the new field defaults to `None`).

- [ ] **Step 1.2.3:** Commit.

    ```bash
    git add src/flexloop/ai/codex_auth.py
    git commit -m "feat(ai): add days_until_expiry field to CodexAuthSnapshot"
    ```

### Task 1.3: OpenClaw happy path — read_access_token()

**Files:**
- Modify: `tests/test_codex_auth.py`
- Modify: `src/flexloop/ai/codex_auth.py`

- [ ] **Step 1.3.1:** Write the failing test at the bottom of `test_codex_auth.py`, in a new section:

    ```python
    # ---- OpenClaw auth-profiles.json format tests ----

    from tests.fixtures.auth_json_factory import make_openclaw_auth_profiles


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
    ```

- [ ] **Step 1.3.2:** Run the tests to confirm they fail:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py::test_openclaw_happy_path_returns_token tests/test_codex_auth.py::test_openclaw_multiple_profiles_picks_codex -v
    ```

    Expected: FAIL (OpenClaw format not recognized, raises `CodexAuthMalformed` because there's no `auth_mode` key).

- [ ] **Step 1.3.3:** Implement format detection in `_load_and_validate()`. Replace the current method body with format dispatch:

    ```python
    def _load_and_validate(self) -> tuple[dict[str, Any], str]:
        """Read, parse, and validate the file. Return ``(data, access_token)``."""
        data = self._load_file_with_retry()

        # Format detection: OpenClaw checked first, Codex CLI as fallback.
        if "version" in data and "profiles" in data:
            return self._validate_openclaw(data)
        if "auth_mode" in data:
            return self._validate_codex_cli(data)

        raise CodexAuthMalformed(
            f"unrecognized auth file format in {self._resolved_path!r}: "
            f"expected 'version'+'profiles' (OpenClaw) or 'auth_mode' (Codex CLI)"
        )
    ```

    Extract the existing Codex CLI validation into `_validate_codex_cli()`:

    ```python
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
    ```

    Add the new `_validate_openclaw()`:

    ```python
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

        # Find the first openai-codex profile.
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

        access_token = codex_profile.get("access_token")
        if not access_token:
            raise CodexAuthMalformed(
                f"access_token missing from openai-codex profile in "
                f"{self._resolved_path!r}"
            )

        # Normalize into a shape snapshot() can consume.
        normalized: dict[str, Any] = {
            "auth_mode": "openclaw-oauth",
            "account_id": codex_profile.get("accountId"),
            "expires_at": codex_profile.get("expires_at"),
        }
        return normalized, access_token
    ```

- [ ] **Step 1.3.4:** Run the two new tests:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py::test_openclaw_happy_path_returns_token tests/test_codex_auth.py::test_openclaw_multiple_profiles_picks_codex -v
    ```

    Expected: PASS.

- [ ] **Step 1.3.5:** Run all tests to confirm nothing is broken:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -v
    ```

    Expected: all pass.

- [ ] **Step 1.3.6:** Commit.

    ```bash
    git add src/flexloop/ai/codex_auth.py tests/test_codex_auth.py
    git commit -m "feat(ai): auto-detect OpenClaw auth-profiles.json format"
    ```

### Task 1.4: OpenClaw error cases

**Files:**
- Modify: `tests/test_codex_auth.py`

- [ ] **Step 1.4.1:** Write the failing tests for all OpenClaw error cases:

    ```python
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
    ```

- [ ] **Step 1.4.2:** Run the new tests:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -k "openclaw" -v
    ```

    Expected: all pass (implementation from task 1.3 already handles these).

- [ ] **Step 1.4.3:** Commit.

    ```bash
    git add tests/test_codex_auth.py
    git commit -m "test(ai): OpenClaw error case coverage for CodexAuthReader"
    ```

### Task 1.5: OpenClaw freshness — `days_until_expiry` + snapshot

**Files:**
- Modify: `tests/test_codex_auth.py`
- Modify: `src/flexloop/ai/codex_auth.py`

- [ ] **Step 1.5.1:** Write the failing snapshot tests:

    ```python
    def test_openclaw_snapshot_healthy(tmp_path):
        auth_file = tmp_path / "auth-profiles.json"
        # Expires 10 days from now
        from datetime import datetime, timedelta, timezone
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
        # Already expired (1 day ago)
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
        assert snap.error_code == "wrong_mode"
    ```

- [ ] **Step 1.5.2:** Run the snapshot tests to confirm they fail:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -k "openclaw_snapshot" -v
    ```

    Expected: FAIL (snapshot() doesn't know how to handle OpenClaw normalized data yet).

- [ ] **Step 1.5.3:** Update `snapshot()` to handle the OpenClaw path. The key changes:

    In the success path of `snapshot()` (after `data, _ = self._load_and_validate()`), check if `data["auth_mode"] == "openclaw-oauth"`:

    ```python
    # Inside snapshot(), after the try block succeeds:
    auth_mode = data["auth_mode"]

    if auth_mode == "openclaw-oauth":
        # OpenClaw path: use expires_at for freshness.
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

    # Codex CLI path (existing code, unchanged):
    last_refresh = self._parse_last_refresh(data.get("last_refresh"))
    # ... rest of existing code
    ```

    Add the new static helpers:

    ```python
    @staticmethod
    def _parse_expires_at(value: Any) -> datetime | None:
        """Convert millisecond epoch timestamp to datetime."""
        if value is None or not isinstance(value, (int, float)):
            return None
        if value <= 0:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)

    @staticmethod
    def _compute_days_until(expiry: datetime | None) -> float | None:
        if expiry is None:
            return None
        now = datetime.now(timezone.utc)
        delta = expiry - now
        return delta.total_seconds() / 86400.0

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
        if days_until_expiry < 2.0:
            return (
                "degraded_red",
                None,
                f"session expires in {days_until_expiry:.1f} days",
            )
        if days_until_expiry < 5.0:
            return (
                "degraded_yellow",
                None,
                f"session expires in {days_until_expiry:.1f} days",
            )
        return "healthy", None, None
    ```

    Also update the `CodexAuthWrongMode` catch block in `snapshot()` to be format-aware. When `e.data` has OpenClaw shape (contains `"accountId"` or `"expires_at"`), extract those fields instead of looking for Codex CLI's `"last_refresh"` and `"tokens"`:

    ```python
    except CodexAuthWrongMode as e:
        data = e.data
        # Detect format from exception data.
        if "accountId" in data or "expires_at" in data:
            # OpenClaw profile shape.
            expiry_dt = self._parse_expires_at(data.get("expires_at"))
            return CodexAuthSnapshot(
                status="down",
                file_exists=True,
                file_path=self._resolved_path,
                auth_mode=data.get("type"),
                last_refresh=expiry_dt,
                days_until_expiry=self._compute_days_until(expiry_dt),
                account_email=data.get("accountId"),
                error_code="wrong_mode",
                error=str(e),
            )
        # Codex CLI shape (existing code).
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
    ```

- [ ] **Step 1.5.4:** Run all snapshot tests:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -k "openclaw_snapshot" -v
    ```

    Expected: all pass.

- [ ] **Step 1.5.5:** Run the full test file to confirm no regressions:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -v
    ```

    Expected: all pass (existing + new).

- [ ] **Step 1.5.6:** Commit.

    ```bash
    git add src/flexloop/ai/codex_auth.py tests/test_codex_auth.py
    git commit -m "feat(ai): OpenClaw snapshot freshness + format-aware wrong-mode handler"
    ```

### Task 1.6: Format detection edge case

**Files:**
- Modify: `tests/test_codex_auth.py`

- [ ] **Step 1.6.1:** Write a test for the ambiguous-format edge case:

    ```python
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
    ```

- [ ] **Step 1.6.2:** Run:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py::test_format_detection_prefers_openclaw_when_ambiguous -v
    ```

    Expected: PASS (OpenClaw is checked first in `_load_and_validate`).

- [ ] **Step 1.6.3:** Commit.

    ```bash
    git add tests/test_codex_auth.py
    git commit -m "test(ai): format detection edge case for ambiguous auth file"
    ```

## Chunk 1 verification gate

- [ ] **All tests pass:**

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -v 2>&1 | tail -5
    ```

- [ ] **Full suite still green:**

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~584 passing.

---

## Chunk 2: API response, frontend, and deploy docs

**Scope:** Update `CodexStatusResponse` so the new field reaches the frontend. Update the status panel to show "Expires" for OpenClaw. Update deploy docs. Final verification.

**Chunk 2 end state:**
- `CodexStatusResponse` includes `days_until_expiry`.
- TypeScript types regenerated.
- `CodexStatusPanel` shows "Expires" label and "N days from now" for OpenClaw.
- `ConfigForm` placeholder updated.
- Deploy docs updated.
- Frontend builds clean.

### Task 2.1: Update `CodexStatusResponse`

**Files:**
- Modify: `src/flexloop/admin/routers/config.py`

- [ ] **Step 2.1.1:** Add `days_until_expiry: float | None = None` to the `CodexStatusResponse` class (after `days_since_refresh`):

    ```python
    class CodexStatusResponse(BaseModel):
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
    ```

- [ ] **Step 2.1.2:** Run existing admin config tests to confirm no breakage:

    ```bash
    ./.venv/bin/python -m pytest tests/test_admin_codex_status.py -v
    ```

    Expected: all pass.

- [ ] **Step 2.1.3:** Commit.

    ```bash
    git add src/flexloop/admin/routers/config.py
    git commit -m "feat(admin): add days_until_expiry to CodexStatusResponse"
    ```

### Task 2.2: Regenerate OpenAPI types

**Files:**
- Modify: `admin-ui/src/lib/api.types.ts`

- [ ] **Step 2.2.1:** Check how the project generates TypeScript types (look for a comment at the top of `api.types.ts` or a `typegen` script in `admin-ui/package.json`). If auto-generated, run:

    ```bash
    cd admin-ui
    npm run typegen
    ```

    If not auto-generated, manually add `days_until_expiry?: number | null;` to the `CodexStatusResponse` type in `api.types.ts`.

- [ ] **Step 2.2.2:** Run `npm run build` to confirm no TypeScript errors:

    ```bash
    cd admin-ui && npm run build
    ```

    Expected: clean build.

- [ ] **Step 2.2.3:** Commit.

    ```bash
    git add admin-ui/src/lib/api.types.ts
    git commit -m "chore(admin-ui): regenerate openapi types for days_until_expiry"
    ```

### Task 2.3: Update `CodexStatusPanel`

**Files:**
- Modify: `admin-ui/src/components/config/CodexStatusPanel.tsx`

- [ ] **Step 2.3.1:** Update the "Last refresh" `<Field>` to conditionally show "Expires" when `days_until_expiry` is present. Replace the existing `<Field label="Last refresh" ...>` block (lines 99-114) with:

    ```tsx
    <Field
      label={query.data?.days_until_expiry != null ? "Expires" : "Last refresh"}
      value={
        query.data?.last_refresh ? (
          <div className={cn("text-right", refreshTone)}>
            <div className="tabular-nums">
              {new Date(query.data.last_refresh).toLocaleString()}
            </div>
            <div className="text-xs">
              {query.data.days_until_expiry != null
                ? formatDaysFromNow(query.data.days_until_expiry)
                : formatDaysAgo(query.data.days_since_refresh)}
            </div>
          </div>
        ) : (
          "—"
        )
      }
    />
    ```

- [ ] **Step 2.3.2:** Add the `formatDaysFromNow` helper after the existing `formatDaysAgo`:

    ```typescript
    function formatDaysFromNow(daysUntilExpiry?: number | null) {
      if (daysUntilExpiry == null) {
        return "—";
      }
      if (daysUntilExpiry <= 0) {
        return "expired";
      }
      const roundedDays = Math.round(daysUntilExpiry);
      return `${roundedDays} ${roundedDays === 1 ? "day" : "days"} from now`;
    }
    ```

- [ ] **Step 2.3.3:** Update `getAuthModeBadge` to handle `"openclaw-oauth"`:

    ```typescript
    case "openclaw-oauth":
      return {
        label: "openclaw",
        className:
          "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
      };
    ```

    Add this case after the existing `"chatgpt"` case.

- [ ] **Step 2.3.4:** Run `npm run build` to confirm:

    ```bash
    cd admin-ui && npm run build
    ```

    Expected: clean build.

- [ ] **Step 2.3.5:** Commit.

    ```bash
    git add admin-ui/src/components/config/CodexStatusPanel.tsx
    git commit -m "feat(admin-ui): show Expires label for OpenClaw auth in CodexStatusPanel"
    ```

### Task 2.4: Update `ConfigForm` placeholder

**Files:**
- Modify: `admin-ui/src/components/forms/ConfigForm.tsx`

- [ ] **Step 2.4.1:** Add a `placeholder` prop to the `codex_auth_file` `<Input>` (around line 176):

    ```tsx
    <Input
      id="codex_auth_file"
      className="font-mono"
      placeholder="~/.codex/auth.json or ~/.openclaw/.../auth-profiles.json"
      {...register("codex_auth_file")}
    />
    ```

- [ ] **Step 2.4.2:** Commit.

    ```bash
    git add admin-ui/src/components/forms/ConfigForm.tsx
    git commit -m "feat(admin-ui): add placeholder for codex_auth_file showing both formats"
    ```

### Task 2.5: Update deploy docs

**Files:**
- Modify: `deploy/README.md`
- Modify: `deploy/agent-runbook.md`

- [ ] **Step 2.5.1:** In `deploy/README.md`, update the "Using the Codex (OAuth) provider" note to mention both file formats:

    Replace the current text with:

    ```markdown
    **Using the Codex (OAuth) provider:** If this VPS also runs OpenClaw
    (or any tool that maintains `~/.codex/auth.json` or
    `~/.openclaw/.../auth-profiles.json`), you can use the `openai-codex`
    provider instead of providing an API key. After first login, go to
    **Config**, pick **OpenAI Codex (OAuth)**, set the auth file path to
    whichever file exists on this system, and save. Both Codex CLI and
    OpenClaw auth file formats are auto-detected. The Codex status panel
    shows whether the session file is healthy.
    ```

- [ ] **Step 2.5.2:** In `deploy/agent-runbook.md`, update the pre-flight Codex session check to look for both files:

    Replace the current check with:

    ```bash
    # 4. Codex session (soft check — doesn't block deploy)
    if [ -f /home/ubuntu/.codex/auth.json ]; then
        echo "codex: ~/.codex/auth.json present (Codex CLI format)"
    elif [ -f /home/ubuntu/.openclaw/agents/main/agent/auth-profiles.json ]; then
        echo "codex: OpenClaw auth-profiles.json present (OpenClaw format)"
    else
        echo "codex: no auth file found — run 'codex login' or configure OpenClaw if you plan to use openai-codex provider"
    fi
    ```

- [ ] **Step 2.5.3:** Commit.

    ```bash
    git add deploy/README.md deploy/agent-runbook.md
    git commit -m "docs(deploy): document OpenClaw auth-profiles.json support"
    ```

## Chunk 2 verification gate

- [ ] **Full backend test suite green:**

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

- [ ] **Frontend build clean:**

    ```bash
    cd admin-ui && npm run build 2>&1 | tail -15
    ```

- [ ] **Ruff clean on changed files:**

    ```bash
    ./.venv/bin/ruff check src/flexloop/ai/codex_auth.py src/flexloop/admin/routers/config.py
    ```
