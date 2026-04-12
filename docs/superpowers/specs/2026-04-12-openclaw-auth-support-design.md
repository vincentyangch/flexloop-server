# OpenClaw Auth Profile Support — Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Scope:** Teach `CodexAuthReader` to auto-detect and read OpenClaw's
`auth-profiles.json` format alongside the existing Codex CLI `auth.json`
format.

## 1. Problem

FlexLoop's `openai-codex` provider reads OAuth tokens from
`~/.codex/auth.json` (Codex CLI format). On VPS deployments that run
OpenClaw, the OAuth session is stored in a different file:

```
~/.openclaw/agents/main/agent/auth-profiles.json
```

OpenClaw does not write `~/.codex/auth.json`. An operator must
currently maintain a separate Codex CLI login or manually copy tokens
between files. This is fragile and adds operational drift.

## 2. Goal

Support both auth file formats transparently. The operator points
`codex_auth_file` at whichever file exists on their system — the reader
detects the format and extracts the `openai-codex` access token.

No new config fields, no DB migration, no new UI components.

## 3. File formats

### 3.1 Codex CLI (`~/.codex/auth.json`) — existing

```json
{
  "auth_mode": "chatgpt",
  "last_refresh": "2026-04-12T14:23:45.123456+00:00",
  "tokens": {
    "access_token": "eyJ...",
    "refresh_token": "...",
    "id_token": "eyJ..."
  }
}
```

Key fields: `auth_mode == "chatgpt"`, `tokens.access_token`,
`last_refresh` (ISO 8601), email decoded from `tokens.id_token` JWT.

### 3.2 OpenClaw (`auth-profiles.json`) — new

```json
{
  "version": 1,
  "profiles": {
    "openai-codex:default": {
      "type": "oauth",
      "provider": "openai-codex",
      "access_token": "eyJ...",
      "refresh_token": "...",
      "expires_at": 1744483200000,
      "accountId": "user@example.com"
    }
  }
}
```

Key fields: `version` + `profiles` (format marker), profile with
`provider == "openai-codex"`, `access_token`, `expires_at`
(milliseconds since epoch), `accountId`.

## 4. Format detection

After `_load_file_with_retry()` returns a parsed dict:

| Condition | Format | Action |
|-----------|--------|--------|
| Has `version` and `profiles` keys | OpenClaw | Extract first profile where `provider == "openai-codex"` |
| Has `auth_mode` key | Codex CLI | Existing validation path (unchanged) |
| Neither | Unknown | Raise `CodexAuthMalformed` |

Detection happens once per `_load_and_validate()` call, before any
field-level validation.

## 5. OpenClaw profile extraction

From the matched profile object:

| OpenClaw field | Maps to | Notes |
|----------------|---------|-------|
| `access_token` | access token (returned directly) | Same semantics as Codex CLI `tokens.access_token` |
| `expires_at` | freshness input | Milliseconds since epoch. Convert to `datetime`, compute days *until* expiry. Healthy if >5 days out, `degraded_yellow` if 2-5 days, `degraded_red` if <2 days. |
| `accountId` | `account_email` in snapshot | Used as display value directly (no JWT decoding) |
| `type` | mode check | Must be `"oauth"`. Other values raise `CodexAuthWrongMode`. |
| `provider` | profile selection | Must be `"openai-codex"` for the profile to be selected. |

### 5.1 Freshness mapping

Codex CLI uses `last_refresh` (time of last token refresh) and measures
days *since* refresh. OpenClaw uses `expires_at` (token expiry) which
measures days *until* expiry.

For the snapshot, we normalize both to the existing
`last_refresh` / `days_since_refresh` fields:

