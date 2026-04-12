# Codex OAuth Provider for FlexLoop — Design

**Date:** 2026-04-11
**Status:** Draft (pending reviewer + user approval)
**Author:** Brainstormed with Claude (Opus 4.6)

## 1. Context

FlexLoop's backend currently authenticates to the AI provider using a
classic API key + base URL pair (`AI_API_KEY`, `AI_BASE_URL`,
`AI_PROVIDER ∈ {openai, openai-compatible, anthropic, ollama}`). This
works but has two operational problems for the planned VPS deployment:

1. The operator wants to use their ChatGPT Plus/Pro subscription quota
   instead of a metered API key, and the OpenAI Codex CLI's ChatGPT
   OAuth flow (`codex login`) is the official supported path for that.
2. OpenClaw — an LLM CLI tool the operator already runs on the VPS —
   already authenticates via Codex OAuth and keeps the token fresh in
   `~/.codex/auth.json`. FlexLoop should be able to share the same
   Codex OAuth profile without any extra configuration or a second
   login flow.

The operator also wants to be able to change the AI model (Codex family:
`gpt-5.1-codex-max`, `gpt-5.1-codex-mini`, etc.) and the reasoning
effort (`none` / `minimal` / `low` / `medium` / `high`) at runtime
through the admin Config page, without redeploys.

This spec adds a new LLM provider `openai-codex` to FlexLoop that
satisfies all three requirements: free-ride on OpenClaw's Codex OAuth
credentials, expose runtime model + reasoning knobs through the admin
UI, and coexist with the existing providers so the operator can switch
back to an API key flow in seconds if anything goes wrong.

## 2. Goals

- **Read-only consumer of `~/.codex/auth.json`.** FlexLoop never writes
  to the file, never calls OpenAI's token refresh endpoint, and never
  interacts with the OAuth PKCE flow. It reads the current access
  token fresh on every request.
- **Shared Codex profile with OpenClaw.** Both FlexLoop and OpenClaw
  run as the same Linux user (`ubuntu`) on the VPS and read from the
  same `~/.codex/auth.json`. Whichever tool was used most recently has
  already refreshed the token; the other one benefits automatically.
- **Runtime model + reasoning configurability.** The admin Config page
  exposes `ai_model` (free-text), `ai_reasoning_effort` (dropdown), and
  `codex_auth_file` (path input, default `~/.codex/auth.json`) fields
  when the `openai-codex` provider is selected.
- **Add-alongside, not replace.** Existing `openai` / `openai-compatible`
  / `anthropic` / `ollama` adapters stay exactly as they are. The
  operator can switch providers at runtime through the Config page. If
  Codex OAuth breaks, falling back to an API key is a 30-second UI
  flip, not a redeploy.
- **Visible health and session freshness.** The admin Health page gains
  a "Codex session" card (visible only when provider is `openai-codex`)
  showing whether `auth.json` is present and parseable, the current
  `auth_mode`, `last_refresh` age with color coding, and the decoded
  account email from the `id_token` JWT. The operator sees problems
  before the iOS app does.

## 3. Non-Goals

Deliberately excluded from this design to keep scope tight and avoid
duplicating work OpenClaw / the Codex CLI already do:

- **No OAuth flow in FlexLoop.** No PKCE, no callback handler, no
  `codex login` equivalent. Login happens out-of-band via
  `openclaw auth login --provider openai-codex` or `codex login`.
- **No token refresh by FlexLoop.** Zero writes to `auth.json`. No
  calls to OpenAI's token refresh endpoint. Refresh is the Codex CLI's
  / OpenClaw's job.
- **No fallback provider chain.** When `ai_provider = "openai-codex"`
  and the session is broken, AI calls fail with a clear error. The
  system does not silently fall back to the `openai` adapter with a
  leftover API key. The operator switches providers manually.
- **No parsing of OpenClaw's `auth-profiles.json`.** OpenClaw stores
  credentials in its own file when not in "reuse Codex" mode;
  FlexLoop does not read it. We only read `~/.codex/auth.json`.
- **No iOS app changes.** Zero new error codes, zero new response
  shapes, zero new endpoints. The feature is invisible to
  `flexloop-ios`.
- **No Dockerfile update.** The existing `Dockerfile` is already
  noted as stale in `deploy/README.md`; fixing it is a separate task.
- **No multi-account / account-switching UI.** One Codex profile per
  FlexLoop deployment, matching the single-operator assumption of
  the admin dashboard v1.
- **No `reasoning.effort` on other providers.** The new
  `ai_reasoning_effort` field is read only by `OpenAICodexAdapter`.
  Wiring it into the existing `OpenAIAdapter` (for API-key-authed
  o1 / o3 / gpt-5 calls) is a future enhancement out of scope here.

## 4. Architecture

### 4.1 Where the new code lives

The new adapter is a normal subclass of the existing `LLMAdapter`
hierarchy — same file layout, same factory dispatch, same interface.

```
flexloop-server/src/flexloop/ai/
├── base.py                    # LLMAdapter ABC (unchanged)
├── factory.py                 # create_adapter() — extended with one branch
├── openai_adapter.py          # OpenAIAdapter (unchanged)
├── openai_codex_adapter.py    # NEW: OpenAICodexAdapter(OpenAIAdapter)
├── codex_auth.py              # NEW: CodexAuthReader helper
├── anthropic_adapter.py       # (unchanged)
└── ollama_adapter.py          # (unchanged)
```

### 4.2 Request flow

```
iOS app
   │
   ▼
POST /api/ai/... (existing router)
   │
   │ reads settings.ai_provider = "openai-codex"
   │       settings.ai_model = "gpt-5.1-codex-max"
   │       settings.codex_auth_file = "~/.codex/auth.json"
   │       settings.ai_reasoning_effort = "medium"
   ▼
create_adapter("openai-codex", ...) ──▶ OpenAICodexAdapter
                                              │
                                              │ adapter.generate(...)
                                              ▼
                        CodexAuthReader(path).read_access_token()
                                              │
                                              │ reads /home/ubuntu/.codex/auth.json
                                              │ parses JSON (with retry-on-parse-error)
                                              │ validates auth_mode=="chatgpt"
                                              │ extracts tokens.access_token
                                              ▼
                        fresh AsyncOpenAI(api_key=<token>)
                                              │
                                              ▼
                        client.chat.completions.create(
                            model=..., messages=[...],
                            reasoning_effort="medium"  ← top-level string, iff ≠ "none"
                        )
                                              │   (fallback path:
                                              │    client.responses.create(
                                              │      model=..., input=..., instructions=...,
                                              │      reasoning={"effort": "medium"}  ← nested object
                                              │    ))
                                              ▼
                        LLMResponse ──▶ iOS app
```

**Key property:** `auth.json` is re-read on every request. No in-memory
token caching beyond a request's lifetime. This is what makes the
read-only consumer model work correctly — FlexLoop always picks up
whatever OpenClaw last wrote to the file, without any coordination.

