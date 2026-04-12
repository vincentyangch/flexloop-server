# Codex OAuth Provider Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `openai-codex` LLM provider to FlexLoop that authenticates via the OpenAI Codex CLI's ChatGPT OAuth credentials stored in `~/.codex/auth.json`, free-rides on OpenClaw's token refreshes, and exposes runtime model + reasoning effort configuration through the admin Config page.

**Architecture:** New `OpenAICodexAdapter` subclasses the existing `OpenAIAdapter` via a small behavior-preserving base-class refactor (hook methods + `_RERAISE_EXCEPTIONS` tuple). Reads `~/.codex/auth.json` fresh on every request via a new `CodexAuthReader` helper with a 3-attempt `JSONDecodeError` retry loop. Read-only consumer: never writes the file, never calls the OAuth token endpoint. Adds `codex_auth_file` and `ai_reasoning_effort` fields to the DB-backed `app_settings` row with a new Alembic migration. Admin Config page hides API key fields when the provider is `openai-codex` and shows a new `CodexStatusPanel`. Health page gains a Codex session card. Deploy changes systemd user from `flexloop` to `ubuntu` so FlexLoop can read OpenClaw's existing auth file without cross-user ACL plumbing.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, pytest + pytest-asyncio, React 19 + Vite + Tailwind v4 + shadcn/ui, `openai` Python SDK ≥1.50, Caddy + systemd (deploy). Reuses the existing `LLMAdapter` hierarchy and the `AppSettings` singleton-row pattern.

---

## Spec reference

Full design: `docs/superpowers/specs/2026-04-11-codex-oauth-provider-design.md`

All "Acceptance criteria" from §12 of the spec are test gates for this plan. Do not skip any of them.

## Baseline

- **flexloop-server tip:** `bd8b755` on `main` (post-deploy-runbook work)
- **Test count baseline:** 502 passing via `./.venv/bin/python -m pytest`
- **Parent repo tip:** `c48dcae` on `main` (local-only, no remote)
- **OpenClaw user on VPS:** `ubuntu` (user confirmation during brainstorming — not re-verified in code)
- **`.env` override for `CODEX_AUTH_FILE` is NOT in scope.** The setting is DB-backed only, matching the existing AI settings pattern. Pydantic will still read any matching env var at cold start (that's standard pydantic-settings behavior and we don't disable it), but we won't document or test it as an override path.
- **CodexAuthReader path expansion** uses `os.path.expanduser()`, which resolves `~` via the `HOME` environment variable of the running process. Under the updated systemd unit (`User=ubuntu`), `HOME=/home/ubuntu` is set automatically from the passwd entry.

## Branch strategy

This is "big plan-driven work" per `feedback_branch_strategy.md`. Implementation happens in a dedicated worktree with a feature branch:

- **Worktree:** created during the execution handoff step (not now).
- **Branch name:** `feat/codex-oauth-provider`
- **Base:** `bd8b755` on `main`
- **Merge:** fast-forward only, back to `main` after all chunks land and the full test suite passes.
- **Parent bump:** one chore commit in the umbrella repo (no remote) at the end.

## Skills referenced by this plan

- @superpowers:test-driven-development — every task is structured RED → GREEN → refactor.
- @superpowers:verification-before-completion — every chunk ends with a verification step that must pass before the chunk is marked complete.
- @superpowers:systematic-debugging — if a step's verification fails unexpectedly, use this skill instead of retrying blindly.

---

## File structure

### New backend files

| Path | Responsibility |
|---|---|
| `src/flexloop/ai/codex_auth.py` | `CodexAuthReader` class, `CodexAuth*` exception types, `CodexAuthSnapshot` dataclass. Single responsibility: parse `~/.codex/auth.json` on demand. Never writes. |
| `src/flexloop/ai/openai_codex_adapter.py` | `OpenAICodexAdapter(OpenAIAdapter)`. Thin subclass — overrides `_get_client`, `_chat_extra_kwargs`, `_responses_extra_kwargs` hooks and sets `_RERAISE_EXCEPTIONS`. Inherits response parsing, streaming, tool_use from the base class. |
| `alembic/versions/<hash>_add_codex_fields.py` | Migration adding `codex_auth_file` and `ai_reasoning_effort` columns to `app_settings`. Follows the `_table_exists` / `_column_exists` idempotency guard pattern. |

### New backend test files

| Path | Responsibility |
|---|---|
| `tests/fixtures/auth_json_factory.py` | `make_auth_json(path, **overrides)` helper. Shared fixture used by reader, adapter, config router, and status endpoint tests. |
| `tests/test_codex_auth.py` | Unit tests for `CodexAuthReader` (both `read_access_token()` raise-path and `snapshot()` no-raise-path), retry loop behavior, boundary cases at 5d/9d, JWT email decoding. |
| `tests/test_openai_codex_adapter.py` | Unit tests for `OpenAICodexAdapter` with a fake `AsyncOpenAI` stub that captures request kwargs. Covers both reasoning parameter shapes (`reasoning_effort` on Chat Completions, nested `reasoning={"effort":...}` on Responses fallback). |
| `tests/test_ai_openai_adapter_refactor.py` | Regression tests for the `OpenAIAdapter` base-class refactor: `_get_client` returns persistent client by default, `_chat_extra_kwargs`/`_responses_extra_kwargs` return empty dict by default, `_RERAISE_EXCEPTIONS` is empty tuple by default. |
| `tests/test_admin_codex_status.py` | Integration tests for the new `GET /api/admin/config/codex-status` endpoint, parametrized across fixture states. |
| `tests/test_migration_add_codex_fields.py` | Upgrade/downgrade/idempotent-rerun tests for the new Alembic migration. |

### Modified backend files

| Path | Change |
|---|---|
| `src/flexloop/ai/openai_adapter.py` | Refactor to use `_get_client()` / `_chat_extra_kwargs()` / `_responses_extra_kwargs()` hooks + `_RERAISE_EXCEPTIONS` class attribute. Behavior-preserving. |
| `src/flexloop/ai/factory.py` | Add `openai-codex` branch calling `OpenAICodexAdapter`. |
| `src/flexloop/config.py` | Add `codex_auth_file: str` and `ai_reasoning_effort: str` fields to `Settings`. Add both to `_DB_BACKED_FIELDS`. |
| `src/flexloop/models/app_settings.py` | Add two mapped columns matching the new settings. |
| `src/flexloop/admin/routers/config.py` | Extend `AppSettingsResponse`, `AppSettingsUpdate`, `TestConnectionRequest` with the new fields. Extend `_masked_dict` for audit logging. Add new `GET /api/admin/config/codex-status` endpoint. Update `test_connection` endpoint to pass new kwargs through `create_adapter`. |
| `src/flexloop/admin/routers/health.py` | Extend `_check_ai_provider` with the `openai-codex` branch that calls `CodexAuthReader.snapshot()`. |
| `src/flexloop/routers/ai.py` | Update `get_ai_coach()` and `get_plan_refiner()` to pass `codex_auth_file` and `reasoning_effort` kwargs through to `create_adapter`. |
| `src/flexloop/admin/routers/playground.py` | Update `run_playground()` to pass the new kwargs; add optional overrides to `PlaygroundRunRequest`. |
| `src/flexloop/admin/routers/triggers.py` | Update the `test-ai` trigger handler to pass the new kwargs. |
| `tests/test_admin_auth.py` or `tests/test_admin_config.py` | Extend existing Config router tests to cover the new fields and the provider switch. (Chunk 3 decides which.) |
| `tests/test_admin_health.py` | Extend existing Health tests with the `openai-codex` branch. |

### New frontend files

| Path | Responsibility |
|---|---|
| `admin-ui/src/components/config/CodexStatusPanel.tsx` | Read-only status card. Fetches `GET /api/admin/config/codex-status` on mount and on Recheck click. Renders file existence, auth_mode, last_refresh age with color, email, error message. |

### Modified frontend files

| Path | Change |
|---|---|
| `admin-ui/src/components/forms/ConfigForm.tsx` | Add `openai-codex` option to provider `<Select>`. Conditional rendering: when provider is `openai-codex`, hide `ai_api_key` + `ai_base_url`, show `codex_auth_file` input + `ai_reasoning_effort` dropdown + `<CodexStatusPanel />`. Update Zod schema. |
| `admin-ui/src/pages/HealthPage.tsx` | Nested Codex session sub-card that renders when `ai_provider === "openai-codex"`. Reuses `<CodexStatusPanel />` so Config and Health show identical data from the same endpoint. |
| `admin-ui/src/lib/api.types.ts` (or similar) | OpenAPI-typed schema additions for the new fields and the new endpoint, if the project uses auto-generated types. Otherwise, manual type additions matching the Python Pydantic models. |

### Modified deploy files

| Path | Change |
|---|---|
| `deploy/flexloop.service` | `User=flexloop` → `User=ubuntu`, `Group=flexloop` → `Group=ubuntu`. |
| `deploy/README.md` | Step 2 no longer creates a new system user. Post-first-boot step for switching to `openai-codex` provider. |
| `deploy/agent-runbook.md` | Same `User=ubuntu` adjustment. Pre-flight soft-check for `/home/ubuntu/.codex/auth.json` existence. |

---

## Chunk 1: Base-class refactor + CodexAuthReader

**Scope:** Safe, feature-flag-free refactor of `OpenAIAdapter` that preserves today's behavior byte-for-byte, plus a new standalone `CodexAuthReader` module with exhaustive unit tests. No new adapter. No factory changes. No migration. No routes. No frontend.

**Why this chunk first:** The refactor is the single largest risk in the feature (it touches production code used by every AI request). Landing it separately, with all existing tests passing, isolates the blast radius. If anything regresses, we bisect this one commit.

**Chunk 1 end state:**
- `OpenAIAdapter` uses hook methods internally; all existing tests pass; new regression tests guard the hooks' default behavior.
- `CodexAuthReader` is complete and unit-tested but not wired into the factory yet.
- Test suite: 502 → ~530 (adds regression tests for the refactor + reader unit tests + additional snapshot cases).
- Commit trail: 3 commits (fixture factory, refactor, reader).

**Important constraint surfaced during plan review:** `OpenAIAdapter.client`
must NOT be renamed. Existing tests in `tests/test_adapter_tool_use.py`
monkeypatch `adapter.client = MagicMock()`. The refactor therefore adds a
`_get_client()` method that returns `self.client` by default, and replaces
every direct `self.client.*` call site inside the adapter with a locally
bound `client = self._get_client()` variable — but the instance attribute
name stays `self.client` so existing mocks continue to work.