- `last_refresh`: set to `expires_at` converted to a `datetime` (this
  represents "when the token expires" rather than "when it was refreshed",
  but it's the most useful timestamp to show the operator)
- `days_since_refresh`: set to a *negative* value representing days
  until expiry (e.g. -3.0 means "expires in 3 days"). This lets the
  existing UI show "3 days from now" and the freshness classifier
  distinguish healthy from degraded.

Alternatively, we add a `days_until_expiry` field to the snapshot and
adjust the classifier. Given the snapshot is a simple dataclass with
few consumers, adding one optional field is cleaner than overloading
`days_since_refresh` with negative semantics.

**Decision:** Add `days_until_expiry: float | None = None` to
`CodexAuthSnapshot`. The classifier checks `days_until_expiry` when
set (OpenClaw path), otherwise falls back to `days_since_refresh`
(Codex CLI path). For the OpenClaw path, `last_refresh` is set to
`datetime.fromtimestamp(expires_at / 1000, tz=timezone.utc)` and
labeled as "Expires" in context.

Thresholds for `days_until_expiry`:
- `> 5 days` → healthy
- `2-5 days` → degraded_yellow
- `< 2 days` → degraded_red
- `<= 0` (already expired) → down

### 5.2 `auth_mode` in snapshot

For OpenClaw profiles, `auth_mode` in the snapshot is set to
`"openclaw-oauth"` to distinguish from the Codex CLI's `"chatgpt"`.
This surfaces in the admin status panel so the operator knows which
file format is active.

## 6. Error cases

| Scenario | Exception / status | Snapshot `error_code` |
|----------|--------------------|-----------------------|
| File missing | `CodexAuthMissing` | `missing` |
| File unreadable | `CodexAuthMissing` | `permission` |
| JSON parse failure | `CodexAuthMalformed` | `malformed` |
| Neither Codex CLI nor OpenClaw format | `CodexAuthMalformed` | `malformed` |
| OpenClaw format but no `openai-codex` profile | `CodexAuthWrongMode` | `wrong_mode` |
| OpenClaw profile has `type != "oauth"` | `CodexAuthWrongMode` | `wrong_mode` |
| OpenClaw profile missing `access_token` | `CodexAuthMalformed` | `malformed` |
| Codex CLI format errors | Unchanged from current behavior | Unchanged |

## 7. Files changed

### 7.1 `src/flexloop/ai/codex_auth.py`

- Add format detection at the top of `_load_and_validate()`
- Add `_validate_openclaw()` method: find profile, check type, extract
  token, build normalized dict
- Add `days_until_expiry` field to `CodexAuthSnapshot`
- Update `_classify_freshness()` to accept either metric
- Update `snapshot()` to populate `days_until_expiry` for OpenClaw path

### 7.2 `tests/test_codex_auth.py`

New test cases:
- OpenClaw happy path (single codex profile, valid token)
- OpenClaw multiple profiles (picks the `openai-codex` one)
- OpenClaw no codex profile → wrong_mode
- OpenClaw profile type != oauth → wrong_mode
- OpenClaw missing access_token → malformed
- OpenClaw expired token → down status
- OpenClaw nearing expiry → degraded_yellow / degraded_red
- Format detection: ambiguous file (has both keys) → prefer OpenClaw
  if `version` + `profiles` present

### 7.3 `tests/fixtures/auth_json_factory.py`

Add `openclaw_auth_profiles()` builder that generates valid
`auth-profiles.json` content with configurable profiles, expiry, and
account IDs.

### 7.4 `admin-ui/src/components/forms/ConfigForm.tsx`

Update the `codex_auth_file` input placeholder from its current value
to: `~/.codex/auth.json or ~/.openclaw/.../auth-profiles.json`

### 7.5 `admin-ui/src/components/config/CodexStatusPanel.tsx`

When `auth_mode == "openclaw-oauth"`, display the `last_refresh`
timestamp with label "Expires" instead of "Last refresh". Show
`days_until_expiry` as "N days from now" instead of "N days ago".

### 7.6 `deploy/README.md` + `deploy/agent-runbook.md`

Update the Codex provider documentation to note that both
`~/.codex/auth.json` and OpenClaw `auth-profiles.json` are supported.
Update the pre-flight check to also look for the OpenClaw path.

## 8. What does NOT change

- DB schema — no migration needed
- Config field name — `codex_auth_file` stays
- `OpenAICodexAdapter` — calls `reader.read_access_token()` which
  returns a string regardless of source format
- Health endpoint — calls `reader.snapshot()` which returns the same
  dataclass
- Factory — creates the reader with the same path
- Config router — passes the same path string

## 9. Testing strategy

All new behavior is in `codex_auth.py` which is a pure-Python module
with no DB or network dependencies. Tests use fixture files written
to `tmp_path` — same pattern as the existing `test_codex_auth.py`.

No integration tests needed: the adapter and health endpoints are
already tested against `CodexAuthReader` via mocks, and those
interfaces don't change.

## 10. Acceptance criteria

1. Operator sets `codex_auth_file` to an OpenClaw `auth-profiles.json`
   path → `read_access_token()` returns the `openai-codex` profile's
   access token.
2. `snapshot()` shows `auth_mode: "openclaw-oauth"`, correct expiry
   info, and account ID.
3. Health page and Config status panel display the OpenClaw session
   state correctly, with "Expires" label.
4. Operator sets path to a Codex CLI `auth.json` → behavior unchanged
   from before this feature.
5. All existing tests pass unmodified.