**Two different reasoning parameter shapes.** The OpenAI Python SDK
exposes reasoning effort in two different places depending on which
API is being called:
- `chat.completions.create` accepts `reasoning_effort="medium"` as a
  top-level string parameter.
- `responses.create` accepts `reasoning={"effort": "medium"}` as a
  nested object parameter.

The adapter must use the correct shape for each path because it
inherits the existing `OpenAIAdapter` behavior of trying Chat
Completions first and falling back to the Responses API whenever the
Chat Completions call raises any exception (the existing
`except Exception:` catch in `openai_adapter.py` is deliberately
broad — it was added as a defensive workaround for OpenAI-compatible
proxies that strip response content). See §5.1 for how the Codex
adapter selectively opts specific exceptions out of this fallback via
`_RERAISE_EXCEPTIONS`.

### 4.3 Concurrency with OpenClaw

The refresh token in `auth.json` is single-use (confirmed by
[openai/codex#9634](https://github.com/openai/codex/issues/9634)), so
whichever process calls the OpenAI token endpoint first invalidates
the refresh token for any other process holding the old value. This
is the race that [openclaw#57399](https://github.com/openclaw/openclaw/issues/57399)
and the community Codex-auth plugins repeatedly hit.

FlexLoop avoids the race entirely by **never calling the token
endpoint**. OpenClaw is the sole refresher. When OpenClaw refreshes:

1. OpenClaw detects `last_refresh > ~8 days` old before its own API call.
2. OpenClaw hits OpenAI's token endpoint with the current `refresh_token`.
3. OpenClaw receives new `access_token` + new `refresh_token` +
   new `last_refresh`.
4. OpenClaw writes the updated tokens back to
   `/home/ubuntu/.codex/auth.json`. **The exact write strategy
   (atomic rename vs. in-place truncation) is not verified by this
   spec**, and the design does not depend on either pattern.
5. OpenClaw continues its own request using the new token.

FlexLoop is not aware this happened. Its next `CodexAuthReader` call
picks up the new file. In-flight FlexLoop requests complete fine on
whatever access token they already pulled — access tokens are not
invalidated on refresh, only the refresh token is.

**Torn-read robustness.** We do not rely on any specific OpenClaw
write strategy to guarantee read safety. Instead, the
`CodexAuthReader` is robust to a possibly-torn read:

- On `json.JSONDecodeError`, retry the read up to 2 more times with
  a 5-millisecond sleep between attempts.
- After 3 failed attempts, give up and raise `CodexAuthMalformed`.

Three fast reads cover any realistic sub-second write window. If all
three still see unparseable content, the file really is broken and
the operator needs to intervene. No file locking is required on
either side, and no assumption is made about OpenClaw's write
semantics.

### 4.4 User / filesystem permissions

Both FlexLoop (systemd-managed uvicorn) and OpenClaw run as the Linux
user `ubuntu` on the VPS. This means `~/.codex/auth.json` resolves to
the same `/home/ubuntu/.codex/auth.json` path for both, and both have
native read permission without ACL plumbing.

This is a deliberate deviation from the current `deploy/flexloop.service`
systemd unit, which creates and runs a dedicated `flexloop` system
user. The tradeoff: running as `ubuntu` gives FlexLoop access to the
entire `ubuntu` home directory, which is a small security downgrade
from a dedicated service user. On a single-operator VPS, the benefit
(zero permission plumbing, one file both tools see) outweighs the
cost (lost isolation that doesn't actually stop the most valuable
credential — `auth.json` itself — from being compromised if the
service is compromised).

### 4.5 Admin Config + Health surface

- **Config page:** When the user picks `openai-codex` as the provider,
  `ai_api_key` and `ai_base_url` inputs are hidden (they're meaningless
  for this provider). New fields appear: `codex_auth_file` (path,
  default `~/.codex/auth.json`) and `ai_reasoning_effort` (dropdown).
  A read-only `CodexStatusPanel` component renders below the provider
  select, showing file existence, auth_mode, `last_refresh` age with
  color, and account email.
- **Health page:** The existing `ai_provider` health card gains a
  "Codex session" sub-card (rendered only when provider is
  `openai-codex`) that reuses the `CodexStatusPanel` component for
  consistency.

## 5. Components

### 5.1 Backend — new files

**`flexloop-server/src/flexloop/ai/codex_auth.py`**

Single-responsibility helper module. Exports:

```python
class CodexAuthMissing(Exception): ...      # file not found or unreadable
class CodexAuthMalformed(Exception): ...    # unparseable or missing required fields
class CodexAuthWrongMode(Exception): ...    # auth_mode != "chatgpt"

@dataclass(frozen=True)
class CodexAuthSnapshot:
    # Always populated
    status: str                    # "healthy" | "degraded_yellow" | "degraded_red"
                                   # | "unconfigured" | "down"
    file_exists: bool
    file_path: str                 # resolved absolute path (post-expanduser)

    # Populated only when file_exists and parse succeeded
    auth_mode: str | None = None          # "chatgpt" | "api_key" | None
    last_refresh: datetime | None = None
    days_since_refresh: float | None = None
    account_email: str | None = None      # decoded from id_token JWT, unverified

    # Populated only when status is unconfigured / down / degraded due to error
    error: str | None = None              # human-readable summary of what went wrong
    error_code: str | None = None         # machine-readable: "missing" | "permission"
                                          # | "malformed" | "wrong_mode" | "stale"

class CodexAuthReader:
    def __init__(self, path: str) -> None: ...
    def read_access_token(self) -> str: ...
    def snapshot(self) -> CodexAuthSnapshot: ...
```

Design notes:
- The constructor takes a raw path. `os.path.expanduser` is applied
  inside so callers can pass `"~/.codex/auth.json"` or an absolute
  path interchangeably.
- `read_access_token()` is the fast path used by the adapter on every
  request. It raises `CodexAuthMissing` / `CodexAuthMalformed` /
  `CodexAuthWrongMode` on failure. Parse errors (`json.JSONDecodeError`)
  trigger up to 2 retries with 5ms sleep between attempts before
  giving up and raising `CodexAuthMalformed`.
- `snapshot()` is the slow path used by the Config status panel and
  the Health check. **It never raises** — every failure mode is
  encoded into the `status` + `error` + `error_code` fields. This
  gives the UI and the Health check a single, consistent shape to
  render regardless of what went wrong. Internally it calls
  `read_access_token()` and catches the three exception types,
  converting them into specific `error_code` values:
  - `CodexAuthMissing` → `error_code="missing"` or `"permission"` (depending on `PermissionError` in the chain) → `status="unconfigured"`
  - `CodexAuthMalformed` → `error_code="malformed"` → `status="down"`
  - `CodexAuthWrongMode` → `error_code="wrong_mode"` → `status="down"`
  - `last_refresh >= 9 days old` → `error_code="stale"` → `status="degraded_red"`
  - `5 days <= last_refresh < 9 days` → no `error_code`, `status="degraded_yellow"`
  - `last_refresh < 5 days` → `status="healthy"`
- Email decoding is JWT parsing only, no signature verification. We
  split on `.`, base64-url-decode the payload (with padding correction
  for URL-safe encoding), `json.loads`, and read the `email` claim.
  Failures here silently degrade to `account_email = None` (the
  snapshot still succeeds and `status` is unaffected).

**`flexloop-server/src/flexloop/ai/openai_codex_adapter.py`**

```python
class OpenAICodexAdapter(OpenAIAdapter):
    def __init__(
        self,
        model: str,
        auth_file: str,
        reasoning_effort: str = "medium",
        **kwargs,
    ) -> None: ...
```

Subclasses `OpenAIAdapter` but **requires a small targeted refactor
of the base class** to cleanly extend, because `OpenAIAdapter`
currently holds `self.client = AsyncOpenAI(api_key=api_key)` as a
persistent instance attribute that every method (`generate`, `chat`,
`stream_generate`, `tool_use`, `_stream_chat_completion`) references
directly. A naive subclass cannot rotate the client per-request
without either overriding every method (heavy duplication) or mutating
`self.client` mid-call (unsafe under concurrent requests).

**Base-class refactor** (small, mechanical, preserves all existing
behavior):

1. Rename `self.client` → `self._client` (internal).
2. Add a class attribute and three hook methods to `OpenAIAdapter`
   with defaults that preserve today's behavior:

    ```python
    # Class-level attribute: exception types that must NOT be caught
    # by the Chat Completions → Responses API fallback. Default is
    # empty — existing behavior (swallow everything and try both
    # endpoints) is preserved. Subclasses can list exceptions that
    # should bypass the fallback and raise immediately.
    _RERAISE_EXCEPTIONS: tuple[type[BaseException], ...] = ()

    def _get_client(self) -> AsyncOpenAI:
        """Return the OpenAI client to use for this request.

        Default: the persistent client built in __init__. Subclasses
        may override to return a fresh client per request.
        """
        return self._client

    def _chat_extra_kwargs(self) -> dict:
        """Return extra kwargs to merge into chat.completions.create().

        Default: empty dict. Subclasses may override to inject
        provider-specific parameters like reasoning_effort.
        """
        return {}

    def _responses_extra_kwargs(self) -> dict:
        """Return extra kwargs to merge into responses.create().

        Default: empty dict. Subclasses may override to inject
        provider-specific parameters like a reasoning object.
        """
        return {}
    ```

3. Replace every `self.client.*` call in `OpenAIAdapter` methods
   (`generate`, `chat`, `stream_generate`, `tool_use`,
   `_stream_chat_completion`) with `client = self._get_client()` at
   the top of the method plus `client.*` usage. Merge the appropriate
   `_chat_extra_kwargs()` or `_responses_extra_kwargs()` dict into the
   request kwargs.
4. Modify the `except Exception as e:` fallback blocks in both
   `generate` and `chat` (the two methods that try Chat Completions
   first and fall back to the Responses API) so they re-raise
   immediately when the caught exception is an instance of any type
   in `self._RERAISE_EXCEPTIONS`:

    ```python
    async def generate(self, ...):
        client = self._get_client()
        chat_kwargs = self._chat_extra_kwargs()
        try:
            return await self._stream_chat_completion(
                messages, temperature, max_tokens, **chat_kwargs
            )
        except self._RERAISE_EXCEPTIONS:
            raise  # caller asked for this to bypass the fallback
        except Exception as e:
            logger.warning(f"Chat Completions API failed: {e}. Trying Responses API.")
            responses_kwargs = self._responses_extra_kwargs()
            try:
                response = await client.responses.create(
                    model=self.model, instructions=system_prompt,
                    input=user_prompt, temperature=temperature,
                    max_output_tokens=max_tokens, **responses_kwargs,
                )
                return self._parse_response(response)
            except self._RERAISE_EXCEPTIONS:
                raise
            except Exception as e2:
                logger.error(f"Both API formats failed. Chat: {e}, Responses: {e2}")
                raise e2
    ```

   Because the default `_RERAISE_EXCEPTIONS = ()`, the existing
   `OpenAIAdapter` continues to catch and fall back on every
   exception exactly as it does today. The refactor is
   behavior-preserving for the base class.

This refactor is covered by the existing `OpenAIAdapter` tests
(unchanged) as a guard against regression, plus the new regression
tests listed in §8.2b.

**`_RERAISE_EXCEPTIONS` is scoped to `generate` and `chat` only**,
not to `stream_generate` or `tool_use`. Rationale, verified against
`openai_adapter.py`:

- **`tool_use`** has no Chat-Completions → Responses-API fallback at
  all. It calls `client.chat.completions.create` directly (lines
  274-281 in `openai_adapter.py`) with no outer `try/except`. Any
  exception (auth or otherwise) already propagates to the caller
  naturally — no change needed.
- **`stream_generate`** intentionally catches all exceptions and
  yields them as `StreamEvent(type="error", ...)` events followed
  by a terminal `done` event (lines 189-192). This is the correct
  UX for the admin AI Playground, which is the only caller of
  `stream_generate` and which renders the stream into a UI where
  an error event produces an inline "error" message. Raising a
  `CodexAuthMissing` exception mid-stream would break streaming
  semantics (FastAPI cannot send an HTTP error mid-response after
  headers are flushed), so the design deliberately keeps the
  existing "catch-and-yield" behavior for `stream_generate`. A
  Codex auth error in the Playground therefore appears as an
  error event with the exception message, exactly like any other
  adapter failure.
- **`generate` and `chat`** are the only methods that have the
  problematic Chat-Completions → Responses-API fallback, and they're
  the only methods iOS-facing routers call directly (via
  `coach.adapter.generate()` and friends). These are the methods
  where "raise immediately on auth failure" matters, because
  otherwise an expired Codex session causes two log-noisy failed
  API attempts per request instead of one clean raise.

**Subclass implementation** (`OpenAICodexAdapter`):

1. Sets the class attribute
   `_RERAISE_EXCEPTIONS = (CodexAuthMissing, CodexAuthMalformed, CodexAuthWrongMode, openai.AuthenticationError)`.
   This makes `CodexAuth*` exceptions and 401 responses bypass the
   Chat Completions → Responses API fallback. The adapter raises
   immediately on auth failures instead of trying the Responses
   endpoint a second time (which would hit the same failure).
2. `__init__` stores `self._auth_file = auth_file`,
   `self._reasoning_effort = reasoning_effort`. Calls
   `super().__init__(model, api_key="", base_url="")` with an empty
   placeholder so the base's `_client` construction doesn't crash —
   we'll override `_get_client()` to never use it.
3. `_get_client()` override:

    ```python
    def _get_client(self) -> AsyncOpenAI:
        token = CodexAuthReader(self._auth_file).read_access_token()
        return AsyncOpenAI(api_key=token)
    ```

   Called by every public method at the top of each call, and also
   inside `_stream_chat_completion`. Because `generate` / `chat`
   currently delegate to `_stream_chat_completion`, the Chat
   Completions path can invoke `_get_client()` twice per request
   — that's fine (both invocations produce equivalent fresh
   clients). Per-request client construction is ~1ms overhead,
   negligible vs. model latency. OpenAI's SDK sends whatever value
   is passed as `api_key` in the `Authorization: Bearer` header
   without caring whether it's a traditional API key or an OAuth
   token, so this is a clean reuse.
4. `_chat_extra_kwargs()` override:

    ```python
    def _chat_extra_kwargs(self) -> dict:
        if self._reasoning_effort == "none":
            return {}
        return {"reasoning_effort": self._reasoning_effort}
    ```

5. `_responses_extra_kwargs()` override:

    ```python
    def _responses_extra_kwargs(self) -> dict:
        if self._reasoning_effort == "none":
            return {}
        return {"reasoning": {"effort": self._reasoning_effort}}
    ```

Note the **shape difference** — Chat Completions wants
`reasoning_effort="..."` (top-level string), Responses API wants
`reasoning={"effort": "..."}` (nested object). Verified against the
installed OpenAI Python SDK source during spec review (2026-04-11).

`CodexAuthMissing` / `CodexAuthMalformed` / `CodexAuthWrongMode` raised
from inside `_get_client()` propagate up through the adapter method
call and out of the router. The iOS-facing router currently does not
wrap adapter exceptions (verified in
`flexloop-server/src/flexloop/routers/ai.py`), so they surface as
FastAPI 500s with the exception message in the body — see §7 for the
full discussion of the existing error surface.

**Alembic migration**

One migration adds two columns to `app_settings`:

- `codex_auth_file` TEXT NOT NULL DEFAULT `'~/.codex/auth.json'`
- `ai_reasoning_effort` TEXT NOT NULL DEFAULT `'medium'`

Follows the `_table_exists` / `_column_exists` guard pattern per
`feedback_alembic_migrations.md` (init_db runs `create_all` before
`upgrade`, so migrations must be idempotent on re-runs).

### 5.2 Backend — modified files

**`flexloop-server/src/flexloop/ai/factory.py`**

One new branch in `create_adapter`:

```python
elif provider == "openai-codex":
    return OpenAICodexAdapter(
        model=model,
        auth_file=kwargs.pop("codex_auth_file", "~/.codex/auth.json"),
        reasoning_effort=kwargs.pop("reasoning_effort", "medium"),
    )
```

**Every `create_adapter(...)` call site must be updated** to pass
the two new kwargs through. The caller inventory (verified by grep
during spec review):

1. `src/flexloop/routers/ai.py::get_ai_coach()` — iOS-facing
   generate/chat calls
2. `src/flexloop/routers/ai.py::get_plan_refiner()` — iOS-facing
   plan refinement tool-use calls
3. `src/flexloop/admin/routers/playground.py::run_playground()` —
   admin AI Playground streaming endpoint (already has
   per-request override kwargs; needs new `codex_auth_file` /
   `reasoning_effort` overrides added to its `PlaygroundRunRequest`
   schema so operators can test alternate values without persisting)
4. `src/flexloop/admin/routers/triggers.py::<test-ai trigger>`
   (the phase 5c "test AI connection" trigger) — must pass the
   new kwargs so that the trigger reflects the actual configured
   Codex session
5. `src/flexloop/admin/routers/config.py::test_connection()` —
   the Config page Test Connection endpoint; already has override
   fields for API-key-style providers, needs new `codex_auth_file`
   and `reasoning_effort` override fields on its
   `TestConnectionRequest` schema

All five call sites must read the new fields off `settings` (or the
request override) and pass them through to `create_adapter`. This is
mechanical boilerplate but every site must be touched — skipping any
one means that code path would silently ignore the Codex settings.

**`flexloop-server/src/flexloop/config.py`**

Adds two new fields to the `Settings` class:

```python
codex_auth_file: str = "~/.codex/auth.json"
ai_reasoning_effort: str = "medium"
```

Both added to `_DB_BACKED_FIELDS` so they hot-reload via
`refresh_settings_from_db` after a Config page save.

**`flexloop-server/src/flexloop/models/app_settings.py`**

Matching mapped columns on the ORM model.

**`flexloop-server/src/flexloop/admin/routers/config.py`**

- `AppSettingsResponse`: adds `codex_auth_file: str`,
  `ai_reasoning_effort: str`. No masking for either (they aren't
  secrets — path and enum value).
- `AppSettingsUpdate`: adds the same two fields as optional.
- `TestConnectionRequest`: adds optional `codex_auth_file` and
  `reasoning_effort` override fields.
- `_masked_dict`: extended to include the two new fields in the audit
  log snapshot.
- **New endpoint:** `GET /api/admin/config/codex-status` returns a
  `CodexAuthSnapshot`-shaped response (file_exists, auth_mode,
  last_refresh, days_since_refresh, account_email, status). Uncached.
  Requires admin auth. Always reads the file fresh — the Recheck
  button on the Config panel and the Health page's explicit refresh
  both hit this endpoint.

**`flexloop-server/src/flexloop/admin/routers/health.py`**

- `_check_ai_provider` gains a branch for `provider == "openai-codex"`:
  call `CodexAuthReader(settings.codex_auth_file).snapshot()` (which
  never raises), and propagate the snapshot's `status` field plus
  `file_exists`, `auth_mode`, `last_refresh`, `days_since_refresh`,
  `account_email`, and `error` into the health response dict. The
  snapshot's `status` field directly maps into the health row
  color, and is computed by the reader using these thresholds:
  - `file_exists == False` → `unconfigured` (red) with `error` set
  - `CodexAuthMalformed` / `CodexAuthWrongMode` (converted internally
    to status codes) → `down` (red) with `error` set
  - `days_since_refresh >= 9` → `degraded_red`
  - `5 <= days_since_refresh < 9` → `degraded_yellow`
  - `days_since_refresh < 5` → `healthy`

  **Boundary rules are inclusive-left / exclusive-right so exactly-9-days
  is red, exactly-5-days is yellow, and there is no value that falls
  into two buckets.**
- The health check path uses `snapshot()` (never raises), not
  `read_access_token()` (raises), so the Health endpoint never
  returns a 500 just because auth.json is broken — it surfaces the
  specific status.
- Existing 60-second cache retained for the dashboard aggregate. The
  `/codex-status` endpoint is separately uncached.

### 5.3 Frontend — new files

**`flexloop-server/admin-ui/src/components/config/CodexStatusPanel.tsx`**

Small card component. ~80 LOC. Fetches `GET /api/admin/config/codex-status`
on mount and on "Recheck" click. Renders:

- Status dot (green/yellow/red) matching `status`
- File path (from config)
- "File exists: ✓/✗"
- `auth_mode` badge ("chatgpt" green, "api_key" yellow, missing red)
- `last_refresh` timestamp + "N days ago" + color
- Account email (or "—" if unavailable)
- Recheck button

### 5.4 Frontend — modified files

**`flexloop-server/admin-ui/src/components/forms/ConfigForm.tsx`**

- Add `<SelectItem value="openai-codex">OpenAI Codex (OAuth)</SelectItem>`
  to the provider dropdown.
- When `watch("ai_provider") === "openai-codex"`:
  - Hide `ai_api_key` and `ai_base_url` inputs.
  - Show new `codex_auth_file` text input.
  - Show new `ai_reasoning_effort` Select dropdown with values
    `none` / `minimal` / `low` / `medium` / `high`.
  - Render `<CodexStatusPanel />` below the provider select.
- `ai_model` input gets a provider-aware placeholder
  (`"e.g. gpt-5.1-codex-max"` when Codex is selected) but stays as
  free text for all providers.
- Zod schema: `codex_auth_file: z.string()`,
  `ai_reasoning_effort: z.enum(["none", "minimal", "low", "medium", "high"])`.

**`flexloop-server/admin-ui/src/pages/HealthPage.tsx`**

The existing AI provider health card gains a nested "Codex session"
section that reuses `<CodexStatusPanel />` when `provider === "openai-codex"`.
No change to other providers' rendering.

### 5.5 Deploy path — modified files

- **`flexloop-server/deploy/flexloop.service`** — `User=flexloop` →
  `User=ubuntu`, `Group=flexloop` → `Group=ubuntu`. Keep everything else.
- **`flexloop-server/deploy/README.md`** — step 2 changes from "create
  flexloop system user" to "ensure /opt/flexloop exists and is owned
  by ubuntu." Add a new post-first-boot mini-step pointing at the
  Config page for switching to the `openai-codex` provider.
- **`flexloop-server/deploy/agent-runbook.md`** — same `User=ubuntu`
  change; pre-flight gains a soft-check for
  `/home/ubuntu/.codex/auth.json` existence.

## 6. Data flow

### 6.1 iOS app makes an AI request

See the sequence diagram in §4.2. End-to-end: iOS → FastAPI router →
`create_adapter` → `OpenAICodexAdapter.generate` → `CodexAuthReader` →
fresh `AsyncOpenAI` → `chat.completions.create` → `LLMResponse` → iOS.

### 6.2 OpenClaw refreshes the token out-of-band

OpenClaw detects stale `last_refresh`, calls OpenAI's token endpoint,
receives new tokens, writes them back to `auth.json` (write strategy
unverified — see §4.3). FlexLoop is unaware; its next
`CodexAuthReader` read picks up the new file via the 3-attempt
`JSONDecodeError` retry loop if the read happens mid-write. In-flight
FlexLoop requests complete on the old access token (still valid —
only the refresh token was consumed).

### 6.3 Admin reads config (`GET /api/admin/config`)

Standard existing flow. The response grows two new fields
(`codex_auth_file`, `ai_reasoning_effort`), neither masked. The
existing `ai_api_key` masking logic is untouched — for the
`openai-codex` provider, the key value is empty, so the mask returns
empty, and the form hides the field anyway.

### 6.4 Admin reads Codex status (`GET /api/admin/config/codex-status`)

```
CodexStatusPanel mount or Recheck click
         │
         ▼
  GET /api/admin/config/codex-status
         │
         ▼
  routers/config.py::get_codex_status()
         │
         │ CodexAuthReader(settings.codex_auth_file).snapshot()
         │
         ▼
  CodexStatusResponse JSON → panel renders
```

Dedicated endpoint rather than folding into `GET /config` because:

- Status is a probe result, not persisted config.
- The Recheck button wants a fresh read on demand.
- The Health page reads the same snapshot independently.
- Separate caching: `/config` can be cached, status is always fresh.

Both UI consumers (ConfigForm status panel, HealthPage card) hit the
same backend endpoint. Single source of truth.

### 6.5 Admin PUT `/api/admin/config`

Unchanged flow: partial update via `model_dump(exclude_unset=True)`,
audit log via `_masked_dict`, `refresh_settings_from_db(db)` hot-reload
of the in-memory singleton, response with the new values. The new
fields participate in all three steps without any special handling.

## 7. Error handling

### 7.1 The existing iOS-facing error surface is unchanged

**Important context before the failure matrix:** the existing
iOS-facing AI router at
`flexloop-server/src/flexloop/routers/ai.py` does **not** wrap adapter
calls in `try/except`. Any exception raised from a `coach.adapter.*`
call propagates uncaught and FastAPI converts it to a generic
`HTTP 500 Internal Server Error` with the exception message in the
response body. There are no structured error codes like
`AI_UNAVAILABLE` / `AI_UPSTREAM_ERROR` / `AI_MODEL_ERROR` in the
current code — they do not exist.

This spec **does not add** structured error mapping to the iOS-facing
router. Adding that mapping would be a cross-cutting refactor of the
existing AI error surface, touching every adapter call site, and is
out of scope for this feature. Instead, every `CodexAuth*` exception
propagates up exactly like any other adapter exception does today,
and the iOS app sees the same "AI call failed" experience it already
sees when the configured `openai` or `anthropic` provider fails —
just with a different underlying cause in the error body.

If richer user-facing error handling on the iOS side is desired,
that's a separate spec. This feature's job is to make Codex OAuth
work; it is not to rearchitect FlexLoop's AI error surface.

### 7.2 Failure matrix

"iOS-app response" below means: the response the iOS app actually
sees today, given the unchanged router layer.

| Failure | Raised by | iOS-app response | Admin Health card | Config status panel | Recovery |
|---|---|---|---|---|---|
| `auth.json` missing | `CodexAuthMissing` at request time | `HTTP 500` with exception message | `unconfigured` / red / "File not found" + `error_code="missing"` | Red ✗ + path + re-auth hint | Run `codex login` or `openclaw auth login --provider openai-codex` |
| Permission denied | `CodexAuthMissing` (chained `PermissionError`) | `HTTP 500` | `unconfigured` / red / "Permission denied" + `error_code="permission"` | Red ✗ + specific error | Fix perms |
| Unparseable JSON (3 retry failures) | `CodexAuthMalformed` | `HTTP 500` | `down` / red / "auth.json malformed" + `error_code="malformed"` | Red ✗ + parse error | Re-auth (rewrites file) |
| `auth_mode != "chatgpt"` | `CodexAuthWrongMode` | `HTTP 500` | `down` / red / "Wrong auth mode" + `error_code="wrong_mode"` | Red ✗ + "run `codex login` for ChatGPT OAuth" | Re-auth with ChatGPT flow |
| Missing `tokens.access_token` | `CodexAuthMalformed` | `HTTP 500` | `down` / red | Red ✗ | Re-auth |
| Unparseable `id_token` JWT | None (cosmetic) | Normal success | Normal | Panel shows "email: —" but `status` unchanged | Cosmetic only |
| `last_refresh` in [5, 9) days | None from reader | Normal | `degraded_yellow` / "aging — N days since refresh" | Yellow ⚠ + "N days since refresh" | Use openclaw or codex once to refresh |
| `last_refresh` ≥ 9 days | None from reader (snapshot only); likely `401` at request time | `HTTP 500` (at request time) | `degraded_red` / "stale ≥9d" + `error_code="stale"` | Red ✗ | Re-auth |
| 401 from OpenAI (token expired or revoked mid-request) | `openai.AuthenticationError` from the OpenAI SDK | `HTTP 500` with "401" in the body | Unchanged until next cache refresh | Unchanged until next call to `/codex-status` | Re-auth |
| 404 "model not found" | `openai.NotFoundError` | `HTTP 500` with "model not found" | Unchanged (it's a model misconfig, not a session issue) | Unchanged | Fix `ai_model` |
| 429 rate limit | `openai.RateLimitError` | `HTTP 500` with "rate limit" | Unchanged (transient) | Unchanged | Wait |
| 5xx upstream | `openai.APIError` or similar | `HTTP 500` with upstream message | Unchanged (transient) | Unchanged | Wait / retry |
| Network timeout | `asyncio.TimeoutError` from the SDK | `HTTP 500` with "timeout" | Unchanged | Unchanged | Retry |

**Two signal paths diverge intentionally:**

- **Request-path signals** (raised by `read_access_token()` or by the
  OpenAI SDK during a real API call) cause the iOS request to fail
  as `HTTP 500`. The admin operator diagnoses via the Health page and
  the Config status panel.
- **Snapshot-path signals** (observed by `snapshot()` on the admin
  Health / Config status panel endpoints) are folded into the
  `status` field. These never raise, never cause a 500, and are how
  the operator sees problems *before* the iOS app hits them.

The 60-second Health cache means there can be a window where the
Health row is green but a live iOS request fails on a just-expired
token. The operator clicks "Recheck" on the Config status panel
(uncached) to see fresh state; the panel and the Health page will
agree after the next cache miss.

### 7.3 Design principles

- **No automatic retries on the adapter side.** On `CodexAuthMissing`
  or 401, the adapter raises immediately. FlexLoop does not attempt
  "maybe OpenClaw is mid-refresh, wait 2 seconds and re-read"
  heuristics at the adapter level.
- **Retry-on-parse-error is ONLY for torn reads.** The 3-attempt
  retry loop inside `CodexAuthReader` exists specifically to handle
  the very narrow case where a read races a write and sees partial
  content. It does **not** retry on missing file, permission denied,
  wrong auth mode, or any other semantically-meaningful failure.
- **Logging levels:**
  - `CodexAuthMissing` / `Malformed` / `WrongMode` → `WARNING`
  - 401 at request time → `WARNING`
  - 4xx other than 401 → `INFO`
  - 5xx / timeouts / network errors → `ERROR`
- **Health check caching.** The existing 60-second cache on
  `_check_ai_provider` is retained for the dashboard aggregate. The
  new `/api/admin/config/codex-status` endpoint is **uncached** —
  the ConfigPage's Recheck button and the HealthPage's explicit
  refresh both hit uncached data. The two can disagree for up to 60
  seconds after a state change; this is acceptable and matches the
  existing behavior for every other health check.
- **Concurrency.** No file locking on `auth.json` reads. The
  3-attempt retry loop in `read_access_token()` handles torn reads
  without depending on atomic-rename guarantees from the writer.
- **Test Connection.** The existing
  `POST /api/admin/config/test-connection` endpoint "just works"
  once the factory knows about `openai-codex` — it builds the
  adapter, fires a tiny generate, returns the result. Failures
  (including `CodexAuth*` exceptions) surface inline in the UI as
  the existing `status: "error"` response shape.
- **No new iOS error codes.** The feature adds zero iOS-visible
  error symbols. Whatever the iOS app does today on an adapter
  failure (show a generic "AI unavailable" message, probably) is
  what it will do for Codex OAuth failures. If nicer iOS error UX
  is wanted, that's a separate spec.

## 8. Testing strategy

Total new tests: approximately 55–60, bringing the suite from 502 →
~560. The count grew from an initial estimate of ~30 after spec review
added explicit tests for both request parameter shapes, base-class
refactor regressions, boundary cases on freshness thresholds, and the
torn-read retry. Most new tests are small parameterized variants and
contribute modest LOC.

### 8.1 `CodexAuthReader` unit tests

File: `tests/test_codex_auth.py` (new). Uses `tmp_path` fixture to
materialize different `auth.json` variants. Helper:
`make_auth_json(path, **overrides)` writes a default-valid file with
overrides applied.

**`read_access_token()` tests (raises on failure):**
- `test_reader_happy_path_returns_token`
- `test_reader_missing_file_raises` → `CodexAuthMissing`
- `test_reader_permission_denied_raises` → `CodexAuthMissing`
- `test_reader_malformed_json_raises_after_retries` → `CodexAuthMalformed`
  after 3 failed attempts
- `test_reader_torn_read_recovers_on_retry` → first read returns
  partial content, second read returns valid content, reader
  eventually succeeds without raising
- `test_reader_missing_auth_mode_raises` → `CodexAuthMalformed`
- `test_reader_api_key_mode_raises` → `CodexAuthWrongMode`
- `test_reader_missing_tokens_raises` → `CodexAuthMalformed`
- `test_reader_missing_access_token_raises` → `CodexAuthMalformed`
- `test_reader_expanduser_on_tilde_path` with monkeypatched HOME

**`snapshot()` tests (never raises, status field encoded):**
- `test_snapshot_happy_path_healthy` → `status="healthy"`,
  `error is None`, `account_email` populated
- `test_snapshot_missing_file_unconfigured` → `status="unconfigured"`,
  `error_code="missing"`
- `test_snapshot_permission_denied` → `error_code="permission"`
- `test_snapshot_malformed` → `status="down"`, `error_code="malformed"`
- `test_snapshot_wrong_mode` → `status="down"`, `error_code="wrong_mode"`
- `test_snapshot_days_since_refresh_fresh` (`< 5` → healthy)
- `test_snapshot_days_since_refresh_aging` (5 ≤ x < 9 → yellow)
- `test_snapshot_days_since_refresh_exactly_5_days` (boundary: yellow)
- `test_snapshot_days_since_refresh_exactly_9_days` (boundary: red)
- `test_snapshot_days_since_refresh_stale` (≥ 9 → red)
- `test_snapshot_missing_last_refresh` → `days_since_refresh is None`,
  does not crash
- `test_snapshot_tolerates_malformed_id_token` → `account_email is None`,
  rest ok, status unaffected
- `test_snapshot_never_raises_on_any_fixture` — parametrized across
  every fixture variant above, asserts the call always returns
  without raising

### 8.2 `OpenAICodexAdapter` unit tests

File: `tests/test_openai_codex_adapter.py` (new). Uses a fake
`AsyncOpenAI` stub that captures request kwargs so we can assert on
the exact parameter shape sent to each endpoint.

**Token handling:**
- `test_generate_reads_token_from_auth_file`
- `test_generate_rereads_token_per_call` (write A → call → overwrite
  with B → call → second uses B)
- `test_auth_missing_raises_through_generate`
- `test_401_from_client_propagates`
- `test_stream_generate_reads_token_and_streams`

**Chat Completions request shape (top-level `reasoning_effort`):**
- `test_chat_completions_reasoning_effort_medium_top_level` — assert
  captured kwargs contain `"reasoning_effort": "medium"` as a
  top-level field, **not** nested under `"reasoning"`
- `test_chat_completions_reasoning_effort_high_top_level`
- `test_chat_completions_reasoning_effort_none_not_injected` —
  assert `"reasoning_effort"` key is absent from kwargs entirely
- `test_chat_completions_no_nested_reasoning_object` — assert the
  `"reasoning"` key is **never** present on the Chat Completions
  request even when effort is non-none

**Responses API fallback request shape (nested `reasoning.effort`):**
- `test_responses_api_reasoning_effort_medium_nested` — force the
  adapter into the Responses API fallback path (by making the
  Chat Completions mock raise) and assert the fallback call kwargs
  contain `"reasoning": {"effort": "medium"}`, **not** a top-level
  `"reasoning_effort"` string
- `test_responses_api_reasoning_effort_none_not_injected` — assert
  `"reasoning"` key is absent on the Responses path when effort is
  `"none"`
- `test_responses_api_no_top_level_reasoning_effort` — assert the
  top-level `"reasoning_effort"` field is **never** present on the
  Responses API call

### 8.2b Base-class `OpenAIAdapter` refactor regression tests

File: `tests/test_ai_openai_adapter.py` (extend existing or add a
new file). These tests exist to guarantee the `_get_client` /
`_chat_extra_kwargs` / `_responses_extra_kwargs` hook refactor is
behavior-preserving — the existing `OpenAIAdapter` passes all its
tests unchanged, but we also add explicit assertions:

- `test_base_adapter_get_client_returns_persistent_client` — default
  `_get_client()` returns the same `AsyncOpenAI` instance every call
- `test_base_adapter_chat_extra_kwargs_empty_by_default` — default
  hook returns `{}`
- `test_base_adapter_responses_extra_kwargs_empty_by_default` —
  default hook returns `{}`
- `test_base_adapter_chat_completions_no_reasoning_field` — asserts
  that a pure `OpenAIAdapter` call does NOT inject any reasoning
  parameter (proves the refactor didn't accidentally add one)

### 8.3 Factory

File: `tests/test_ai_factory.py` (new or extend existing).

- `test_create_adapter_returns_codex_adapter_for_openai_codex`
- `test_create_adapter_unknown_provider_raises` (existing behavior preserved)

### 8.4 Config router integration

File: `tests/test_admin_config.py` (extend existing).

- `test_get_config_includes_new_fields`
- `test_put_config_updates_codex_fields`
- `test_put_config_switch_provider_to_codex`
- `test_test_connection_codex_happy`
- `test_test_connection_codex_missing_file`
- `test_test_connection_codex_expired_token`
- `test_put_config_audit_log_masks_nothing_for_new_fields`

### 8.5 Codex status endpoint

File: `tests/test_admin_codex_status.py` (new).

- `test_get_codex_status_healthy`
- `test_get_codex_status_aging` (last_refresh=6d)
- `test_get_codex_status_stale` (last_refresh=10d)
- `test_get_codex_status_missing_file`
- `test_get_codex_status_malformed`
- `test_get_codex_status_requires_admin`
- `test_get_codex_status_uncached`

### 8.6 Health endpoint integration

File: `tests/test_admin_health.py` (extend existing).

- `test_health_ai_provider_branch_codex_healthy`
- `test_health_ai_provider_branch_codex_missing`
- `test_health_ai_provider_branch_non_codex_unaffected`
- `test_health_codex_check_cache_respects_60s_ttl`

### 8.7 Migration

File: `tests/test_migration_add_codex_fields.py` (new).

- `test_migration_upgrade_adds_columns`
- `test_migration_downgrade_removes_columns`
- `test_migration_idempotent_on_rerun` (per feedback memory)

### 8.8 Test-only infrastructure

- **`tests/fixtures/auth_json_factory.py`** — `make_auth_json(path, **overrides)`
  helper writing a default-valid `auth.json` with mutation support.
  Used across §8.1, 8.2, 8.4, 8.5, 8.6.
- **Fake `AsyncOpenAI`** — minimal stub matching the SDK surface the
  adapter uses. Lives next to `test_openai_codex_adapter.py`.
- **JWT fixture helper** — produces a minimal unsigned JWT with an
  arbitrary `email` claim for email-display tests. ~10 LOC.

### 8.9 Out of scope for tests

- Real OpenAI API calls (all OpenAI SDK interactions are mocked).
- Real Codex CLI subprocess calls.
- Real OAuth flow.
- Real OpenClaw interactions.
- **Real concurrent writer/reader integration testing** (a dedicated
  filesystem harness spawning a real OpenClaw-like writer during a
  read). The **unit-level torn-read retry test** in §8.1
  (`test_reader_torn_read_recovers_on_retry`) IS required and covered;
  what's out of scope is a full multi-process integration harness.

## 9. Security notes

- **`auth.json` contents are secrets.** The adapter never logs access
  token values, never includes them in error messages surfaced to
  users, never echoes them in audit logs. Only the file *path* goes
  into audit entries, and it's stored plain (it's a path, not a
  credential).
- **Email displayed from unverified JWT.** The `id_token` payload is
  base64-decoded for UI display only. No signature verification. We
  never make authorization decisions based on its contents. Security
  impact: "if the file is tampered with, the UI might show a wrong
  email" — not "trust can be bypassed."
- **Run-as-ubuntu tradeoff.** FlexLoop inherits `ubuntu`'s full
  filesystem access. If FlexLoop has an RCE, the attacker gets
  `ubuntu`'s shell — including SSH keys and other secrets under
  `/home/ubuntu`. Acknowledged tradeoff: (a) single operator,
  (b) an RCE attacker would steal `auth.json` itself regardless of
  user isolation, (c) the dedicated service user alternative adds
  operational complexity (ACLs that can drift) without shrinking
  the highest-value blast radius.
- **File permissions.** The design does **not** mandate `0600` on
  `auth.json`. Codex CLI writes it that way by default and we just
  read whatever's there. If the operator has made it more permissive
  deliberately, that's their call.

## 10. Rollout / migration sequence

1. **Backend migration.** Alembic adds `codex_auth_file` and
   `ai_reasoning_effort` to `app_settings` with safe defaults.
   Existing rows get the defaults. Existing behavior unchanged until
   the operator flips `ai_provider`.
2. **Backend code.** New adapter, factory branch, config + health
   router updates. `ai_provider` defaults still point to `openai`,
   so this is a no-op for any existing deployment.
3. **Frontend.** ConfigForm + CodexStatusPanel + HealthPage card
   updates. Same behavior for any provider other than `openai-codex`.
4. **Deploy.** Operator follows the updated `agent-runbook.md` (with
   `User=ubuntu` baked in). On first boot, everything works exactly
   as today with the `openai` provider. OpenClaw is assumed already
   running on the VPS.
5. **Operator flip.** Operator opens Config page, sets provider to
   `openai-codex`, confirms `CodexStatusPanel` is green, saves. CSRF
   middleware hot-reloads. Next AI request uses Codex OAuth. Zero
   downtime.

**Rollback.** Operator opens the Config page, flips `ai_provider`
back to the previous value, pastes API key into `ai_api_key` if
needed, saves. Service continues on the old provider. No migration
rollback required — the new columns stay in the DB, unused by the
old adapter path.

## 11. Open risks

These are the things the spec reviewer should specifically push on:

1. **`auth.json` schema stability.** OpenAI has not publicly committed
   to a stable schema for this file. Fields could be renamed or
   reshaped in a future Codex CLI release. Mitigation: keep the
   reader narrow (only `auth_mode`, `tokens.access_token`,
   `last_refresh`, `id_token`) and surface schema errors as clear
   `CodexAuthMalformed` messages. Tests include a
   `test_reader_missing_auth_mode_raises` case that will catch any
   field rename during upgrades.
2. **Token format stability.** OpenAI could change how ChatGPT OAuth
   tokens look on the wire. Today's assumption is "opaque string
   suitable as a Bearer header value." Verified during spec review:
   the installed OpenAI Python SDK emits
   `Authorization: Bearer {api_key}` verbatim regardless of whether
   the string is a traditional API key or an OAuth token. If OpenAI
   changes this, the adapter breaks until updated.
3. **`reasoning_effort` parameter shape.** Verified during spec review
   against the installed OpenAI Python SDK source: Chat Completions
   accepts `reasoning_effort="..."` (top-level string) and Responses
   API accepts `reasoning={"effort": "..."}` (nested object). Both
   shapes are now explicitly specified in §4.2 and §5.1, and §12
   acceptance criteria tests verify both paths produce the correct
   request shape. **This was previously listed as an unresolved risk
   and is now closed.**
4. **JWT decode edge cases.** URL-safe base64 with missing padding
   is a well-known gotcha. The `id_token` decode uses
   `base64.urlsafe_b64decode` with explicit padding correction.
   Covered by `test_snapshot_tolerates_malformed_id_token`.
5. **OpenClaw write behavior is not independently verified.** The
   spec deliberately **does not** assume OpenClaw uses
   atomic-rename semantics. Instead, `CodexAuthReader.read_access_token()`
   and `snapshot()` implement a 3-attempt retry loop on
   `json.JSONDecodeError` with a 5ms sleep between attempts to
   survive a torn read window without depending on the writer's
   strategy. If OpenClaw happens to use atomic rename (as Codex CLI
   is believed to do), the retry loop is harmless. If OpenClaw does
   in-place truncation, the retry loop is what keeps us safe. Either
   way the design is robust.
6. **60s health cache vs. uncached status endpoint.** Two code paths
   read `auth.json` — one cached for the dashboard aggregate, one
   uncached for the Config panel and HealthPage refresh. During a
   60-second window, a user might see "green on Health, red on
   Config" if they refreshed the Config page after making a fix but
   the Health aggregate is still stale. Acceptable but worth
   flagging — and matches the behavior of every other existing
   health check.

## 12. Acceptance criteria

The feature is considered complete when:

1. `create_adapter("openai-codex", ...)` returns an
   `OpenAICodexAdapter` instance that successfully completes a
   generate call against a fixture `auth.json`.
2. **Chat Completions path sends `reasoning_effort=<value>` as a
   top-level string.** Test captures the request kwargs sent to the
   mocked `AsyncOpenAI.chat.completions.create` call and asserts
   `kwargs["reasoning_effort"] == "medium"` (or the currently
   configured value), **not** nested under `reasoning`.
3. **Responses API fallback path sends `reasoning={"effort": <value>}`
   as a nested object.** Test captures the request kwargs sent to
   the mocked `AsyncOpenAI.responses.create` call and asserts
   `kwargs["reasoning"] == {"effort": "medium"}`, **not** as a
   top-level string.
4. When `ai_reasoning_effort == "none"`, **neither** parameter is
   injected on either path (absent from the request kwargs entirely).
5. `OpenAIAdapter` (the existing API-key adapter) still passes all
   of its existing tests after the `_get_client` / `_chat_extra_kwargs`
   / `_responses_extra_kwargs` refactor. The refactor is
   behavior-preserving.
6. `CodexAuthReader.read_access_token()` survives a torn read with
   the **exact retry policy specified**: the test writes partial
   content, then full valid content, and verifies that the reader
   retries up to 2 more times (3 attempts total) with a 5ms sleep
   between attempts before succeeding or giving up with
   `CodexAuthMalformed`. Both the retry count and the sleep interval
   are assertable in test (e.g., via a mocked `time.sleep`).
7. `CodexAuthReader.snapshot()` **never raises** under any of the
   fixture failure cases (`missing`, `permission`, `malformed`,
   `wrong_mode`, `stale`). Every failure returns a snapshot with
   `status`, `error_code`, and `error` populated.
8. The admin Config page, when provider is `openai-codex`, hides
   `ai_api_key` and `ai_base_url`, shows `codex_auth_file` and
   `ai_reasoning_effort`, and renders a live `CodexStatusPanel` that
   reflects the current `auth.json` state.
9. The admin Health page shows a Codex session card with
   color-coded `last_refresh` status when provider is `openai-codex`.
   Exactly-9-days is red, exactly-5-days is yellow, no value falls
   into two buckets.
10. `POST /api/admin/config/test-connection` with provider
    `openai-codex` successfully round-trips a tiny prompt and returns
    `status: "ok"` (in tests, via a mocked `AsyncOpenAI`).
11. Alembic migration up and down cleanly; re-upgrade is a no-op on an
    already-migrated database.
12. All ~55–60 new tests pass (the growth from an initial ~30
    estimate reflects spec-review-driven additions for both request
    parameter shapes, boundary cases, torn-read retry, and
    base-class refactor regressions). Existing 502 tests remain
    unaffected.
13. `deploy/flexloop.service` uses `User=ubuntu`, `deploy/README.md`
    and `deploy/agent-runbook.md` match, and a fresh VPS deploy
    following the agent runbook ends with a working `openai-codex`
    provider and a green Codex session indicator on Health.
14. Rollback path verified: flipping provider back to `openai` with a
    valid API key restores the previous behavior without a restart.

## 13. Scope boundary

All changes are confined to:

- `flexloop-server/` — backend code, frontend code, deploy files, tests
- `docs/superpowers/specs/` — this spec

No changes to:

- `flexloop-ios/` — the iOS app is unaffected
- Parent umbrella repo (`FlexLoop/`) — except a routine submodule
  pointer bump after the feature branch merges
- External tools (OpenClaw, Codex CLI) — we consume them, we don't
  modify them

## 14. Total code delta estimate

- **Backend:** ~400 LOC new + ~80 LOC modified (the ~20 extra
  modified LOC is for the `OpenAIAdapter` `_get_client` /
  `_chat_extra_kwargs` / `_responses_extra_kwargs` refactor hooks)
- **Frontend:** ~200 LOC new + ~80 LOC modified
- **Tests:** ~1100 LOC (55–60 tests + shared fixtures)
- **Deploy docs:** ~30 LOC modified

Approximately **~1800 LOC** total. Fits comfortably in a single
worktree + feature-branch flow per the project's branch-strategy
convention.