### Task 1.1: Create the test fixtures helper (`tests/fixtures/auth_json_factory.py`)

**Why first:** Every test in Chunk 1 and later chunks uses this helper. Getting it right up front avoids churn.

**Files:**
- Create: `tests/fixtures/auth_json_factory.py`
- Create: `tests/fixtures/__init__.py` (if it doesn't exist)

- [ ] **Step 1.1.1:** Check whether `tests/fixtures/` already exists. Run from the `flexloop-server/` directory:

    ```bash
    ls tests/fixtures/ 2>/dev/null && echo "exists" || echo "does not exist"
    ```

    Expected: "does not exist". If it exists, skip the directory creation below.

- [ ] **Step 1.1.2:** Create the directory and an empty `__init__.py`:

    ```bash
    mkdir -p tests/fixtures
    touch tests/fixtures/__init__.py
    ```

- [ ] **Step 1.1.3:** Write the fixture factory at `tests/fixtures/auth_json_factory.py`:

    ```python
    """Test helper: materialize a valid-by-default ~/.codex/auth.json on disk.

    Used by CodexAuthReader tests, OpenAICodexAdapter tests, and the admin
    Config / Health / Codex-status endpoint integration tests.
    """
    from __future__ import annotations

    import base64
    import json
    from datetime import datetime, timedelta, timezone
    from pathlib import Path
    from typing import Any


    _DEFAULT_ACCESS_TOKEN = "test-access-token-abc123"
    _DEFAULT_ID_TOKEN_EMAIL = "operator@example.com"
    _DEFAULT_REFRESH_TOKEN = "test-refresh-token-xyz789"


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
    ```

- [ ] **Step 1.1.4:** Verify the module imports cleanly (sanity check):

    ```bash
    ./.venv/bin/python -c "from tests.fixtures.auth_json_factory import make_auth_json; print('ok')"
    ```

    Expected output: `ok`. If the import fails, fix the syntax before proceeding.

- [ ] **Step 1.1.5:** Commit:

    ```bash
    git add tests/fixtures/__init__.py tests/fixtures/auth_json_factory.py
    git commit -m "test: add auth.json fixture factory for codex oauth tests"
    ```

### Task 1.2: Write the failing test for `OpenAIAdapter` hook defaults

**Why:** The base-class refactor must be behavior-preserving. Test the default hook behavior BEFORE changing the production code so we can prove the refactor doesn't regress anything.

**Files:**
- Create: `tests/test_ai_openai_adapter_refactor.py`

- [ ] **Step 1.2.1:** Write the test file:

    ```python
    """Regression tests for the OpenAIAdapter hook refactor.

    These tests pin the DEFAULT behavior of _get_client,
    _chat_extra_kwargs, _responses_extra_kwargs, and _RERAISE_EXCEPTIONS
    so that any subclass (like OpenAICodexAdapter) can rely on the hooks
    being empty/no-op unless explicitly overridden, AND any change to
    the base class that alters these defaults will flag.
    """
    from __future__ import annotations

    import pytest

    from flexloop.ai.openai_adapter import OpenAIAdapter


    def test_openai_adapter_get_client_returns_persistent_instance():
        adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
        client_a = adapter._get_client()
        client_b = adapter._get_client()
        assert client_a is client_b, (
            "default _get_client must return the same persistent AsyncOpenAI "
            "instance on repeated calls — subclasses are the ones that rotate"
        )


    def test_openai_adapter_chat_extra_kwargs_empty_by_default():
        adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
        assert adapter._chat_extra_kwargs() == {}


    def test_openai_adapter_responses_extra_kwargs_empty_by_default():
        adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
        assert adapter._responses_extra_kwargs() == {}


    def test_openai_adapter_reraise_exceptions_empty_tuple_by_default():
        assert OpenAIAdapter._RERAISE_EXCEPTIONS == ()


    def test_openai_adapter_instance_honors_class_reraise_exceptions():
        """Instances read the class attribute — overriding on a subclass
        class attribute is enough; per-instance mutation is NOT supported."""
        adapter = OpenAIAdapter(model="gpt-4o-mini", api_key="sk-test")
        assert adapter._RERAISE_EXCEPTIONS == ()
    ```

- [ ] **Step 1.2.2:** Run the test to confirm it fails with an `AttributeError` (the hooks don't exist yet):

    ```bash
    ./.venv/bin/python -m pytest tests/test_ai_openai_adapter_refactor.py -v 2>&1 | tail -30
    ```

    Expected: All 5 tests ERROR out at collection time or fail with `AttributeError: 'OpenAIAdapter' object has no attribute '_get_client'` (or similar for each hook). This is the RED state.

    If tests accidentally pass, STOP — something in your branch already has the hooks. Investigate before proceeding.

- [ ] **Step 1.2.3:** Do NOT commit yet. The test is RED by design; we commit after GREEN.

### Task 1.3: Implement the `OpenAIAdapter` base-class refactor

**Why:** Get the regression tests from Task 1.2 to GREEN while keeping all pre-existing `OpenAIAdapter` tests passing. This is the largest single code change in the chunk; proceed carefully.

**Files:**
- Modify: `src/flexloop/ai/openai_adapter.py`

- [ ] **Step 1.3.1:** Open `src/flexloop/ai/openai_adapter.py`. Locate the `OpenAIAdapter` class. **Do not rename `self.client`** — existing tests in `tests/test_adapter_tool_use.py` monkeypatch `adapter.client = MagicMock()` and renaming would break them. Add the `_RERAISE_EXCEPTIONS` class attribute and the three new hook methods *alongside* the existing `__init__` (which keeps `self.client` as-is):

    ```python
    class OpenAIAdapter(LLMAdapter):
        _RERAISE_EXCEPTIONS: tuple[type[BaseException], ...] = ()

        def __init__(self, model: str, api_key: str, base_url: str = "", **kwargs):
            super().__init__(model, api_key, base_url)
            client_kwargs = {"api_key": api_key}
            if base_url:
                client_kwargs["base_url"] = base_url
            self.client = AsyncOpenAI(**client_kwargs)  # UNCHANGED — keep the name!

        def _get_client(self) -> "AsyncOpenAI":
            """Return the OpenAI client to use for this request.

            Default: the persistent client built in ``__init__``. Subclasses
            may override to return a fresh client per request (e.g., the
            Codex adapter rotates the Bearer token on every call).
            """
            return self.client

        def _chat_extra_kwargs(self) -> dict:
            """Return extra kwargs merged into ``chat.completions.create``.

            Default: empty dict. Subclasses may override to inject
            provider-specific parameters (e.g., reasoning_effort).
            """
            return {}

        def _responses_extra_kwargs(self) -> dict:
            """Return extra kwargs merged into ``responses.create``.

            Default: empty dict. Subclasses may override for the Responses
            API fallback path (e.g., nested reasoning={"effort":...}).
            """
            return {}
    ```

    Why `_get_client()` returns `self.client` instead of a private `_client`:
    **preserving the existing public attribute name lets existing tests
    continue to monkeypatch `adapter.client = MagicMock()` and the mock
    flows through `_get_client()` correctly**. This is not an aesthetic
    choice — it's a compatibility requirement verified against the current
    test suite.

- [ ] **Step 1.3.2:** Replace every `self.client.` reference in the file with a locally-bound `client = self._get_client()` followed by `client.` usage. **Keep `self.client` as the persistent attribute** — the replacement is only inside method bodies where the client is *used*, not where it's *stored*. Approximately 5 call sites, in:
    - `_stream_chat_completion` (method body)
    - `generate` (fallback path)
    - `chat` (fallback path)
    - `tool_use` (method body)
    - `stream_generate` (method body)

    Example of the pattern. BEFORE:

    ```python
    async def _stream_chat_completion(
        self, messages: list[dict], temperature: float, max_tokens: int,
    ) -> LLMResponse:
        stream = await self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, stream=True,
            stream_options={"include_usage": True},
        )
        ...
    ```

    AFTER:

    ```python
    async def _stream_chat_completion(
        self, messages: list[dict], temperature: float, max_tokens: int,
    ) -> LLMResponse:
        client = self._get_client()
        chat_extra = self._chat_extra_kwargs()
        stream = await client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature,
            max_tokens=max_tokens, stream=True,
            stream_options={"include_usage": True},
            **chat_extra,
        )
        ...
    ```

    Apply the same shape (`client = self._get_client()`, merge extras) in every method that touches `self.client`. For `tool_use`, merge `_chat_extra_kwargs()` into the `chat.completions.create` call. For `stream_generate`, do the same. For the Responses API fallback in `generate` and `chat`, merge `_responses_extra_kwargs()` into `client.responses.create(...)`.

    **Crucially:** `self.client` stays untouched as an instance attribute
    so `test_adapter_tool_use.py` tests that mock it via
    `adapter.client = MagicMock()` continue to route through
    `_get_client()` → `self.client` → the mock.

- [ ] **Step 1.3.3:** Add the `_RERAISE_EXCEPTIONS` bypass to the `generate` method's fallback block. The existing pattern is:

    ```python
    try:
        return await self._stream_chat_completion(messages, temperature, max_tokens)
    except Exception as e:
        logger.warning(f"Chat Completions API failed: {e}. Trying Responses API.")
        try:
            response = await self.client.responses.create(...)
            return self._parse_response(response)
        except Exception as e2:
            logger.error(f"Both API formats failed. Chat: {e}, Responses: {e2}")
            raise e2
    ```

    Change BOTH outer and inner `except Exception` clauses to re-raise the listed exception types before the broad catch:

    ```python
    client = self._get_client()
    chat_extra = self._chat_extra_kwargs()
    responses_extra = self._responses_extra_kwargs()

    try:
        return await self._stream_chat_completion(messages, temperature, max_tokens)
    except self._RERAISE_EXCEPTIONS:
        raise  # bypass fallback on caller-declared exception types
    except Exception as e:
        logger.warning(f"Chat Completions API failed: {e}. Trying Responses API.")
        try:
            response = await client.responses.create(
                model=self.model,
                instructions=system_prompt,
                input=user_prompt,
                temperature=temperature,
                max_output_tokens=max_tokens,
                **responses_extra,
            )
            return self._parse_response(response)
        except self._RERAISE_EXCEPTIONS:
            raise
        except Exception as e2:
            logger.error(f"Both API formats failed. Chat: {e}, Responses: {e2}")
            raise e2
    ```

    Apply the identical bypass to `chat` (which has the same pattern). Do NOT touch `stream_generate` or `tool_use` — they don't have the fallback block and `_RERAISE_EXCEPTIONS` intentionally does not apply there (see spec §5.1 rationale).

- [ ] **Step 1.3.4:** Run the refactor regression tests to confirm they now pass:

    ```bash
    ./.venv/bin/python -m pytest tests/test_ai_openai_adapter_refactor.py -v
    ```

    Expected: 5/5 tests pass.

- [ ] **Step 1.3.5:** Run the existing adapter tests that monkeypatch `adapter.client`. These are the tests most at risk from the refactor:

    ```bash
    ./.venv/bin/python -m pytest tests/test_adapter_tool_use.py tests/test_adapter_streaming.py -v 2>&1 | tail -30
    ```

    Expected: all tests still pass. If any test fails with `AttributeError: 'MagicMock' has no attribute 'chat'` or similar, the refactor probably accidentally touched the `self.client` attribute assignment. Fix the refactor (restore `self.client`) — do NOT change the tests.

- [ ] **Step 1.3.6:** Run the FULL test suite to catch any remaining indirect breakage in `AICoach`, `PlanRefiner`, or other consumers of `OpenAIAdapter`:

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -10
    ```

    Expected: 502 baseline + 5 new refactor regression tests = 507 passing.

- [ ] **Step 1.3.7:** Commit:

    ```bash
    git add src/flexloop/ai/openai_adapter.py tests/test_ai_openai_adapter_refactor.py
    git commit -m "refactor(ai): extract OpenAIAdapter hooks for subclass extension

    Introduces _get_client, _chat_extra_kwargs, _responses_extra_kwargs
    hook methods and a _RERAISE_EXCEPTIONS class attribute with default
    empty-tuple behavior. Preserves all existing OpenAIAdapter behavior
    byte-for-byte — the refactor is a precondition for the upcoming
    OpenAICodexAdapter subclass (which rotates the Bearer token per
    request and injects provider-specific reasoning parameters).

    Adds 5 regression tests to pin the defaults so any future change
    that accidentally alters them is caught immediately."
    ```

### Task 1.4: Write the failing tests for `CodexAuthReader`

**Why:** TDD discipline — write the contract tests before writing the reader.

**Files:**
- Create: `tests/test_codex_auth.py`

- [ ] **Step 1.4.1:** Write the test file:

    ```python
    """Unit tests for flexloop.ai.codex_auth.CodexAuthReader.

    These are pure-filesystem tests using tmp_path fixtures. No network,
    no real auth.json, no mocking of json/os/time.
    """
    from __future__ import annotations

    import json
    import os
    import stat
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
    from tests.fixtures.auth_json_factory import make_auth_json


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
        """Simulate a torn read: first read returns partial content, second
        read returns valid content. The retry loop should succeed.
        """
        auth_file = tmp_path / "auth.json"
        make_auth_json(auth_file)
        valid_content = auth_file.read_text()

        call_count = {"n": 0}
        real_read_text = type(auth_file).read_text

        def flaky_read_text(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "{incomplete"  # torn read on first attempt
            return real_read_text(self, *args, **kwargs)

        with patch.object(type(auth_file), "read_text", flaky_read_text):
            reader = CodexAuthReader(str(auth_file))
            token = reader.read_access_token()

        assert token == "test-access-token-abc123"
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

        # 3 attempts = 2 sleep calls between them
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
        """Non-dict JSON must not crash snapshot().

        json.loads('null') returns None, and `"key" in None` raises
        TypeError. Same for lists, numbers, bare strings, booleans.
        The reader must catch these cases up front so snapshot() can
        keep its never-raises contract.
        """
        auth_file = tmp_path / "auth.json"
        make_auth_json(auth_file, raw_override=non_object_json)
        snap = CodexAuthReader(str(auth_file)).snapshot()
        assert snap.status == "down"
        assert snap.error_code == "malformed"
        assert "not a JSON object" in (snap.error or "")


    def test_snapshot_wrong_mode_preserves_all_metadata_for_ui(tmp_path):
        """When auth_mode is wrong but the file otherwise parsed, snapshot
        must carry auth_mode, last_refresh, days_since_refresh, and
        account_email so the UI can show the full context of WHY the
        session is down (which account, when it was last fresh, etc.).

        Uses a fixed last_refresh 3.5 days in the past so we can assert
        exact values rather than just `is not None`.
        """
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
            "wrong_mode snapshots must carry last_refresh — the file "
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
        """Boundary: 5 days exactly → yellow (inclusive left on yellow range)."""
        auth_file = tmp_path / "auth.json"
        make_auth_json(
            auth_file,
            last_refresh=datetime.now(timezone.utc) - timedelta(days=5),
        )
        snap = CodexAuthReader(str(auth_file)).snapshot()
        assert snap.status == "degraded_yellow"
        assert 4.99 < snap.days_since_refresh < 5.01


    def test_snapshot_days_since_refresh_exactly_9_days_red(tmp_path):
        """Boundary: 9 days exactly → red (inclusive left on red range)."""
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
        # Still healthy because the essential fields are present — just
        # the freshness info is unknown. The status should be healthy OR
        # a new "unknown_freshness" status if you want to be strict. We
        # pick healthy with days_since_refresh=None for simplicity.
        assert snap.days_since_refresh is None
        assert snap.status == "healthy"


    def test_snapshot_tolerates_malformed_id_token(tmp_path):
        auth_file = tmp_path / "auth.json"
        # Write a valid file, then overwrite its id_token with garbage
        make_auth_json(auth_file)
        data = json.loads(auth_file.read_text())
        data["tokens"]["id_token"] = "not-a-valid-jwt"
        auth_file.write_text(json.dumps(data))

        snap = CodexAuthReader(str(auth_file)).snapshot()
        assert snap.status == "healthy"  # unaffected
        assert snap.account_email is None  # gracefully skipped


    def test_snapshot_id_token_email_missing_claim(tmp_path):
        auth_file = tmp_path / "auth.json"
        make_auth_json(auth_file, id_token_email=None)
        snap = CodexAuthReader(str(auth_file)).snapshot()
        assert snap.status == "healthy"
        assert snap.account_email is None


    @pytest.mark.parametrize(
        "kwargs",
        [
            {},  # happy
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
        # If this line raises, the test fails — the invariant is
        # "snapshot() never raises, ever".
        snap = reader.snapshot()
        assert isinstance(snap, CodexAuthSnapshot)
        assert snap.file_path  # always populated
    ```

- [ ] **Step 1.4.2:** Run the test file to confirm every test fails with `ImportError: cannot import name 'CodexAuthReader'` (the module doesn't exist yet):

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -v 2>&1 | tail -15
    ```

    Expected: collection error with `ImportError from flexloop.ai.codex_auth`. RED state confirmed.

- [ ] **Step 1.4.3:** Do NOT commit yet — tests are RED. Commit after GREEN in the next task.

### Task 1.5: Implement `CodexAuthReader`

**Why:** Make the failing tests from Task 1.4 pass. Minimal implementation only — no speculative features.

**Files:**
- Create: `src/flexloop/ai/codex_auth.py`

- [ ] **Step 1.5.1:** Write the module:

    ```python
    """Read-only consumer of ~/.codex/auth.json.

    This module never writes to auth.json, never calls the OpenAI token
    refresh endpoint, and never interacts with the PKCE flow. It simply
    reads whatever OpenClaw / the Codex CLI has last written and exposes
    the access token plus a structured snapshot for UI display and
    health checks.

    See the design spec at
    docs/superpowers/specs/2026-04-11-codex-oauth-provider-design.md
    for rationale and the shared-file threat model.
    """
    from __future__ import annotations

    import base64
    import json
    import os
    import time
    from dataclasses import dataclass
    from datetime import datetime, timezone
    from typing import Any


    # Retry policy for torn-read robustness. See spec §4.3.
    _READ_RETRY_ATTEMPTS = 3
    _READ_RETRY_SLEEP_SECONDS = 0.005

    # Freshness thresholds (days_since_refresh). See spec §5.2 / §7.1.
    _YELLOW_THRESHOLD_DAYS = 5.0
    _RED_THRESHOLD_DAYS = 9.0


    class CodexAuthError(Exception):
        """Base class for all reader errors."""


    class CodexAuthMissing(CodexAuthError):
        """File does not exist or is unreadable (permission denied)."""


    class CodexAuthMalformed(CodexAuthError):
        """File exists but its contents are unparseable or missing required fields."""


    class CodexAuthWrongMode(CodexAuthError):
        """File is in ``api_key`` mode rather than ``chatgpt`` mode.

        Carries the full parsed ``data`` dict as an attribute so
        ``snapshot()`` can extract all observational metadata
        (auth_mode, last_refresh, id_token → email) for UI display
        even though the file is in the wrong mode. The file parsed
        successfully — only the semantic check failed — so every
        status-panel field except the access token is still usable.
        """

        def __init__(self, message: str, data: dict | None = None) -> None:
            super().__init__(message)
            self.data: dict = data or {}


    @dataclass(frozen=True)
    class CodexAuthSnapshot:
        """A point-in-time view of ~/.codex/auth.json for admin UIs.

        ``snapshot()`` is guaranteed never to raise — every failure mode
        is encoded into ``status`` / ``error_code`` / ``error`` fields.
        """

        status: str  # "healthy" | "degraded_yellow" | "degraded_red" | "unconfigured" | "down"
        file_exists: bool
        file_path: str

        auth_mode: str | None = None
        last_refresh: datetime | None = None
        days_since_refresh: float | None = None
        account_email: str | None = None

        error: str | None = None
        error_code: str | None = None  # "missing" | "permission" | "malformed" | "wrong_mode" | "stale"


    class CodexAuthReader:
        """Read ``~/.codex/auth.json`` and expose its access token + metadata.

        Instances are cheap to construct; instantiate one per request and
        call ``read_access_token()`` or ``snapshot()`` as needed.
        """

        def __init__(self, path: str) -> None:
            self._raw_path = path
            self._resolved_path = os.path.expanduser(path)

        # -- request-path ---------------------------------------------------

        def read_access_token(self) -> str:
            """Return the current access token.

            Raises:
                CodexAuthMissing: file does not exist or is unreadable.
                CodexAuthMalformed: unparseable content after retry, or
                    missing required fields (``auth_mode``, ``tokens``,
                    ``tokens.access_token``).
                CodexAuthWrongMode: ``auth_mode`` is not ``"chatgpt"``.
            """
            _, access_token = self._load_and_validate()
            return access_token

        # -- observation path -----------------------------------------------

        def snapshot(self) -> CodexAuthSnapshot:
            """Return a structured snapshot of the current file state.

            Never raises. Every failure mode from ``_load_and_validate()``
            is caught and encoded into ``status`` / ``error_code`` / ``error``.
            By routing through the SAME validation as ``read_access_token()``,
            we guarantee that a snapshot returning ``status="healthy"``
            corresponds to a file that will actually yield a usable token
            at request time.
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
                # File parsed successfully but auth_mode is wrong.
                # Extract every observational field from e.data so the
                # UI can still show last_refresh, days_since_refresh,
                # and account email alongside the error — the user
                # needs this context to diagnose (e.g., "which account
                # is currently logged in via api_key mode?").
                data = e.data
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

            # File is valid; apply freshness classification and email decode.
            auth_mode = data["auth_mode"]  # guaranteed "chatgpt" by _load_and_validate
            last_refresh = self._parse_last_refresh(data.get("last_refresh"))
            days_since_refresh = self._compute_days_since(last_refresh)
            email = self._decode_id_token_email(
                data.get("tokens", {}).get("id_token")
            )
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

        # -- shared validation ----------------------------------------------

        def _load_and_validate(self) -> tuple[dict[str, Any], str]:
            """Read, parse, and validate the file. Return (data, access_token).

            Shared helper used by both ``read_access_token()`` and
            ``snapshot()`` so that both paths apply identical validation
            rules. Raises the same three exception types as
            ``read_access_token()``.
            """
            data = self._load_file_with_retry()
            if "auth_mode" not in data:
                raise CodexAuthMalformed(
                    f"auth_mode field missing from {self._resolved_path!r}"
                )
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

        # -- internals ------------------------------------------------------

        def _load_file_with_retry(self) -> dict[str, Any]:
            """Read + json.load the file with a 3-attempt retry on JSONDecodeError.

            Guarantees the return type is a dict. Non-dict JSON values
            (``null``, a list, a number, a bare string) are treated as
            malformed — this is critical for ``snapshot()``'s "never
            raises" contract, because downstream ``"key" in data``
            checks would otherwise raise ``TypeError`` on non-dict values.
            """
            if not os.path.exists(self._resolved_path):
                raise CodexAuthMissing(
                    f"auth.json not found at {self._resolved_path!r}"
                )
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
                    break  # fall through to the raise below
                else:
                    if not isinstance(parsed, dict):
                        raise CodexAuthMalformed(
                            f"{self._resolved_path!r} parsed but is not a JSON "
                            f"object (got {type(parsed).__name__}); expected a "
                            f"dict like {{\"auth_mode\": ...}}"
                        )
                    return parsed
            raise CodexAuthMalformed(
                f"could not parse {self._resolved_path!r} after "
                f"{_READ_RETRY_ATTEMPTS} attempts: {last_parse_error}"
            )

        def _read_text(self) -> str:
            # Indirection exists so tests can monkey-patch the read path
            # if they need to simulate weird I/O behavior.
            from pathlib import Path
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
        def _compute_days_since(last_refresh: datetime | None) -> float | None:
            if last_refresh is None:
                return None
            now = datetime.now(timezone.utc)
            delta = now - last_refresh
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
            # Fix base64 padding for urlsafe decode
            padding = "=" * (-len(payload_b64) % 4)
            try:
                payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
                payload = json.loads(payload_bytes)
            except (ValueError, json.JSONDecodeError):
                return None
            email = payload.get("email")
            return email if isinstance(email, str) else None

        @staticmethod
        def _classify_freshness(
            days_since_refresh: float | None,
        ) -> tuple[str, str | None, str | None]:
            """Map days_since_refresh → (status, error_code, error).

            Thresholds per spec §5.2 / §7.1:
              * ``None`` → ``healthy`` (no data to classify on)
              * ``< 5`` → ``healthy``
              * ``5 <= x < 9`` → ``degraded_yellow``
              * ``>= 9`` → ``degraded_red``
            """
            if days_since_refresh is None:
                return "healthy", None, None
            if days_since_refresh < _YELLOW_THRESHOLD_DAYS:
                return "healthy", None, None
            if days_since_refresh < _RED_THRESHOLD_DAYS:
                return (
                    "degraded_yellow",
                    None,
                    f"session aging — {days_since_refresh:.1f} days since refresh",
                )
            return (
                "degraded_red",
                "stale",
                f"session stale — {days_since_refresh:.1f} days since refresh",
            )
    ```

- [ ] **Step 1.5.2:** Run the reader tests:

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py -v 2>&1 | tail -40
    ```

    Expected: all tests pass (approximately 25 tests — 12 raise-path + 13 snapshot-path). If any fail, debug with @superpowers:systematic-debugging — read the specific failure output, do NOT retry blindly.

- [ ] **Step 1.5.3:** Run the full suite to confirm no regression:

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: 502 + 5 refactor tests + ~25 reader tests = ~532 passing.

- [ ] **Step 1.5.4:** Commit:

    ```bash
    git add src/flexloop/ai/codex_auth.py tests/test_codex_auth.py
    git commit -m "feat(ai): add CodexAuthReader for read-only consumption of ~/.codex/auth.json

    New flexloop.ai.codex_auth module provides:
    - CodexAuthReader.read_access_token() — request-path: raises
      CodexAuthMissing / CodexAuthMalformed / CodexAuthWrongMode on
      failure. Includes a 3-attempt JSONDecodeError retry loop with
      5ms sleep between attempts for torn-read robustness (no
      assumption about OpenClaw's write strategy).
    - CodexAuthReader.snapshot() — observation path: never raises.
      Returns a CodexAuthSnapshot with status/error_code/error fields
      encoding every failure mode. Used by the admin Health check
      and the (soon-to-exist) codex-status endpoint.
    - Three-level freshness classification: <5d healthy, [5, 9) yellow,
      >=9d red, with inclusive-left / exclusive-right boundaries.
    - Unverified JWT decode of id_token for account email display.
      Failures here gracefully degrade; the reader never fails a
      snapshot because of a malformed id_token.

    Reader is not yet wired into the factory or any adapter — that
    happens in chunk 2."
    ```

---

## Chunk 1 verification gate

Before marking Chunk 1 complete, run these verification commands and confirm every expected output. Do not rely on "it probably worked" — @superpowers:verification-before-completion.

- [ ] **Verify all new tests pass:**

    ```bash
    ./.venv/bin/python -m pytest tests/test_codex_auth.py tests/test_ai_openai_adapter_refactor.py -v 2>&1 | tail -40
    ```

    Expected: ~30 tests passing (25 reader tests + 5 refactor regression tests).

- [ ] **Verify no regressions in the full suite:**

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: approximately 532 passing (502 baseline + 5 refactor + 25 reader). If the count is different, investigate before claiming Chunk 1 is done.

- [ ] **Verify the refactor completed by grepping for direct `self.client.` *usages* (not the attribute assignment) in the adapter:**

    ```bash
    grep -nE 'self\.client\.' src/flexloop/ai/openai_adapter.py
    ```

    Expected: **no matches**. `self.client` should appear EXACTLY ONCE in the file — as the assignment `self.client = AsyncOpenAI(**client_kwargs)` inside `__init__`. Every method body should use `client = self._get_client()` + `client.*` instead. Any direct `self.client.chat.*` or `self.client.responses.*` matches mean the refactor is incomplete.

    To verify the attribute assignment is still there (this is a SEPARATE check):

    ```bash
    grep -n 'self\.client = ' src/flexloop/ai/openai_adapter.py
    ```

    Expected: exactly 1 match in `__init__`.

- [ ] **Verify the commit history is tidy:**

    ```bash
    git log --oneline -5
    ```

    Expected: 3 commits added on top of `bd8b755`:
    1. `test: add auth.json fixture factory for codex oauth tests`
    2. `refactor(ai): extract OpenAIAdapter hooks for subclass extension`
    3. `feat(ai): add CodexAuthReader for read-only consumption of ~/.codex/auth.json`

If all four gates pass, Chunk 1 is complete. Proceed to Chunk 2.

---

## Format note for Chunks 2-5

Chunks 2-5 use a **trimmed detail level** compared to Chunk 1. The task
structure (RED → GREEN → verify → commit) and verification gates are
unchanged, but full code bodies are not re-materialized in the plan —
instead, each task references the authoritative definition in the spec
by section number (e.g. "implement per spec §5.1 `OpenAICodexAdapter`").
The spec at `docs/superpowers/specs/2026-04-11-codex-oauth-provider-design.md`
is the source of truth for every class, method, field, endpoint, and
UI component mentioned below; the plan tells you the *order* and *test
names*, while the spec tells you the *code*.

If you (the executor) find an ambiguity between the plan and the spec,
trust the spec. If the spec itself is unclear, stop and ask — do not
guess. Chunk 1 locked in the hardest design decisions (base-class
refactor shape, reader validation contract, error semantics), so the
remaining chunks should be mostly mechanical wiring.

---

## Chunk 2: `OpenAICodexAdapter` + factory + config schema + migration

**Scope:** Land the new adapter, wire it into `create_adapter()`, add the
two new DB-backed settings fields (`codex_auth_file`,
`ai_reasoning_effort`) to the `Settings` singleton + `AppSettings` model,
and add the idempotent Alembic migration. No router changes, no frontend,
no deploy edits yet. The factory branch exists but is not yet reached
by any production code path (the config router still uses the old
signature) — that wiring comes in Chunk 3.

**Chunk 2 end state:**
- `OpenAICodexAdapter` class exists with full unit-test coverage, tested in
  isolation against a fake `AsyncOpenAI` stub.
- `create_adapter("openai-codex", ...)` returns an `OpenAICodexAdapter`.
- `Settings.codex_auth_file` and `Settings.ai_reasoning_effort` exist in
  `flexloop.config` and are both listed in `_DB_BACKED_FIELDS`.
- `AppSettings` ORM model has the two new mapped columns with safe defaults.
- Alembic migration adds the columns idempotently per
  `feedback_alembic_migrations.md`, and is tested for up/down/re-upgrade.
- Test count: ~532 → ~550 (3 migration + 13 adapter + 2 factory = 18 new tests).
- Commits: 5 (migration, settings/model, adapter tests, adapter impl, factory).

### Task 2.1: Alembic migration for `codex_auth_file` + `ai_reasoning_effort`

**Files:**
- Create: `alembic/versions/<auto-hash>_add_codex_oauth_fields.py`
- Test: `tests/test_migration_add_codex_fields.py`

**Spec references:** §5.1 (Alembic migration), §5.2 (config schema fields),
`feedback_alembic_migrations.md` (idempotency pattern).

- [ ] **Step 2.1.1:** Generate a new Alembic revision stub:

    ```bash
    cd /opt/flexloop/flexloop-server  # or project root in worktree
    ./.venv/bin/alembic revision -m "add codex oauth fields to app_settings"
    ```

    Note the generated filename (there will be a fresh hash prefix). Open
    it for editing.

- [ ] **Step 2.1.2:** Replace the autogenerated body with an idempotent
    upgrade that:
    - Checks `_column_exists("app_settings", "codex_auth_file")` — a helper
      modeled on the existing `_table_exists` pattern (see any phase
      4a/4b migration for reference). Add the helper inline if the file
      is the first to need it.
    - `op.add_column("app_settings", sa.Column("codex_auth_file", sa.String(512), nullable=False, server_default="~/.codex/auth.json"))` when the column is missing.
    - Same pattern for `ai_reasoning_effort`, `sa.String(16)`, `server_default="medium"`.

    `downgrade` drops both columns, also guarded with the column-exists check.

    Why idempotency: per `feedback_alembic_migrations.md`, `init_db`
    calls `Base.metadata.create_all()` BEFORE `command.upgrade()`, so a
    freshly started server will already have the columns when the
    migration runs. A naive `op.add_column` would then fail with
    "duplicate column name". Every new migration in this project must
    be re-runnable.

- [ ] **Step 2.1.3:** Write the migration test at
    `tests/test_migration_add_codex_fields.py`. Three tests:
    - `test_upgrade_adds_columns_to_fresh_schema` — create a throwaway
      in-memory SQLite, run the migration's `upgrade()`, query the
      schema, assert both columns exist with the correct defaults.
    - `test_downgrade_removes_columns` — run upgrade then downgrade,
      assert the columns are gone.
    - `test_upgrade_idempotent_on_rerun` — run upgrade twice, assert
      the second run is a no-op and does not raise.

    Use the same pattern as the existing migration test files (search
    for `test_migration_*` in the repo for prior examples). If none
    exist, follow the minimal Alembic test pattern: construct an
    ``Engine``, call `op.get_bind()` with an inspector, use
    `sqlalchemy.inspect(engine).get_columns("app_settings")`.

- [ ] **Step 2.1.4:** Run the migration tests first (RED — they will
    fail because the migration file's upgrade body hasn't been filled
    in yet in Step 2.1.2 if you haven't done it... but do step 2.1.2
    fully first, then run tests to GREEN):

    ```bash
    ./.venv/bin/python -m pytest tests/test_migration_add_codex_fields.py -v
    ```

    Expected: 3 tests pass.

- [ ] **Step 2.1.5:** Commit:

    ```bash
    git add alembic/versions/<hash>_add_codex_oauth_fields.py tests/test_migration_add_codex_fields.py
    git commit -m "feat(db): alembic migration for codex_auth_file + ai_reasoning_effort"
    ```

### Task 2.2: `Settings` + `AppSettings` model updates

**Files:**
- Modify: `src/flexloop/config.py`
- Modify: `src/flexloop/models/app_settings.py`
- Modify: `tests/test_admin_auth.py` (extend existing `test_app_settings_can_be_created`)

**Spec references:** §5.2 `Settings` changes, §5.2 `AppSettings` model.

- [ ] **Step 2.2.1:** Extend `test_admin_auth.py::test_app_settings_can_be_created`
    to include values for the two new columns when constructing the row
    fixture. This is a RED step — the test will fail to compile/run
    once we start adding the fields but haven't completed the model yet.
    Commit-ready assertion: `row.codex_auth_file == "~/.codex/auth.json"` and
    `row.ai_reasoning_effort == "medium"`.

- [ ] **Step 2.2.2:** Add `codex_auth_file: str = "~/.codex/auth.json"`
    and `ai_reasoning_effort: str = "medium"` to `Settings` in
    `flexloop/config.py`. Add both to the `_DB_BACKED_FIELDS` tuple.
    These values are cold-start defaults — the migration seeds the DB
    row with the same defaults, and `refresh_settings_from_db` will
    override them with whatever the row contains on startup.

- [ ] **Step 2.2.3:** Add matching `Mapped[str]` columns on
    `AppSettings` in `flexloop/models/app_settings.py`. **Use
    `server_default=` (DB-side), NOT `default=` (Python-side).** This is
    important: `init_db` runs `Base.metadata.create_all()` before Alembic,
    and the existing seed migration
    `74637d156bd7_seed_app_settings.py` does a raw SQL `INSERT INTO
    app_settings (id, ai_provider, ai_model, …)` that enumerates only the
    pre-Codex columns. Without `server_default`, the new columns would
    be `NOT NULL` with no DB-level default, and the seed INSERT would
    fail with `NOT NULL constraint failed: app_settings.codex_auth_file`
    on any fresh deployment.

    Use:

    ```python
    codex_auth_file: Mapped[str] = mapped_column(
        String(512), nullable=False, server_default="~/.codex/auth.json"
    )
    ai_reasoning_effort: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="medium"
    )
    ```

    `server_default` emits a `DEFAULT '...'` clause in the `CREATE TABLE`
    DDL, so `create_all()` produces columns that the seed migration's
    raw INSERT can skip without violating NOT NULL. On already-migrated
    deployments, the existing row gets the default filled in when the
    Alembic migration from Task 2.1 runs `op.add_column(...)` with the
    same `server_default`.

    **Do NOT add `default=` as well** — using both is legal but
    redundant here (Python-side defaults only fire on ORM inserts,
    and we have no ORM insert path for the new columns in this
    change). Keeping only `server_default=` makes the intent clear.

- [ ] **Step 2.2.4:** Run the existing Settings + AppSettings tests:

    ```bash
    ./.venv/bin/python -m pytest tests/test_admin_auth.py -v -k "app_settings or Settings" 2>&1 | tail -20
    ```

    Expected: tests pass. If any fail, it's because a test constructs
    `AppSettings(...)` without providing the new fields. With
    `server_default=` on the model, the DB supplies the default on
    INSERT, but if a test constructs an ORM instance in memory and
    accesses the attribute BEFORE flushing to the DB, Python sees
    `None` instead of the default. Fix by either flushing first or
    providing the new fields in the test fixture — do NOT add
    Python-side `default=` to the model.

- [ ] **Step 2.2.5:** Run the full suite to catch indirect breakage:

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~535 passing (502 baseline + 5 refactor + 25 reader + 3 migration + 0 net change from model updates).

- [ ] **Step 2.2.6:** Commit:

    ```bash
    git add src/flexloop/config.py src/flexloop/models/app_settings.py tests/test_admin_auth.py
    git commit -m "feat(config): add codex_auth_file + ai_reasoning_effort to AppSettings"
    ```

### Task 2.3: Write failing tests for `OpenAICodexAdapter`

**Files:**
- Create: `tests/test_openai_codex_adapter.py`

**Spec references:** §8.2 (test list), §5.1 (adapter implementation).

- [ ] **Step 2.3.1:** Write the test file with every test from spec §8.2
    sections "Token handling", "Chat Completions request shape", and
    "Responses API fallback request shape". 13 tests total. All use a
    fake `AsyncOpenAI` stub that captures request kwargs (see spec §8.2
    "Test-only infrastructure" for the fake's shape).

    Place the fake `AsyncOpenAI` class at the top of the test file (or
    in a helper module if you prefer — do not put it in the production
    `flexloop.ai` package).

    Key assertions:
    - **Token rotation:** write token A to the fixture, call
      `adapter.generate(...)`, capture the api_key passed to AsyncOpenAI;
      overwrite fixture with token B, call again, capture again; assert
      the second capture has token B.
    - **Chat Completions top-level field:** assert
      `captured_kwargs["reasoning_effort"] == "medium"` and assert
      `"reasoning"` is NOT a key in `captured_kwargs`.
    - **Responses API nested field:** force the adapter into the
      Responses fallback path by making the mock raise a non-auth
      exception from `chat.completions.create` on the first call.
      Assert the fallback call has `"reasoning" == {"effort": "medium"}`
      and assert `"reasoning_effort"` is NOT a key.
    - **Reasoning=none:** assert the effort field is absent on both paths
      when `reasoning_effort == "none"`.
    - **`_RERAISE_EXCEPTIONS` behavior:** mock `_get_client()` to raise
      `CodexAuthMissing` on the first Chat Completions attempt; assert
      the exception propagates OUT of the adapter (does not hit the
      Responses API fallback).

- [ ] **Step 2.3.2:** Run the test file and confirm everything fails
    with `ImportError: cannot import name 'OpenAICodexAdapter'`:

    ```bash
    ./.venv/bin/python -m pytest tests/test_openai_codex_adapter.py -v 2>&1 | tail -15
    ```

    Expected: collection error. RED confirmed.

- [ ] **Step 2.3.3:** Do NOT commit yet.

### Task 2.4: Implement `OpenAICodexAdapter`

**Files:**
- Create: `src/flexloop/ai/openai_codex_adapter.py`

**Spec references:** §5.1 `OpenAICodexAdapter` section. Follow the spec's
implementation sketch verbatim, including the `_RERAISE_EXCEPTIONS`
class attribute and the four overridden hooks.

- [ ] **Step 2.4.1:** Write the adapter file. Key points from the spec:
    - Subclasses `OpenAIAdapter` from Chunk 1.
    - `__init__` takes `(model, auth_file, reasoning_effort="medium",
      **kwargs)`. Stores `self._auth_file` and `self._reasoning_effort`.
      Calls `super().__init__(model, api_key="codex-oauth-placeholder",
      base_url="")` — the placeholder api_key is required because
      `AsyncOpenAI()` rejects empty strings; the placeholder is never
      used because `_get_client()` is overridden. Add a comment
      explaining this foot-gun.
    - Sets `_RERAISE_EXCEPTIONS = (CodexAuthMissing, CodexAuthMalformed, CodexAuthWrongMode, openai.AuthenticationError)`
      as a class attribute. Note: importing `openai.AuthenticationError`
      adds a small module-level import — do it at the top of the file.
    - Overrides `_get_client()` to call `CodexAuthReader(self._auth_file).read_access_token()`
      and return a fresh `AsyncOpenAI(api_key=<token>)`.
    - Overrides `_chat_extra_kwargs()` to return
      `{"reasoning_effort": self._reasoning_effort}` when the effort
      is not `"none"`, else `{}`.
    - Overrides `_responses_extra_kwargs()` to return
      `{"reasoning": {"effort": self._reasoning_effort}}` when not
      `"none"`, else `{}`.

- [ ] **Step 2.4.2:** Run the adapter tests:

    ```bash
    ./.venv/bin/python -m pytest tests/test_openai_codex_adapter.py -v 2>&1 | tail -30
    ```

    Expected: 13/13 pass.

- [ ] **Step 2.4.3:** Run the full suite to catch regressions:

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~548 passing (535 + 13 new adapter tests).

- [ ] **Step 2.4.4:** Commit:

    ```bash
    git add src/flexloop/ai/openai_codex_adapter.py tests/test_openai_codex_adapter.py
    git commit -m "feat(ai): add OpenAICodexAdapter for ChatGPT OAuth sessions"
    ```

### Task 2.5: Wire `openai-codex` into `create_adapter()`

**Files:**
- Modify: `src/flexloop/ai/factory.py`
- Create: `tests/test_ai_factory.py` (if it does not already exist)

**Spec references:** §5.2 factory.py branch.

- [ ] **Step 2.5.1:** Write a factory test first. The test calls
    `create_adapter(provider="openai-codex", model="gpt-5.1-codex-max",
    codex_auth_file="/tmp/fake-auth.json", reasoning_effort="medium")`
    and asserts the result is an `OpenAICodexAdapter` instance with the
    right `_auth_file` and `_reasoning_effort`. A second negative test
    confirms `create_adapter(provider="unknown")` still raises
    `ValueError`.

- [ ] **Step 2.5.2:** Run the test — it should fail with
    `ValueError: Unknown provider: openai-codex`.

- [ ] **Step 2.5.3:** Add the new `elif provider == "openai-codex":`
    branch to `create_adapter()` in `flexloop/ai/factory.py`. The
    branch pops `codex_auth_file` and `reasoning_effort` from `kwargs`
    (with defaults) and passes them into `OpenAICodexAdapter(...)`.

- [ ] **Step 2.5.4:** Run the factory test — should pass.

- [ ] **Step 2.5.5:** Run the full suite:

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~550 passing.

- [ ] **Step 2.5.6:** Commit:

    ```bash
    git add src/flexloop/ai/factory.py tests/test_ai_factory.py
    git commit -m "feat(ai): register openai-codex provider in create_adapter factory"
    ```

## Chunk 2 verification gate

- [ ] **Verify only Chunk 2's new tests pass:**

    ```bash
    ./.venv/bin/python -m pytest tests/test_migration_add_codex_fields.py tests/test_openai_codex_adapter.py tests/test_ai_factory.py -v 2>&1 | tail -30
    ```

    Expected: ~18 tests passing (3 migration + 13 adapter + 2 factory).

- [ ] **Verify no regressions:**

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~550 total passing.

- [ ] **Verify the migration is discoverable by Alembic:**

    ```bash
    ./.venv/bin/alembic history 2>&1 | head -20
    ```

    Expected: the new revision appears in the chain with the
    expected down_revision.

- [ ] **Verify commit history is tidy:**

    ```bash
    git log --oneline -10
    ```

    Expected: 5 new commits on top of Chunk 1's 3 commits.

If all four gates pass, Chunk 2 is complete.

---

## Chunk 3: Backend routes — config schemas, codex-status endpoint, callers, health

**Scope:** Plumb the new fields through every backend HTTP surface. After
this chunk, the admin Config page can read/write the new fields through
the API, the Health check reports Codex session status, and every
`create_adapter()` call site passes the new kwargs through. No frontend
changes yet. No deploy edits.

**Chunk 3 end state:**
- `GET /api/admin/config` and `PUT /api/admin/config` accept and return
  `codex_auth_file` + `ai_reasoning_effort`.
- `POST /api/admin/config/test-connection` supports per-call overrides
  for the Codex fields.
- `GET /api/admin/config/codex-status` is new, always-uncached, reads
  `CodexAuthReader.snapshot()`.
- `_check_ai_provider` branches on provider and returns the Codex snapshot
  structure when the active provider is `openai-codex`.
- Every production `create_adapter()` call site reads the new settings
  and passes them through.
- Test count: ~550 → ~567 (3 config + 7 codex-status + 3 test-connection + 4 health = 17 new tests).
- Commits: 5.

### Task 3.1: Extend Config router schemas for new fields

**Files:**
- Modify: `src/flexloop/admin/routers/config.py`
- Modify: `tests/test_admin_auth.py` (or a dedicated `test_admin_config.py` — match existing location)

**Spec references:** §5.2 `admin/routers/config.py`, §6.3 GET flow, §6.5 PUT flow.

- [ ] **Step 3.1.1:** Write failing tests (RED): `test_get_config_includes_new_fields`,
    `test_put_config_updates_codex_fields`, `test_put_config_audit_log_captures_new_fields`.
    Pattern follows existing Config router tests.

- [ ] **Step 3.1.2:** Run the tests — expect failures on missing response fields.

- [ ] **Step 3.1.3:** Extend the Pydantic schemas. **Field naming differs**
    between persistence and override schemas — match the existing pattern
    (`ai_provider` on settings vs. `provider` on override payloads, `ai_api_key`
    vs. `api_key`, etc.):

    - `AppSettingsResponse` and `AppSettingsUpdate` add:
      - `codex_auth_file: str | None = None` (on Update; required string on Response)
      - `ai_reasoning_effort: str | None = None` (on Update; required string on Response)

    - `TestConnectionRequest` adds:
      - `codex_auth_file: str | None = None` — override for per-call testing
      - `reasoning_effort: str | None = None` — **no `ai_` prefix**, matching the existing
        `provider` / `model` / `api_key` / `base_url` override naming convention

    - `_masked_dict` adds both `codex_auth_file` and `ai_reasoning_effort` (with
      the `ai_` prefix — it's the persistence-side dict). Neither field is masked.

    See spec §5.2 for exact field additions. The `reasoning_effort` vs
    `ai_reasoning_effort` split is important: `test_connection` accepts the
    override via the un-prefixed name, while the persistent DB/API uses the
    `ai_` prefix.

- [ ] **Step 3.1.4:** Run the tests — expect GREEN.

- [ ] **Step 3.1.5:** Run full suite.

- [ ] **Step 3.1.6:** Commit with `feat(admin): expose codex_auth_file + ai_reasoning_effort in config router`.

### Task 3.2: New `GET /api/admin/config/codex-status` endpoint

**Files:**
- Modify: `src/flexloop/admin/routers/config.py` (add endpoint)
- Create: `tests/test_admin_codex_status.py`

**Spec references:** §5.2 (new endpoint), §6.4 (flow), §8.5 (test list).

- [ ] **Step 3.2.1:** Write failing tests from spec §8.5 (7 tests: happy,
    aging, stale, missing file, malformed, admin-auth required, uncached).
    Use the `make_auth_json` fixture factory from Chunk 1 for file
    variants. Tests go in a new `tests/test_admin_codex_status.py`.

- [ ] **Step 3.2.2:** Run the tests — expect collection or 404 failures.

- [ ] **Step 3.2.3:** Add the `GET /api/admin/config/codex-status`
    endpoint to `config.py`. Shape: requires admin auth, reads
    `settings.codex_auth_file`, calls `CodexAuthReader(path).snapshot()`,
    returns the snapshot fields as JSON. The endpoint is intentionally
    **uncached** — every call reads the file fresh. Define a
    `CodexStatusResponse` Pydantic model matching the `CodexAuthSnapshot`
    dataclass fields (status, file_exists, file_path, auth_mode,
    last_refresh, days_since_refresh, account_email, error, error_code).

- [ ] **Step 3.2.4:** Run the tests — expect GREEN.

- [ ] **Step 3.2.5:** Run full suite.

- [ ] **Step 3.2.6:** Commit with `feat(admin): add GET /api/admin/config/codex-status endpoint`.

### Task 3.3: Extend `test_connection` endpoint for Codex overrides

**Files:**
- Modify: `src/flexloop/admin/routers/config.py`
- Modify: `tests/test_admin_auth.py` or `tests/test_admin_config.py`

**Spec references:** §5.2 test_connection changes, §8.4 (tests).

- [ ] **Step 3.3.1:** Write failing tests: `test_test_connection_codex_happy`,
    `test_test_connection_codex_missing_file`, `test_test_connection_codex_expired_token`.
    Each test PUTs the provider to `openai-codex` via the Config PUT
    (or uses the payload's per-call overrides), then POSTs to
    `/test-connection`. Use `make_auth_json` for the file state, and a
    fake `AsyncOpenAI` patched into `flexloop.ai.factory.OpenAICodexAdapter._get_client`
    for the OpenAI side (see spec §8.4).

- [ ] **Step 3.3.2:** Run tests — expect failures.

- [ ] **Step 3.3.3:** Update the `test_connection` handler to read
    `row.codex_auth_file` and `row.ai_reasoning_effort` (or the payload
    overrides) and pass them as kwargs into `create_adapter(...)`. No
    other logic changes — the handler's flow is "build adapter, fire
    tiny generate, return status/latency/text/error" and the adapter
    itself handles everything else.

- [ ] **Step 3.3.4:** Run the tests — expect GREEN.

- [ ] **Step 3.3.5:** Run full suite.

- [ ] **Step 3.3.6:** Commit with `feat(admin): test-connection supports codex overrides`.

### Task 3.4: Health check branch for `openai-codex`

**Files:**
- Modify: `src/flexloop/admin/routers/health.py`
- Modify: `tests/test_admin_health.py`

**Spec references:** §5.2 health.py, §8.6 (test list).

- [ ] **Step 3.4.1:** Write failing tests from spec §8.6 (4 tests:
    codex healthy, codex missing, non-codex unaffected, cache respects
    60s TTL).

- [ ] **Step 3.4.2:** Run tests — expect failures.

- [ ] **Step 3.4.3:** Extend `_check_ai_provider()` in `health.py`.
    When `settings.ai_provider == "openai-codex"`, build the health dict
    from `CodexAuthReader(settings.codex_auth_file).snapshot()` instead
    of the existing openai-key-probe logic. Map `snapshot.status` directly
    into the health row's `status` field.

    **Also fix a pre-existing cache bug surfaced by this feature.** The
    current `_check_ai_provider` caches its result in module-level
    `_ai_cache` / `_ai_cache_at` variables with a 60-second TTL, but
    **the cache does not include the provider in its key**. When the
    operator switches providers via the Config page,
    `refresh_settings_from_db` updates `settings.ai_provider`, but the
    Health page keeps returning the stale cached row for up to 60s,
    which would break the Chunk 4 manual smoke test (Step 4.5.6 switches
    provider and expects the Codex card to disappear immediately).

    Fix: include the current `settings.ai_provider` in the cache
    validity check. When the cached provider does not match the current
    provider, treat it as a cache miss:

    ```python
    async def _check_ai_provider() -> dict[str, Any]:
        global _ai_cache, _ai_cache_at
        now = time.time()
        current_provider = _settings.ai_provider
        if (
            _ai_cache is not None
            and _ai_cache.get("provider") == current_provider
            and (now - _ai_cache_at) < 60
        ):
            return {**_ai_cache, "cached": True}
        # ... existing branch dispatch (openai-codex vs everything else) ...
    ```

    The `provider` field is already stored in the cached result (see
    existing code), so this is a one-line check addition on the lookup
    side — no schema change.

    Add a test in Task 3.4.1 named `test_health_ai_provider_cache_invalidates_on_provider_switch`:
    call `_check_ai_provider()` with provider=`openai`, then monkey-patch
    `_settings.ai_provider = "openai-codex"`, call again, assert the
    second call did NOT return the first call's cached result
    (check for the `cached: True` flag being absent, or compare a
    per-branch marker field).

- [ ] **Step 3.4.4:** Run the tests — expect GREEN.

- [ ] **Step 3.4.5:** Run full suite.

- [ ] **Step 3.4.6:** Commit with `feat(admin): health check reports codex session status`.

### Task 3.5: Update all 5 `create_adapter()` call sites

**Files:**
- Modify: `src/flexloop/routers/ai.py` (2 call sites: `get_ai_coach()`, `get_plan_refiner()`)
- Modify: `src/flexloop/admin/routers/playground.py` (1 call site)
- Modify: `src/flexloop/admin/routers/triggers.py` (1 call site — the phase 5c `test-ai` trigger)
- Modify: `src/flexloop/admin/routers/config.py` (1 call site — already touched in Task 3.3)

**Spec references:** §5.2 caller inventory.

- [ ] **Step 3.5.1:** For each of the 4 files (config.py is already done),
    find the `create_adapter(...)` call and add:

    ```python
    codex_auth_file=settings.codex_auth_file,
    reasoning_effort=settings.ai_reasoning_effort,
    ```

    as additional kwargs. The kwargs are ignored for non-Codex providers
    (the factory pops them only in the `openai-codex` branch).

    For `playground.py`, also add matching per-call overrides to
    `PlaygroundRunRequest` schema and use them via the `payload.X_override or settings.X`
    pattern that already exists for `provider`/`model`/`api_key`/`base_url`.

- [ ] **Step 3.5.2:** No new tests needed beyond what's already in
    Tasks 3.3 and earlier — the existing integration tests exercise
    these call sites and will catch any regression. Run full suite:

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: all tests still pass. ~567 total.

- [ ] **Step 3.5.3:** Grep verification — every `create_adapter(`
    call in the src tree should include `codex_auth_file`:

    ```bash
    grep -n "create_adapter(" src/flexloop/ --include='*.py' -r
    ```

    For each match, open the file and confirm the new kwargs are passed.
    Missing any one means that code path will silently ignore the
    Codex settings.

- [ ] **Step 3.5.4:** Commit with `feat(admin): pass codex kwargs through all create_adapter callers`.

## Chunk 3 verification gate

- [ ] **Verify all chunk 3 tests pass:**

    ```bash
    ./.venv/bin/python -m pytest tests/test_admin_codex_status.py tests/test_admin_health.py tests/test_admin_auth.py -v -k "codex or config" 2>&1 | tail -40
    ```

- [ ] **Verify no regressions:**

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~567 passing.

- [ ] **Verify every caller is updated:** run the grep from Step 3.5.3
    manually and confirm all 5 sites have the new kwargs.

- [ ] **Verify commit history:** 5 new commits on top of Chunk 2.

If all gates pass, Chunk 3 is complete.

---

## Chunk 4: Frontend — ConfigForm, CodexStatusPanel, HealthPage

**Scope:** User-visible changes. After this chunk, an admin operator can
open the Config page, pick `openai-codex` as the provider, see the new
fields appear while the API-key fields hide, save, and see the session
status on both the Config page and the Health page. Backend is
unchanged from Chunk 3.

**Chunk 4 end state:**
- `ConfigForm.tsx` has provider-conditional rendering.
- `CodexStatusPanel.tsx` exists and fetches `/api/admin/config/codex-status`.
- `HealthPage.tsx` shows the Codex session card when the active provider is
  `openai-codex`.
- OpenAPI types regenerated (if the project auto-generates) or manually
  updated to include the new schema.
- Manual smoke test passed (documented at the end of the chunk).
- Commits: 4.

**TDD note for this chunk:** The frontend does not have unit tests in
this project (per `feedback_execution_quirks.md`: "shadcn/Playwright
idioms"). Chunk 4's "verification" is a manual browser smoke test
rather than automated React tests, following the phase 3/4a/4b/4c/4d
precedent. If you (the executor) want to add Vitest coverage for the
new components, that's fine but out of plan scope.

### Task 4.1: Regenerate OpenAPI types (or add manual types)

**Files:**
- Modify: `admin-ui/src/lib/api.types.ts` (or equivalent path)

- [ ] **Step 4.1.1:** Check how the project generates TypeScript types.
    The existing file likely has a comment at the top saying
    "Do not edit, run `npm run typegen`" or similar. If so, run:

    ```bash
    cd admin-ui
    npm run typegen   # or whatever the project calls its openapi-typescript invocation
    ```

    If the project does NOT auto-generate, manually add type
    definitions for `codex_auth_file`, `ai_reasoning_effort`, and the
    `CodexStatusResponse` endpoint. Use the existing `AppSettingsResponse`
    type as a template.

- [ ] **Step 4.1.2:** Run the frontend build:

    ```bash
    npm run build
    ```

    Expected: build succeeds. If there are type errors in existing code
    because the regenerated types removed something, fix the references
    in the offending files.

- [ ] **Step 4.1.3:** Commit with `chore(admin-ui): regenerate openapi types for codex oauth fields`.

### Task 4.2: `CodexStatusPanel` component

**Files:**
- Create: `admin-ui/src/components/config/CodexStatusPanel.tsx`

**Spec references:** §5.3 frontend components, §6.4 data flow.

- [ ] **Step 4.2.1:** Write the component per spec §5.3. Key elements:
    - Fetches `GET /api/admin/config/codex-status` on mount via
      `useQuery` (TanStack Query — the project already uses it, search
      for `useQuery` in ConfigPage.tsx for the idiom).
    - Renders a small Card component from shadcn/ui with:
      - Status dot (green / yellow / red) matching `status`
      - `file_path` (monospace)
      - "File exists" ✓/✗
      - `auth_mode` badge
      - `last_refresh` timestamp + "N days ago" + color
      - `account_email` (or "—")
      - Error message when `error` is non-null
      - Recheck button that calls `refetch()` from the query
    - Color mapping: `healthy` → green, `degraded_yellow` → amber,
      `degraded_red` / `down` → red, `unconfigured` → gray.

- [ ] **Step 4.2.2:** Commit with `feat(admin-ui): add CodexStatusPanel component`.

### Task 4.3: Update `ConfigForm.tsx` with provider-conditional rendering

**Files:**
- Modify: `admin-ui/src/components/forms/ConfigForm.tsx`
- Modify: `admin-ui/src/pages/ConfigPage.tsx` (formValuesToUpdate mapping — see Step 4.3.2b)

**Spec references:** §5.4 frontend modified files.

- [ ] **Step 4.3.1:** Add `<SelectItem value="openai-codex">OpenAI Codex (OAuth)</SelectItem>`
    to the provider Select, after the existing four options.

- [ ] **Step 4.3.2:** Update the Zod schema to include `codex_auth_file: z.string()`
    and `ai_reasoning_effort: z.enum(["none", "minimal", "low", "medium", "high"])`.
    Add matching defaults in the form's `defaultValues`.

- [ ] **Step 4.3.2b:** Update `ConfigPage.tsx::formValuesToUpdate()` to
    include the two new fields in the returned `ConfigUpdate` object.
    The existing function explicitly enumerates every field it forwards
    to the PUT request — if you skip this step, the new fields get
    dropped silently on Save and the user will see "Config saved"
    but nothing actually persisted.

    Add these two lines to the returned object literal:

    ```typescript
    codex_auth_file: v.codex_auth_file,
    ai_reasoning_effort: v.ai_reasoning_effort,
    ```

    Verify by grepping:

    ```bash
    grep -A20 "function formValuesToUpdate" admin-ui/src/pages/ConfigPage.tsx
    ```

    The returned object should list every field from the Zod schema.

- [ ] **Step 4.3.3:** Add conditional rendering based on `provider === "openai-codex"`:
    - Hide the `ai_api_key` input entirely
    - Hide the `ai_base_url` input entirely
    - Show a new text input for `codex_auth_file` with the default value
      `~/.codex/auth.json`
    - Show a new Select dropdown for `ai_reasoning_effort` with the
      5 enum values
    - Render `<CodexStatusPanel />` below the provider select

    Use the existing `provider === "openai"` pattern in the file for
    reference (if there is no existing conditional, add a
    `watch("ai_provider")` hook at the top of the component).

- [ ] **Step 4.3.4:** Update the `ai_model` input's `placeholder` to
    `"e.g. gpt-5.1-codex-max"` when provider is `openai-codex`.
    (The input itself stays as a free-text input per the spec's
    Q4 = i decision.)

- [ ] **Step 4.3.5:** Run `npm run build` and confirm no TypeScript
    errors. If there are, fix them.

- [ ] **Step 4.3.6:** Commit with `feat(admin-ui): conditional rendering for openai-codex in ConfigForm`.

### Task 4.4: Update `HealthPage.tsx` to show Codex session card

**Files:**
- Modify: `admin-ui/src/pages/HealthPage.tsx`

- [ ] **Step 4.4.1:** Find the existing AI provider health card. Below
    or inside it, add a conditional block that renders
    `<CodexStatusPanel />` when the current `ai_provider === "openai-codex"`.
    Reuse the same component as `ConfigForm` — both Config and Health
    read from the same `/codex-status` endpoint.

- [ ] **Step 4.4.2:** Run `npm run build`.

- [ ] **Step 4.4.3:** Commit with `feat(admin-ui): add codex session card to HealthPage`.

### Task 4.5: Manual smoke test in browser

**Spec references:** §12 acceptance criteria 8-10.

Run the dev server and the backend locally, then walk through the UI:

- [ ] **Step 4.5.1:** Start the backend and dev server. Two terminals:

    ```bash
    # terminal 1
    cd flexloop-server
    ./.venv/bin/uvicorn flexloop.main:app --host 127.0.0.1 --port 8000 --reload

    # terminal 2
    cd flexloop-server/admin-ui
    npm run dev
    ```

- [ ] **Step 4.5.2:** Open `http://localhost:5173/admin` and log in as
    the bootstrap admin. Go to **Config**. Pick provider `OpenAI Codex (OAuth)`.

    Expected visible changes:
    - `API Key` input disappears.
    - `Base URL` input disappears.
    - New `Codex auth file` input appears with value `~/.codex/auth.json`.
    - New `Reasoning effort` dropdown appears with default `medium`.
    - `CodexStatusPanel` renders below the provider select and shows
      the current state of YOUR local `~/.codex/auth.json` (it will be
      green if you have a valid Codex login on this machine — our
      `codex:setup` confirmed `vincentcy86@gmail.com` is logged in).

- [ ] **Step 4.5.3:** Click **Save**. Confirm the config persists on
    reload and the banner shows success.

- [ ] **Step 4.5.4:** Click the **Test Connection** button. Confirm
    the result renders inline. If your local Codex session is valid,
    you should see a success with a latency number and a short response
    text from the model.

- [ ] **Step 4.5.5:** Visit the **Health** page. Confirm the Codex
    session card appears with the same data as the Config status panel.

- [ ] **Step 4.5.6:** Switch the provider back to `OpenAI` and save.
    Confirm the API key field reappears and the Codex card disappears
    from the Health page. Rollback works.

- [ ] **Step 4.5.7:** No commit needed for this step (pure validation).
    If any expected behavior is missing, go back to Task 4.3 or 4.4
    to debug with @superpowers:systematic-debugging.

## Chunk 4 verification gate

- [ ] **All backend tests still pass:**

    ```bash
    cd flexloop-server
    ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~567 passing (same as end of Chunk 3 — Chunk 4 adds no
    backend tests).

- [ ] **Frontend build clean:**

    ```bash
    cd flexloop-server/admin-ui
    npm run build 2>&1 | tail -20
    ```

    Expected: build succeeds with no TypeScript errors.

- [ ] **Manual smoke checklist** from Task 4.5 all green.

- [ ] **Commit history:** 4 new commits on top of Chunk 3.

---

## Chunk 5: Deploy path + final verification + merge

**Scope:** The last edits to deploy files so a fresh VPS runs FlexLoop
as `ubuntu` (matching OpenClaw). Then a final full-suite run, merge the
feature branch back to `main`, bump the parent submodule.

**Chunk 5 end state:**
- `deploy/flexloop.service` runs as `ubuntu`.
- `deploy/README.md` and `deploy/agent-runbook.md` match.
- Full test suite green.
- Feature branch merged to `main` (fast-forward).
- Parent submodule bumped.
- Commits: 2 (deploy edits, submodule bump).

### Task 5.1: Update `deploy/flexloop.service`

**Files:**
- Modify: `flexloop-server/deploy/flexloop.service`

**Spec references:** §5.5 deploy files.

- [ ] **Step 5.1.1:** Change `User=flexloop` → `User=ubuntu` and
    `Group=flexloop` → `Group=ubuntu`. Leave everything else exactly
    as-is (ExecStart, Restart, hardening flags).

- [ ] **Step 5.1.2:** No tests — this is a pure text edit in a systemd
    unit file. Verification is the line count diff:

    ```bash
    git diff deploy/flexloop.service
    ```

    Expected: exactly 2 lines changed.

### Task 5.2: Update `deploy/README.md`

**Files:**
- Modify: `flexloop-server/deploy/README.md`

- [ ] **Step 5.2.1:** Find step 2 of the walkthrough ("Create the system user").
    Replace it with "Ensure `ubuntu` owns `/opt/flexloop`". Drop the
    `useradd --system --create-home --shell /bin/bash flexloop` line.
    Keep the `mkdir -p /opt/flexloop` and chown, just chown to ubuntu.

- [ ] **Step 5.2.2:** Add a note near step 5 (`.env` configuration) or
    step 10 (allowed origins) that for the `openai-codex` provider,
    the operator should set `ai_provider = "openai-codex"` via the
    Config page after first login. Point at the spec if they want
    details.

- [ ] **Step 5.2.3:** Update the troubleshooting section of the README
    to mention Codex session expiry as a possible cause of "AI
    unavailable" if the Codex provider is active.

### Task 5.3: Update `deploy/agent-runbook.md`

**Files:**
- Modify: `flexloop-server/deploy/agent-runbook.md`

- [ ] **Step 5.3.1:** Same `User=ubuntu` consistency changes.

- [ ] **Step 5.3.2:** Add a pre-flight soft-check to the runbook's
    pre-flight block:

    ```bash
    # Codex session (soft check — doesn't block deploy)
    if [ -f /home/ubuntu/.codex/auth.json ]; then
        echo "codex: auth.json present (openai-codex provider ready)"
    else
        echo "codex: auth.json missing — run 'codex login' or 'openclaw auth login --provider openai-codex' if you plan to use openai-codex provider"
    fi
    ```

    This does not block the deploy — the operator may not be using the
    Codex provider at all. It's a heads-up.

- [ ] **Step 5.3.3:** Commit all three deploy files:

    ```bash
    git add deploy/flexloop.service deploy/README.md deploy/agent-runbook.md
    git commit -m "chore(deploy): run as ubuntu user and document openai-codex setup"
    ```

### Task 5.4: Final full-suite + lint pass

- [ ] **Step 5.4.1:** Run the full backend test suite one more time:

    ```bash
    ./.venv/bin/python -m pytest 2>&1 | tail -10
    ```

    Expected: ~567 passing, no failures, no unexpected warnings.

- [ ] **Step 5.4.2:** Run ruff (the project uses it per `pyproject.toml`):

    ```bash
    ./.venv/bin/ruff check src/ tests/
    ```

    Expected: no errors. Fix any that appear (usually unused imports
    or line length).

- [ ] **Step 5.4.3:** Run the frontend build:

    ```bash
    cd admin-ui && npm run build
    ```

    Expected: clean build.

- [ ] **Step 5.4.4:** If the three checks are clean, merge the feature
    branch back to `main`:

    ```bash
    cd flexloop-server
    git checkout main
    git merge --ff-only feat/codex-oauth-provider
    # no push to origin yet — operator decides when to push
    ```

    If the merge is NOT fast-forward, something landed on `main` during
    the implementation window. Rebase the feature branch and retry.

- [ ] **Step 5.4.5:** Clean up the worktree per
    @superpowers:using-git-worktrees:

    ```bash
    git worktree remove /path/to/worktree
    git branch -d feat/codex-oauth-provider
    ```

### Task 5.5: Parent submodule pointer bump

**Files:**
- Modify: (parent umbrella repo) `flexloop-server` gitlink

- [ ] **Step 5.5.1:** From the parent `FlexLoop/` working tree:

    ```bash
    cd /Users/flyingchickens/Projects/FlexLoop
    git add flexloop-server
    git diff --cached --stat
    ```

    Expected: `flexloop-server | 2 +-`.

- [ ] **Step 5.5.2:** Commit the pointer bump:

    ```bash
    git commit -m "$(cat <<'EOF'
    chore: bump flexloop-server for codex oauth provider

    flexloop-server → <new-hash>: adds openai-codex as a new LLM
    provider that authenticates via ~/.codex/auth.json (ChatGPT
    OAuth). Read-only consumer, free-rides on OpenClaw's refreshes.
    Adds the Codex status panel to the admin Config page and a
    Codex session card to the admin Health page. Deploy path now
    runs FlexLoop as the ubuntu user to share /home/ubuntu/.codex/
    with OpenClaw natively.

    Test count: 502 → ~567. Plan + spec under
    docs/superpowers/plans/2026-04-11-codex-oauth-provider.md and
    docs/superpowers/specs/2026-04-11-codex-oauth-provider-design.md.

    Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
    EOF
    )"
    ```

    Parent has no remote, so there's nothing to push.

## Chunk 5 verification gate

- [ ] **flexloop-server tip has the expected commits:**

    ```bash
    git -C flexloop-server log --oneline -20
    ```

    Expected: the 19 new commits from chunks 1-5 sitting on top of `bd8b755`.

- [ ] **flexloop-server `main` points at the merge commit:**

    ```bash
    git -C flexloop-server status
    ```

    Expected: "On branch main", clean working tree.

- [ ] **parent submodule pointer matches:**

    ```bash
    git -C /Users/flyingchickens/Projects/FlexLoop ls-files --stage flexloop-server
    ```

    Expected: the gitlink hash matches flexloop-server's HEAD.

- [ ] **Full test suite green one more time** (yes, run it again after
    the merge — merges can surprise):

    ```bash
    cd flexloop-server && ./.venv/bin/python -m pytest 2>&1 | tail -5
    ```

    Expected: ~567 passing.

If all four gates pass, the feature is landed. Ready to hand off to
the operator for VPS deployment via the updated `deploy/agent-runbook.md`.

---

## Rollback plan

If anything goes sideways during or after the merge:

1. **Pre-merge rollback:** `git branch -d feat/codex-oauth-provider` on
   flexloop-server, or reset the worktree. Plan + spec stay committed
   as reference.
2. **Post-merge rollback:** `git -C flexloop-server revert <merge-commit>`
   then bump the parent submodule. Safer than `reset --hard` because
   it preserves history for post-mortem.
3. **Runtime rollback (if deployed and broken):** operator flips
   `ai_provider` back to `openai` (or their prior provider) via the
   Config page, enters an API key if needed, saves. Zero downtime.
   The new DB columns remain but are unused by the non-Codex code path.

