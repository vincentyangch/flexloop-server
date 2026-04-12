# Admin Dashboard — Phase 4b (Prompt editor) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin Prompt editor — a filesystem-backed versioned prompt manager with a CodeMirror UI. Operators can list prompt types and their versions, view/edit any version's markdown content, clone the active version into a new draft, set the active version per provider, diff two versions, delete old versions, and see the variables each template references. All prompt files stay as `.md` files on disk (NOT migrated to DB), so git history of prompt evolution is preserved and the existing `PromptManager` keeps working unchanged.

**Architecture:**
1. **Filesystem layout stays unchanged:** `prompts/<name>/v<N>.md` files plus `prompts/manifest.json` mapping `{prompt_name: {provider: version}}`. Phase 4b adds CRUD endpoints that touch these files directly — it does NOT introduce a new DB table or a caching layer.
2. **Backend service layer** (`flexloop.admin.prompt_service`) — pure Python functions that operate on a `prompts_dir: Path`. List, read, write (with `fcntl.flock`), clone, set-active (updates manifest with `flock`), delete (blocks if version is active in any provider), diff (`difflib.unified_diff`), extract-variables (regex `\{\{(\w+)\}\}`). All path components are validated against a whitelist regex to prevent traversal.
3. **Admin router** (`flexloop.admin.routers.prompts`) — 7 endpoints (§10.2) wrapping the service. FastAPI dependency `get_prompts_dir()` returns the default path; tests override it to a `tmp_path`.
4. **Frontend** — two-panel layout: left tree view of prompts + versions (active pinned with a green dot), right `@uiw/react-codemirror` editor with markdown syntax highlighting. Toolbar with Save / New version / Set active / Diff / Variables sidebar. No "Open in playground" button (that's phase 4c scope — will be added there).

**Tech Stack (new to phase 4b):**
- **Backend:** no new dependencies. Uses stdlib `fcntl`, `difflib`, `json`, `pathlib`.
- **Frontend:** three new npm dependencies:
  - `@uiw/react-codemirror` — React wrapper for CodeMirror 6
  - `@codemirror/lang-markdown` — markdown syntax highlighting
  - `@codemirror/theme-one-dark` — dark theme matching the rest of the admin UI

**Spec reference:** `docs/superpowers/specs/2026-04-06-admin-dashboard-design.md`. Read §10.2 (Prompt editor — this is the authoritative spec), §14 phase 4 bullet, §16 ("Bad prompt edit breaks plan generation" risk + mitigation), §17 acceptance criterion 3.

**Phases 1-3 + 4a already delivered** (do not redo): admin auth, 7 CRUD pages, Plans editor, Config editor with `write_audit_log` helper, runtime DB-backed Settings, hot-reload CSRF middleware. The `flexloop.admin.audit.write_audit_log` helper is available but **NOT used by phase 4b** — per the spec, v1 only audits config changes, not prompt edits. The helper stays reserved for phase 5 or later.

**Phases 4c (AI Playground) and 4d (AI Usage dashboard) are out of scope.** The spec's "Open in playground →" toolbar button is deferred to 4c (it needs a playground to exist). Variable inspector (local regex extraction) IS in scope for 4b.

---

## Decisions locked in for this phase

These choices are fixed before implementation starts. Do not re-litigate them mid-execution — if a decision turns out to be wrong, stop and ask the user.

1. **Prompt filesystem layout stays identical** to current state:
   ```
   prompts/
   ├── manifest.json              {name: {provider: version}} mapping
   ├── <prompt_name>/
   │   ├── v1.md
   │   ├── v2.md
   │   └── ...
   ```
   `manifest.json` format (unchanged from pre-phase-4b):
   ```json
   {
     "plan_generation": { "default": "v2" },
     "plan_refinement": { "default": "v1" }
   }
   ```

2. **Path traversal prevention (critical — security invariant).** Every endpoint that accepts a `name` or `version` path parameter validates:
   - Prompt `name`: regex `^[a-z][a-z0-9_]*$` — lowercase letters, digits, underscores; must start with a letter. No slashes, dots, or spaces.
   - Version `version`: regex `^v\d+$` — literal "v" followed by digits. No other formats.
   
   Any path component failing validation returns `400 Bad Request` with `{detail: "invalid prompt name"}` or `{detail: "invalid version name"}`. The service layer helper `_validate_name(name)` / `_validate_version(version)` enforces this BEFORE any filesystem operation.

3. **Auto-incremented version numbers.** `POST /api/admin/prompts/{name}/versions` does NOT accept a version name from the client. It computes `next_version = "v" + str(max_existing_version_number + 1)`, clones the current active version's content, and writes it. The response contains the new version name.

4. **Clone source = the `default` provider's active version.** `manifest.json` can have per-provider active versions (e.g. `{"plan_generation": {"default": "v2", "anthropic": "v1"}}`). The clone endpoint sources from `manifest[name]["default"]`. If there's no "default" entry, fall back to any active version for the prompt (alphabetically first provider). If the prompt has no active versions at all (shouldn't happen in practice), 409.

5. **File locking via `fcntl.flock`.** Both prompt file writes and manifest writes use `fcntl.flock(fd, LOCK_EX)` on open-for-write. The manifest update is a read-modify-write cycle: open manifest with LOCK_EX, re-read contents, modify the dict, seek to 0, truncate, write, release. This guarantees two concurrent admin saves don't clobber each other. **Linux/macOS only** — matches the spec's deployment target (§10.2).

6. **Delete blocks if the version is active in ANY provider.** `DELETE /versions/{version}` checks the full manifest: if the version appears as a value for ANY provider key under `manifest[name]`, return 409 with `{detail: "cannot delete version N: still active for provider X — set a different version as active first"}`. The admin must explicitly set a different version as active before deleting.

7. **Cannot delete the last version.** Even if no provider has it as active (e.g. the prompt had 2 versions and one was already deleted), deleting the last remaining version leaves a "dangling" prompt. Return 409 with `{detail: "cannot delete the last version of a prompt"}`. The admin can delete the whole prompt directory via the filesystem if they really want.

8. **Diff format: unified diff (`difflib.unified_diff`).** `GET /diff?from=v1&to=v2` returns a JSON response:
   ```json
   {
     "name": "plan_generation",
     "from_version": "v1",
     "to_version": "v2",
     "diff": "--- v1\n+++ v2\n@@ -1,3 +1,3 @@\n-old\n+new\n"
   }
   ```
   The frontend renders this as a preformatted `<pre>` with per-line coloring (`+` green, `-` red, `@@` gray) via a simple line-level CSS pass. No diff library on the frontend.

9. **Variable extraction: regex `\{\{(\w+)\}\}` — simple, runs on both sides.** Backend `extract_variables(content)` returns a sorted deduped list. Frontend has its own copy of the same regex that runs on the editor's current buffer (not the saved version), so the variable inspector updates live as the user types without needing a backend round-trip. The backend version is used inside the GET /versions/{v} response so the admin can see the variables on load without typing anything.

10. **No audit log entries for prompt changes in phase 4b.** Per spec §10.1 "v1 only audits config changes". The `write_audit_log` helper is available but unused. If an operator wants a trail of prompt edits, git history of the repo provides it (the `.md` files are version-controlled).

11. **CodeMirror setup: `@uiw/react-codemirror` + markdown lang + one-dark theme.** No Jinja syntax highlighting — the `{{variable}}` placeholders render as regular markdown text. The spec mentions "markdown + Jinja syntax highlighting" but no stable CodeMirror 6 Jinja package exists; markdown-only is the pragmatic choice and the variable inspector makes up for it.

12. **Editor is controlled (not uncontrolled).** The `PromptEditor` page holds the current buffer in React state. The CodeMirror component receives `value={buffer}` and `onChange={setBuffer}`. Unsaved changes are tracked via `buffer !== savedContent` (not a dirty-ref). Navigating away from a dirty prompt triggers a `window.confirm` via `useBlocker` or a simple listener on selection-change.

13. **Save is explicit — no autosave.** Clicking the "Save" button writes the current buffer to the backend. Autosave is explicitly out of scope (risk of half-typed prompts corrupting production).

14. **Set active is per-provider.** The toolbar button "Set as active" opens a dropdown with the available providers (from the current manifest: `default`, plus any explicitly-configured others) and the admin picks. For v1 we ALWAYS assume "default" is the only provider — the dropdown shows a single option. Future phases can add multi-provider UI; phase 4b just hits `PUT /active` with `{version, provider: "default"}`.

15. **Frontend: no toast on buffer-edit, only on successful mutations.** Editing the buffer doesn't fire a toast; only Save, New version, Set active, and Delete fire toasts. The "unsaved changes" indicator is an inline text next to the version name ("• unsaved"), not a toast.

16. **No variable schema or validation.** The variable inspector lists the names and that's it. No type checking, no required/optional distinction, no default values. Phase 4c's playground can extend this with a variable form.

17. **Worktree + feature branch:**
    - Worktree: `/Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b`
    - Branch: `feat/admin-dashboard-phase4b-prompts`
    - Merge strategy: fast-forward into `main`, delete branch + worktree, bump parent submodule, update memory.

---

## File Structure

All paths relative to `flexloop-server/` unless stated otherwise.

**Backend — new:**
```
src/flexloop/admin/
├── prompt_service.py              NEW — pure-Python service (CRUD + diff + variables)
└── routers/
    └── prompts.py                 NEW — 7 admin endpoints
```

**Backend — modified:**
```
src/flexloop/main.py               add import + include_router
```

**Backend — tests:**
```
tests/
├── test_admin_prompt_service.py   NEW — unit tests for the service (uses tmp_path)
└── test_admin_prompts.py          NEW — integration tests for the router
```

**Frontend — new:**
```
admin-ui/src/
├── pages/PromptsPage.tsx          NEW — two-panel prompt editor
└── components/prompts/            NEW — sub-components used only by PromptsPage
    ├── PromptTree.tsx             NEW — left panel tree view
    ├── PromptToolbar.tsx          NEW — Save / New / Set active / Diff
    ├── VariableInspector.tsx      NEW — right sidebar showing {{variables}}
    └── DiffDialog.tsx             NEW — modal showing unified diff
```

**Frontend — modified:**
```
admin-ui/
├── package.json                   add @uiw/react-codemirror,
│                                  @codemirror/lang-markdown,
│                                  @codemirror/theme-one-dark
└── src/
    ├── App.tsx                    add /ai/prompts route
    ├── components/AppSidebar.tsx  remove `disabled: true` from Prompts item
    └── lib/api.types.ts           regenerated from updated OpenAPI
```

**Docs:**
```
docs/admin-dashboard-phase4b-smoke-test.md   NEW — manual + automated checklist
```

---

## Execution setup

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree add /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b -b feat/admin-dashboard-phase4b-prompts
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b
uv sync --extra dev
uv pip install -e .
cd admin-ui && npm install --legacy-peer-deps && cd ..
```

Verify baseline:

```bash
uv run pytest -q
```

Expected: 323 tests green (phase 4a baseline).

```bash
cd admin-ui && npx tsc --noEmit && npm run build && cd ..
```

Expected: both green.

---

## Chunk 1: Backend — prompt service layer

Pure-Python CRUD functions on a `prompts_dir: Path`. No HTTP. Fully unit-testable via `tmp_path`. The router (Chunk 2) is a thin wrapper.

### Task 1: Write failing unit tests for `list_prompts`

**Files:**
- Create: `tests/test_admin_prompt_service.py`

- [ ] **Step 1: Create the test file with fixture + list tests**

```python
"""Unit tests for flexloop.admin.prompt_service."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from flexloop.admin.prompt_service import (
    PromptInfo,
    create_version,
    delete_version,
    diff_versions,
    extract_variables,
    list_prompts,
    read_version,
    set_active,
    write_version,
)


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    """Build a small prompts directory with two prompts and multiple versions."""
    (tmp_path / "plan_generation").mkdir()
    (tmp_path / "plan_generation" / "v1.md").write_text("v1 content for plan_generation")
    (tmp_path / "plan_generation" / "v2.md").write_text("v2 content {{user_name}}")
    (tmp_path / "chat").mkdir()
    (tmp_path / "chat" / "v1.md").write_text("chat v1 {{message}}")
    manifest = {
        "plan_generation": {"default": "v2"},
        "chat": {"default": "v1"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    return tmp_path


class TestListPrompts:
    def test_returns_all_prompts_with_versions(self, prompts_dir: Path) -> None:
        result = list_prompts(prompts_dir)
        assert len(result) == 2
        by_name = {p.name: p for p in result}

        pg = by_name["plan_generation"]
        assert pg.versions == ["v1", "v2"]
        assert pg.active_by_provider == {"default": "v2"}

        chat = by_name["chat"]
        assert chat.versions == ["v1"]
        assert chat.active_by_provider == {"default": "v1"}

    def test_versions_sorted_by_numeric_order(self, tmp_path: Path) -> None:
        """v10 must come after v9, not between v1 and v2 (natural sort)."""
        (tmp_path / "foo").mkdir()
        for i in [1, 2, 10, 3, 9]:
            (tmp_path / "foo" / f"v{i}.md").write_text(f"content {i}")
        (tmp_path / "manifest.json").write_text(json.dumps({"foo": {"default": "v1"}}))
        result = list_prompts(tmp_path)
        assert result[0].versions == ["v1", "v2", "v3", "v9", "v10"]

    def test_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text("{}")
        assert list_prompts(tmp_path) == []

    def test_ignores_non_prompt_files(self, tmp_path: Path) -> None:
        (tmp_path / "manifest.json").write_text("{}")
        (tmp_path / "README.md").write_text("not a prompt")
        (tmp_path / ".DS_Store").write_text("trash")
        result = list_prompts(tmp_path)
        assert result == []

    def test_ignores_non_version_files_inside_prompt_dir(self, tmp_path: Path) -> None:
        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "v1.md").write_text("x")
        (tmp_path / "foo" / "notes.txt").write_text("y")
        (tmp_path / "foo" / "v2a.md").write_text("z")
        (tmp_path / "manifest.json").write_text(json.dumps({"foo": {"default": "v1"}}))
        result = list_prompts(tmp_path)
        assert result[0].versions == ["v1"]
```

- [ ] **Step 2: Run to confirm they fail**

```bash
uv run pytest tests/test_admin_prompt_service.py::TestListPrompts -v
```

Expected: 5 fails (module doesn't exist).

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_admin_prompt_service.py
git commit -m "test(admin): failing tests for list_prompts"
```

---

### Task 2: Implement the service module skeleton + `list_prompts`

**Files:**
- Create: `src/flexloop/admin/prompt_service.py`

- [ ] **Step 1: Write the service module**

```python
"""Filesystem-backed prompt CRUD for the admin dashboard.

Prompts live at ``<prompts_dir>/<name>/v<N>.md``. A single
``<prompts_dir>/manifest.json`` maps ``{name: {provider: version}}`` to
track which version is active per provider.

This module provides pure Python functions over a ``prompts_dir: Path``.
The HTTP layer (admin.routers.prompts) wraps these with validation and
error-to-HTTPException translation.

Concurrency: writes use ``fcntl.flock`` (Linux/macOS only — matches
the deployment target; see spec §10.2).

Security: path components are validated by ``_validate_name`` and
``_validate_version`` to prevent traversal. Never pass raw user input
to ``Path`` operations without validating first.
"""
from __future__ import annotations

import fcntl
import json
import re
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path


# Path-component whitelists — enforced BEFORE any filesystem access.
_VALID_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_VALID_VERSION = re.compile(r"^v\d+$")
_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")

MANIFEST_NAME = "manifest.json"


class PromptServiceError(Exception):
    """Base class for service-level errors.

    The router translates these to HTTP responses with clean messages.
    """


class NotFoundError(PromptServiceError):
    """Prompt or version does not exist."""


class ConflictError(PromptServiceError):
    """Operation would leave the prompt in an invalid state (e.g. delete
    the active version, or the last version of a prompt)."""


class InvalidNameError(PromptServiceError):
    """Caller supplied a prompt name or version that failed validation.
    The router returns 400 for these.
    """


@dataclass
class PromptInfo:
    """Summary of one prompt directory."""
    name: str
    versions: list[str] = field(default_factory=list)
    active_by_provider: dict[str, str] = field(default_factory=dict)


# --- Validation helpers ---------------------------------------------------


def _validate_name(name: str) -> None:
    if not _VALID_NAME.match(name):
        raise InvalidNameError(f"invalid prompt name: {name!r}")


def _validate_version(version: str) -> None:
    if not _VALID_VERSION.match(version):
        raise InvalidNameError(f"invalid version name: {version!r}")


def _version_number(version: str) -> int:
    """Extract the integer N from a ``v<N>`` string. Assumes validation."""
    return int(version[1:])


def _sort_versions(versions: list[str]) -> list[str]:
    """Sort versions by numeric part: v1 < v2 < v9 < v10."""
    return sorted(versions, key=_version_number)


# --- Manifest helpers -----------------------------------------------------


def _manifest_path(prompts_dir: Path) -> Path:
    return prompts_dir / MANIFEST_NAME


def _read_manifest(prompts_dir: Path) -> dict:
    path = _manifest_path(prompts_dir)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _write_manifest_locked(prompts_dir: Path, manifest: dict) -> None:
    """Overwrite the manifest file under an exclusive lock.

    Uses ``fcntl.flock(fd, LOCK_EX)`` on the file descriptor. The lock
    is released when the file is closed at the end of the ``with`` block.
    """
    path = _manifest_path(prompts_dir)
    # Open in r+ if existing, w if new — but we need LOCK_EX on the fd,
    # and the simplest lockable form is open-for-writing.
    mode = "r+" if path.exists() else "w+"
    with open(path, mode) as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        json.dump(manifest, f, indent=2)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# --- List -----------------------------------------------------------------


def list_prompts(prompts_dir: Path) -> list[PromptInfo]:
    """Return a sorted list of PromptInfo for every prompt in the manifest.

    Directories on disk that are not in the manifest are ignored.
    Version files that don't match ``v\\d+\\.md`` are ignored.
    """
    manifest = _read_manifest(prompts_dir)
    result: list[PromptInfo] = []
    for name in sorted(manifest.keys()):
        dir_path = prompts_dir / name
        if not dir_path.is_dir():
            continue
        versions = []
        for f in dir_path.iterdir():
            if not f.is_file() or f.suffix != ".md":
                continue
            stem = f.stem
            if _VALID_VERSION.match(stem):
                versions.append(stem)
        result.append(
            PromptInfo(
                name=name,
                versions=_sort_versions(versions),
                active_by_provider=dict(manifest[name]),
            )
        )
    return result


# --- Read a version -------------------------------------------------------


def read_version(prompts_dir: Path, name: str, version: str) -> str:
    _validate_name(name)
    _validate_version(version)
    path = prompts_dir / name / f"{version}.md"
    if not path.exists():
        raise NotFoundError(f"prompt {name!r} version {version!r} not found")
    return path.read_text()


# --- Write a version ------------------------------------------------------


def write_version(prompts_dir: Path, name: str, version: str, content: str) -> None:
    """Overwrite ``<name>/<version>.md`` under an exclusive lock.

    The directory must already exist (this is an UPDATE, not a create).
    Use ``create_version`` for clone-and-new semantics.
    """
    _validate_name(name)
    _validate_version(version)
    dir_path = prompts_dir / name
    if not dir_path.is_dir():
        raise NotFoundError(f"prompt {name!r} not found")
    path = dir_path / f"{version}.md"
    if not path.exists():
        raise NotFoundError(f"prompt {name!r} version {version!r} not found")
    # r+ opens for read-write without truncating; we truncate manually after
    # acquiring the lock to avoid losing contents in a crash window.
    with open(path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.seek(0)
        f.truncate()
        f.write(content)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


# --- Create a new version (clone of current active) ----------------------


def create_version(prompts_dir: Path, name: str) -> tuple[str, str]:
    """Create the next version by cloning the active (default provider).

    Returns (new_version_name, content).
    """
    _validate_name(name)
    dir_path = prompts_dir / name
    if not dir_path.is_dir():
        raise NotFoundError(f"prompt {name!r} not found")

    manifest = _read_manifest(prompts_dir)
    provider_map: dict[str, str] = manifest.get(name, {})
    source_version = provider_map.get("default") or next(
        iter(sorted(provider_map.values())), None
    )
    if source_version is None:
        raise ConflictError(
            f"prompt {name!r} has no active version to clone from"
        )

    source_path = dir_path / f"{source_version}.md"
    if not source_path.exists():
        raise NotFoundError(
            f"prompt {name!r} active version {source_version!r} file is missing"
        )
    source_content = source_path.read_text()

    # Compute next version number — scan existing files, not the manifest,
    # to cover orphaned versions.
    existing_numbers: list[int] = []
    for f in dir_path.iterdir():
        if f.is_file() and f.suffix == ".md" and _VALID_VERSION.match(f.stem):
            existing_numbers.append(_version_number(f.stem))
    next_number = (max(existing_numbers) if existing_numbers else 0) + 1
    new_version = f"v{next_number}"
    new_path = dir_path / f"{new_version}.md"

    # Write the new file — use LOCK_EX on an open-for-write to prevent
    # two concurrent "New version" clicks from racing.
    with open(new_path, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        f.write(source_content)
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    return new_version, source_content


# --- Set active version --------------------------------------------------


def set_active(prompts_dir: Path, name: str, version: str, provider: str = "default") -> None:
    """Update ``manifest.json`` to make ``version`` active for ``provider``.

    The new manifest is written atomically under ``fcntl.flock``.
    """
    _validate_name(name)
    _validate_version(version)

    # Provider values are also free-form strings — validate with the same
    # rules as prompt names to keep manifest keys safe.
    if not _VALID_NAME.match(provider):
        raise InvalidNameError(f"invalid provider name: {provider!r}")

    dir_path = prompts_dir / name
    if not dir_path.is_dir():
        raise NotFoundError(f"prompt {name!r} not found")
    version_path = dir_path / f"{version}.md"
    if not version_path.exists():
        raise NotFoundError(
            f"prompt {name!r} version {version!r} does not exist"
        )

    manifest = _read_manifest(prompts_dir)
    manifest.setdefault(name, {})[provider] = version
    _write_manifest_locked(prompts_dir, manifest)


# --- Delete a version ----------------------------------------------------


def delete_version(prompts_dir: Path, name: str, version: str) -> None:
    """Delete ``<name>/<version>.md``.

    Refuses to delete:
    - A version that is active for ANY provider (409 ConflictError)
    - The last remaining version of a prompt (409 ConflictError)
    """
    _validate_name(name)
    _validate_version(version)
    dir_path = prompts_dir / name
    if not dir_path.is_dir():
        raise NotFoundError(f"prompt {name!r} not found")
    path = dir_path / f"{version}.md"
    if not path.exists():
        raise NotFoundError(
            f"prompt {name!r} version {version!r} not found"
        )

    manifest = _read_manifest(prompts_dir)
    provider_map: dict[str, str] = manifest.get(name, {})
    active_providers = [p for p, v in provider_map.items() if v == version]
    if active_providers:
        raise ConflictError(
            f"cannot delete version {version!r}: still active for provider "
            f"{active_providers[0]!r} — set a different version as active first"
        )

    # Count remaining versions on disk to catch "last version" case.
    remaining = [
        f for f in dir_path.iterdir()
        if f.is_file() and f.suffix == ".md" and _VALID_VERSION.match(f.stem)
    ]
    if len(remaining) <= 1:
        raise ConflictError("cannot delete the last version of a prompt")

    path.unlink()


# --- Diff ----------------------------------------------------------------


def diff_versions(
    prompts_dir: Path, name: str, from_version: str, to_version: str
) -> str:
    """Return a unified diff (as a single string) between two versions."""
    _validate_name(name)
    _validate_version(from_version)
    _validate_version(to_version)
    from_content = read_version(prompts_dir, name, from_version)
    to_content = read_version(prompts_dir, name, to_version)
    diff_lines = unified_diff(
        from_content.splitlines(keepends=True),
        to_content.splitlines(keepends=True),
        fromfile=from_version,
        tofile=to_version,
    )
    return "".join(diff_lines)


# --- Variable extraction --------------------------------------------------


def extract_variables(content: str) -> list[str]:
    """Return a sorted deduped list of ``{{variable_names}}`` in ``content``."""
    return sorted(set(_VARIABLE_PATTERN.findall(content)))
```

- [ ] **Step 2: Run the list tests**

```bash
uv run pytest tests/test_admin_prompt_service.py::TestListPrompts -v
```

Expected: all 5 pass.

- [ ] **Step 3: Full suite sanity check**

```bash
uv run pytest -q
```

Expected: 328 tests green (323 baseline + 5 new).

- [ ] **Step 4: Commit**

```bash
git add src/flexloop/admin/prompt_service.py
git commit -m "feat(admin): prompt_service list_prompts with validation helpers"
```

---

### Task 3: Tests for `read_version`, `write_version`, `create_version`

**Files:**
- Modify: `tests/test_admin_prompt_service.py`

- [ ] **Step 1: Append the test classes**

```python
class TestReadVersion:
    def test_returns_file_contents(self, prompts_dir: Path) -> None:
        content = read_version(prompts_dir, "plan_generation", "v1")
        assert content == "v1 content for plan_generation"

    def test_missing_prompt_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            read_version(prompts_dir, "nonexistent", "v1")

    def test_missing_version_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            read_version(prompts_dir, "plan_generation", "v99")

    def test_rejects_path_traversal_in_name(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import InvalidNameError
        with pytest.raises(InvalidNameError):
            read_version(prompts_dir, "../etc/passwd", "v1")

    def test_rejects_path_traversal_in_version(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import InvalidNameError
        with pytest.raises(InvalidNameError):
            read_version(prompts_dir, "plan_generation", "../foo")


class TestWriteVersion:
    def test_overwrites_existing_version(self, prompts_dir: Path) -> None:
        write_version(prompts_dir, "plan_generation", "v1", "new content")
        assert read_version(prompts_dir, "plan_generation", "v1") == "new content"

    def test_missing_version_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            write_version(prompts_dir, "plan_generation", "v99", "x")

    def test_missing_prompt_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            write_version(prompts_dir, "nonexistent", "v1", "x")

    def test_rejects_invalid_name(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import InvalidNameError
        with pytest.raises(InvalidNameError):
            write_version(prompts_dir, "Plan-Generation!", "v1", "x")


class TestCreateVersion:
    def test_clones_active_version(self, prompts_dir: Path) -> None:
        new_version, content = create_version(prompts_dir, "plan_generation")
        assert new_version == "v3"
        assert content == "v2 content {{user_name}}"
        # Read it back
        assert read_version(prompts_dir, "plan_generation", "v3") == (
            "v2 content {{user_name}}"
        )

    def test_version_number_continues_from_max(self, tmp_path: Path) -> None:
        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "v1.md").write_text("one")
        (tmp_path / "foo" / "v5.md").write_text("five")
        (tmp_path / "manifest.json").write_text(
            json.dumps({"foo": {"default": "v1"}})
        )
        new_version, _ = create_version(tmp_path, "foo")
        assert new_version == "v6"

    def test_prompt_with_no_active_raises_conflict(self, tmp_path: Path) -> None:
        from flexloop.admin.prompt_service import ConflictError
        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "v1.md").write_text("x")
        (tmp_path / "manifest.json").write_text(json.dumps({"foo": {}}))
        with pytest.raises(ConflictError):
            create_version(tmp_path, "foo")

    def test_missing_prompt_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            create_version(prompts_dir, "nonexistent")
```

- [ ] **Step 2: Run the new tests**

```bash
uv run pytest tests/test_admin_prompt_service.py::TestReadVersion tests/test_admin_prompt_service.py::TestWriteVersion tests/test_admin_prompt_service.py::TestCreateVersion -v
```

Expected: all 13 pass (the implementation is already in place from Task 2).

- [ ] **Step 3: Full suite**

```bash
uv run pytest -q
```

Expected: 341 green.

- [ ] **Step 4: Commit**

```bash
git add tests/test_admin_prompt_service.py
git commit -m "test(admin): read/write/create version tests for prompt_service"
```

---

### Task 4: Tests for `set_active`, `delete_version`, `diff_versions`, `extract_variables`

**Files:**
- Modify: `tests/test_admin_prompt_service.py`

- [ ] **Step 1: Append the test classes**

```python
class TestSetActive:
    def test_updates_manifest(self, prompts_dir: Path) -> None:
        set_active(prompts_dir, "plan_generation", "v1")
        manifest = json.loads((prompts_dir / "manifest.json").read_text())
        assert manifest["plan_generation"]["default"] == "v1"

    def test_per_provider(self, prompts_dir: Path) -> None:
        set_active(prompts_dir, "plan_generation", "v1", provider="anthropic")
        manifest = json.loads((prompts_dir / "manifest.json").read_text())
        # Default is unchanged
        assert manifest["plan_generation"]["default"] == "v2"
        assert manifest["plan_generation"]["anthropic"] == "v1"

    def test_version_must_exist(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            set_active(prompts_dir, "plan_generation", "v99")

    def test_invalid_provider_rejected(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import InvalidNameError
        with pytest.raises(InvalidNameError):
            set_active(prompts_dir, "plan_generation", "v1", provider="../evil")


class TestDeleteVersion:
    def test_deletes_non_active(self, prompts_dir: Path) -> None:
        # plan_generation has v1 and v2; v2 is active. Delete v1.
        delete_version(prompts_dir, "plan_generation", "v1")
        assert not (prompts_dir / "plan_generation" / "v1.md").exists()
        assert (prompts_dir / "plan_generation" / "v2.md").exists()

    def test_refuses_active_version(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import ConflictError
        with pytest.raises(ConflictError, match="still active"):
            delete_version(prompts_dir, "plan_generation", "v2")

    def test_refuses_last_version(self, prompts_dir: Path) -> None:
        from flexloop.admin.prompt_service import ConflictError
        # chat has only v1 (and it's active). Set active to v1 for default,
        # then try to delete a non-existent v2 → NotFoundError first, so
        # we build a fresh case.
        with pytest.raises(ConflictError):
            delete_version(prompts_dir, "chat", "v1")

    def test_refuses_active_in_nondefault_provider(
        self, tmp_path: Path
    ) -> None:
        from flexloop.admin.prompt_service import ConflictError
        (tmp_path / "foo").mkdir()
        (tmp_path / "foo" / "v1.md").write_text("one")
        (tmp_path / "foo" / "v2.md").write_text("two")
        (tmp_path / "manifest.json").write_text(
            json.dumps({"foo": {"default": "v2", "anthropic": "v1"}})
        )
        with pytest.raises(ConflictError, match="still active"):
            delete_version(tmp_path, "foo", "v1")


class TestDiffVersions:
    def test_unified_diff_output(self, prompts_dir: Path) -> None:
        diff = diff_versions(prompts_dir, "plan_generation", "v1", "v2")
        assert "--- v1" in diff
        assert "+++ v2" in diff
        assert "-v1 content for plan_generation" in diff
        assert "+v2 content {{user_name}}" in diff

    def test_same_version_empty_diff(self, prompts_dir: Path) -> None:
        diff = diff_versions(prompts_dir, "plan_generation", "v1", "v1")
        assert diff == ""

    def test_missing_from_version_raises(self, prompts_dir: Path) -> None:
        with pytest.raises(NotFoundError):
            diff_versions(prompts_dir, "plan_generation", "v99", "v1")


class TestExtractVariables:
    def test_finds_variables(self) -> None:
        assert extract_variables("Hello {{user_name}}, your goal is {{goal}}") == [
            "goal",
            "user_name",
        ]

    def test_deduplicates(self) -> None:
        assert extract_variables("{{a}} and {{a}} and {{b}}") == ["a", "b"]

    def test_empty_string(self) -> None:
        assert extract_variables("") == []

    def test_ignores_non_word_chars(self) -> None:
        # {{ hello }} with spaces is NOT a variable match
        assert extract_variables("{{ hello }}") == []
        # {{nested.attr}} is not supported (dots aren't word chars)
        assert extract_variables("{{nested.attr}}") == []
```

- [ ] **Step 2: Run them**

```bash
uv run pytest tests/test_admin_prompt_service.py -v
```

Expected: all 27 tests pass (5 list + 5 read + 4 write + 4 create + 4 set_active + 4 delete + 3 diff + 4 variables = 33, adjust if my count differs).

Actually, let me recount: 5 + 5 + 4 + 4 + 4 + 4 + 3 + 4 = 33 tests in test_admin_prompt_service.py.

- [ ] **Step 3: Full suite**

```bash
uv run pytest -q
```

Expected: ~356 green (323 + 33 new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_admin_prompt_service.py
git commit -m "test(admin): set_active/delete/diff/variables tests for prompt_service"
```

---

**End of Chunk 1.** The service layer is complete and thoroughly tested (33 unit tests, all passing). Next chunk wraps it in HTTP endpoints.

---

## Chunk 2: Backend — admin prompts router

7 endpoints per spec §10.2, thin wrappers over the Chunk 1 service functions. Tests use FastAPI's dependency override to point `get_prompts_dir` at a pytest `tmp_path`.

### Task 5: Router + `get_prompts_dir` dependency + `GET /api/admin/prompts` list endpoint

**Files:**
- Create: `src/flexloop/admin/routers/prompts.py`
- Modify: `src/flexloop/main.py`
- Create: `tests/test_admin_prompts.py`

- [ ] **Step 1: Write failing tests for the list endpoint**

```python
"""Integration tests for /api/admin/prompts."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import SESSION_COOKIE_NAME, create_session, hash_password
from flexloop.admin.routers.prompts import get_prompts_dir
from flexloop.main import app
from flexloop.models.admin_user import AdminUser


ORIGIN = "http://localhost:5173"


async def _make_admin_and_cookie(db: AsyncSession) -> dict[str, str]:
    admin = AdminUser(username="tester", password_hash=hash_password("password123"))
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    token, _ = await create_session(db, admin_user_id=admin.id)
    return {SESSION_COOKIE_NAME: token}


@pytest.fixture
def prompts_tmp_dir(tmp_path: Path) -> Path:
    """Seed a minimal prompts directory and override the router dependency."""
    (tmp_path / "plan_generation").mkdir()
    (tmp_path / "plan_generation" / "v1.md").write_text("v1 original content")
    (tmp_path / "plan_generation" / "v2.md").write_text("v2 {{user_name}}")
    (tmp_path / "chat").mkdir()
    (tmp_path / "chat" / "v1.md").write_text("chat v1 {{message}}")
    manifest = {
        "plan_generation": {"default": "v2"},
        "chat": {"default": "v1"},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))

    app.dependency_overrides[get_prompts_dir] = lambda: tmp_path
    yield tmp_path
    app.dependency_overrides.pop(get_prompts_dir, None)


class TestListPromptsEndpoint:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        assert (await client.get("/api/admin/prompts")).status_code == 401

    async def test_returns_all_prompts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get("/api/admin/prompts", cookies=cookies)
        assert res.status_code == 200
        body = res.json()
        assert "prompts" in body
        by_name = {p["name"]: p for p in body["prompts"]}
        assert "plan_generation" in by_name
        assert by_name["plan_generation"]["versions"] == ["v1", "v2"]
        assert by_name["plan_generation"]["active_by_provider"] == {"default": "v2"}
        assert "chat" in by_name
        assert by_name["chat"]["versions"] == ["v1"]
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_prompts.py::TestListPromptsEndpoint -v
```

Expected: fails (router doesn't exist yet, possibly ImportError).

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_admin_prompts.py
git commit -m "test(admin): failing tests for GET /api/admin/prompts"
```

- [ ] **Step 4: Write the router with the list endpoint**

```python
"""Admin endpoints for prompt file management.

All endpoints are thin wrappers over ``flexloop.admin.prompt_service``.
The prompts directory path is provided via the ``get_prompts_dir``
dependency, which tests override to a temp path.

Spec: §10.2
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from flexloop.admin import prompt_service
from flexloop.admin.auth import require_admin
from flexloop.admin.prompt_service import (
    ConflictError,
    InvalidNameError,
    NotFoundError,
)
from flexloop.models.admin_user import AdminUser

router = APIRouter(prefix="/api/admin/prompts", tags=["admin:prompts"])


# --- Dependency ------------------------------------------------------------


# Default prompts directory — matches flexloop.routers.ai PROMPTS_DIR.
# Resolved to an absolute path so worktrees/tests can't accidentally
# read from the wrong directory when the CWD changes.
_DEFAULT_PROMPTS_DIR = Path("prompts").resolve()


def get_prompts_dir() -> Path:
    """FastAPI dependency returning the active prompts directory.

    Tests override this via ``app.dependency_overrides`` to point at a
    ``tmp_path`` fixture.
    """
    return _DEFAULT_PROMPTS_DIR


# --- Schemas --------------------------------------------------------------


class PromptInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    versions: list[str]
    active_by_provider: dict[str, str]


class ListPromptsResponse(BaseModel):
    prompts: list[PromptInfoResponse]


# --- Error translation ----------------------------------------------------


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidNameError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, NotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


# --- List -----------------------------------------------------------------


@router.get("", response_model=ListPromptsResponse)
async def list_prompts(
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> ListPromptsResponse:
    infos = prompt_service.list_prompts(prompts_dir)
    return ListPromptsResponse(
        prompts=[
            PromptInfoResponse(
                name=p.name,
                versions=p.versions,
                active_by_provider=p.active_by_provider,
            )
            for p in infos
        ]
    )
```

- [ ] **Step 5: Mount the router in `main.py`**

Add the import next to the other admin router imports:

```python
from flexloop.admin.routers.prompts import router as admin_prompts_router
```

And add `app.include_router(admin_prompts_router)` next to the other admin include_routers.

- [ ] **Step 6: Run the list tests**

```bash
uv run pytest tests/test_admin_prompts.py::TestListPromptsEndpoint -v
```

Expected: both tests pass.

- [ ] **Step 7: Full suite**

```bash
uv run pytest -q
```

Expected: 358 tests green.

- [ ] **Step 8: Commit**

```bash
git add src/flexloop/admin/routers/prompts.py src/flexloop/main.py
git commit -m "feat(admin): GET /api/admin/prompts list endpoint"
```

---

### Task 6: `GET /api/admin/prompts/{name}/versions/{version}`

**Files:**
- Modify: `src/flexloop/admin/routers/prompts.py`
- Modify: `tests/test_admin_prompts.py`

- [ ] **Step 1: Append failing tests**

```python
class TestGetVersion:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.get("/api/admin/prompts/plan_generation/versions/v1")
        assert res.status_code == 401

    async def test_returns_content_and_variables(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/plan_generation/versions/v2",
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "plan_generation"
        assert body["version"] == "v2"
        assert body["content"] == "v2 {{user_name}}"
        assert body["variables"] == ["user_name"]

    async def test_404_when_missing(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/plan_generation/versions/v99",
            cookies=cookies,
        )
        assert res.status_code == 404

    async def test_400_on_invalid_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/Bad-Name/versions/v1",
            cookies=cookies,
        )
        assert res.status_code == 400
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_prompts.py::TestGetVersion -v
```

Expected: 4 fail.

- [ ] **Step 3: Add the schema + handler**

Append to `src/flexloop/admin/routers/prompts.py`:

```python
class PromptVersionResponse(BaseModel):
    name: str
    version: str
    content: str
    variables: list[str]


@router.get(
    "/{name}/versions/{version}",
    response_model=PromptVersionResponse,
)
async def get_version(
    name: str,
    version: str,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PromptVersionResponse:
    try:
        content = prompt_service.read_version(prompts_dir, name, version)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return PromptVersionResponse(
        name=name,
        version=version,
        content=content,
        variables=prompt_service.extract_variables(content),
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_admin_prompts.py::TestGetVersion -v
```

Expected: all 4 pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q
```

Expected: 362 green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/prompts.py tests/test_admin_prompts.py
git commit -m "feat(admin): GET /api/admin/prompts/{name}/versions/{version}"
```

---

### Task 7: `PUT /api/admin/prompts/{name}/versions/{version}` (save content)

**Files:**
- Modify: `src/flexloop/admin/routers/prompts.py`
- Modify: `tests/test_admin_prompts.py`

- [ ] **Step 1: Append failing tests**

```python
class TestUpdateVersion:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v1",
            json={"content": "x"},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_updates_content(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v1",
            json={"content": "brand new content"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        # Returns the new content + variables
        body = res.json()
        assert body["content"] == "brand new content"
        assert body["variables"] == []
        # File on disk reflects the update
        assert (prompts_tmp_dir / "plan_generation" / "v1.md").read_text() == (
            "brand new content"
        )

    async def test_404_missing_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v99",
            json={"content": "x"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 404

    async def test_400_invalid_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/Bad/versions/v1",
            json={"content": "x"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 400

    async def test_rejects_unknown_payload_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/versions/v1",
            json={"content": "x", "rogue_field": True},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 422
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_prompts.py::TestUpdateVersion -v
```

Expected: 5 fail.

- [ ] **Step 3: Add schema + handler**

Append to `src/flexloop/admin/routers/prompts.py`:

```python
class PromptVersionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str


@router.put(
    "/{name}/versions/{version}",
    response_model=PromptVersionResponse,
)
async def update_version(
    name: str,
    version: str,
    payload: PromptVersionUpdate,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PromptVersionResponse:
    try:
        prompt_service.write_version(prompts_dir, name, version, payload.content)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return PromptVersionResponse(
        name=name,
        version=version,
        content=payload.content,
        variables=prompt_service.extract_variables(payload.content),
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_admin_prompts.py::TestUpdateVersion -v
```

Expected: all 5 pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q
```

Expected: 367 green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/prompts.py tests/test_admin_prompts.py
git commit -m "feat(admin): PUT /api/admin/prompts/{name}/versions/{version}"
```

---

### Task 8: `POST /api/admin/prompts/{name}/versions` (clone active)

**Files:**
- Modify: `src/flexloop/admin/routers/prompts.py`
- Modify: `tests/test_admin_prompts.py`

- [ ] **Step 1: Append failing tests**

```python
class TestCreateVersionEndpoint:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.post(
            "/api/admin/prompts/plan_generation/versions",
            json={},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_clones_active_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/prompts/plan_generation/versions",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 201
        body = res.json()
        assert body["version"] == "v3"
        assert body["content"] == "v2 {{user_name}}"  # cloned from active v2
        assert body["variables"] == ["user_name"]
        # File on disk
        assert (prompts_tmp_dir / "plan_generation" / "v3.md").read_text() == (
            "v2 {{user_name}}"
        )

    async def test_404_missing_prompt(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.post(
            "/api/admin/prompts/nonexistent/versions",
            json={},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 404
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_prompts.py::TestCreateVersionEndpoint -v
```

Expected: 3 fail.

- [ ] **Step 3: Add the handler**

Append to `src/flexloop/admin/routers/prompts.py`:

```python
@router.post(
    "/{name}/versions",
    response_model=PromptVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    name: str,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> PromptVersionResponse:
    try:
        new_version, content = prompt_service.create_version(prompts_dir, name)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return PromptVersionResponse(
        name=name,
        version=new_version,
        content=content,
        variables=prompt_service.extract_variables(content),
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_admin_prompts.py::TestCreateVersionEndpoint -v
```

Expected: all 3 pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q
```

Expected: 370 green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/prompts.py tests/test_admin_prompts.py
git commit -m "feat(admin): POST /api/admin/prompts/{name}/versions (clone active)"
```

---

### Task 9: `PUT /api/admin/prompts/{name}/active` (set active version)

**Files:**
- Modify: `src/flexloop/admin/routers/prompts.py`
- Modify: `tests/test_admin_prompts.py`

- [ ] **Step 1: Append failing tests**

```python
class TestSetActiveEndpoint:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.put(
            "/api/admin/prompts/plan_generation/active",
            json={"version": "v1"},
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_sets_default_provider(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/active",
            json={"version": "v1"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        manifest = json.loads(
            (prompts_tmp_dir / "manifest.json").read_text()
        )
        assert manifest["plan_generation"]["default"] == "v1"

    async def test_explicit_provider(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/active",
            json={"version": "v1", "provider": "anthropic"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 200
        manifest = json.loads(
            (prompts_tmp_dir / "manifest.json").read_text()
        )
        assert manifest["plan_generation"]["default"] == "v2"
        assert manifest["plan_generation"]["anthropic"] == "v1"

    async def test_404_missing_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/active",
            json={"version": "v99"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 404

    async def test_400_invalid_provider(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.put(
            "/api/admin/prompts/plan_generation/active",
            json={"version": "v1", "provider": "../etc"},
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 400
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_prompts.py::TestSetActiveEndpoint -v
```

Expected: 5 fail.

- [ ] **Step 3: Add schema + handler**

Append to `src/flexloop/admin/routers/prompts.py`:

```python
class SetActiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    provider: str = "default"


class SetActiveResponse(BaseModel):
    name: str
    version: str
    provider: str


@router.put(
    "/{name}/active",
    response_model=SetActiveResponse,
)
async def set_active_version(
    name: str,
    payload: SetActiveRequest,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> SetActiveResponse:
    try:
        prompt_service.set_active(
            prompts_dir, name, payload.version, provider=payload.provider
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return SetActiveResponse(
        name=name, version=payload.version, provider=payload.provider
    )
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_admin_prompts.py::TestSetActiveEndpoint -v
```

Expected: all 5 pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q
```

Expected: 375 green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/prompts.py tests/test_admin_prompts.py
git commit -m "feat(admin): PUT /api/admin/prompts/{name}/active"
```

---

### Task 10: `GET /api/admin/prompts/{name}/diff` + `DELETE /versions/{version}`

**Files:**
- Modify: `src/flexloop/admin/routers/prompts.py`
- Modify: `tests/test_admin_prompts.py`

- [ ] **Step 1: Append failing tests (for both diff and delete)**

```python
class TestDiffEndpoint:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.get(
            "/api/admin/prompts/plan_generation/diff?from=v1&to=v2"
        )
        assert res.status_code == 401

    async def test_returns_unified_diff(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/plan_generation/diff?from=v1&to=v2",
            cookies=cookies,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "plan_generation"
        assert body["from_version"] == "v1"
        assert body["to_version"] == "v2"
        assert "--- v1" in body["diff"]
        assert "+++ v2" in body["diff"]
        assert "-v1 original content" in body["diff"]
        assert "+v2 {{user_name}}" in body["diff"]

    async def test_400_invalid_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/plan_generation/diff?from=bad&to=v2",
            cookies=cookies,
        )
        assert res.status_code == 400

    async def test_404_missing_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.get(
            "/api/admin/prompts/plan_generation/diff?from=v1&to=v99",
            cookies=cookies,
        )
        assert res.status_code == 404


class TestDeleteVersionEndpoint:
    async def test_requires_auth(
        self, client: AsyncClient, prompts_tmp_dir: Path
    ) -> None:
        res = await client.delete(
            "/api/admin/prompts/plan_generation/versions/v1",
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 401

    async def test_deletes_non_active(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            "/api/admin/prompts/plan_generation/versions/v1",
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 204
        assert not (
            prompts_tmp_dir / "plan_generation" / "v1.md"
        ).exists()

    async def test_409_when_active(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            "/api/admin/prompts/plan_generation/versions/v2",
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 409
        assert "still active" in res.json()["detail"]

    async def test_409_when_last_version(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        prompts_tmp_dir: Path,
    ) -> None:
        cookies = await _make_admin_and_cookie(db_session)
        res = await client.delete(
            "/api/admin/prompts/chat/versions/v1",
            cookies=cookies,
            headers={"Origin": ORIGIN},
        )
        assert res.status_code == 409
```

- [ ] **Step 2: Run to confirm failure**

```bash
uv run pytest tests/test_admin_prompts.py::TestDiffEndpoint tests/test_admin_prompts.py::TestDeleteVersionEndpoint -v
```

Expected: 8 fail.

- [ ] **Step 3: Add schemas + handlers**

Append to `src/flexloop/admin/routers/prompts.py`:

```python
class DiffResponse(BaseModel):
    name: str
    from_version: str
    to_version: str
    diff: str


@router.get(
    "/{name}/diff",
    response_model=DiffResponse,
)
async def get_diff(
    name: str,
    from_: str = Depends(lambda from_: from_),  # placeholder — replaced below
    to: str = "",
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> DiffResponse:
    # Query params are read via explicit Query parameters — rewrite the
    # signature to use FastAPI's Query dependency.
    ...
```

Wait — FastAPI doesn't easily allow `from` as a query param name because it's a Python keyword. Rewrite the handler to use `Query(..., alias="from")`:

```python
from fastapi import Query

@router.get(
    "/{name}/diff",
    response_model=DiffResponse,
)
async def get_diff(
    name: str,
    from_version: str = Query(..., alias="from"),
    to_version: str = Query(..., alias="to"),
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> DiffResponse:
    try:
        diff = prompt_service.diff_versions(
            prompts_dir, name, from_version, to_version
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
    return DiffResponse(
        name=name,
        from_version=from_version,
        to_version=to_version,
        diff=diff,
    )
```

Add the `Query` import at the top of `prompts.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
```

And the delete handler:

```python
@router.delete(
    "/{name}/versions/{version}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_version_endpoint(
    name: str,
    version: str,
    prompts_dir: Path = Depends(get_prompts_dir),
    _admin: AdminUser = Depends(require_admin),
) -> None:
    try:
        prompt_service.delete_version(prompts_dir, name, version)
    except Exception as exc:  # noqa: BLE001
        raise _translate(exc) from exc
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_admin_prompts.py::TestDiffEndpoint tests/test_admin_prompts.py::TestDeleteVersionEndpoint -v
```

Expected: all 8 pass.

- [ ] **Step 5: Full suite**

```bash
uv run pytest -q
```

Expected: 383 green.

- [ ] **Step 6: Commit**

```bash
git add src/flexloop/admin/routers/prompts.py tests/test_admin_prompts.py
git commit -m "feat(admin): GET /diff + DELETE /versions/{version}"
```

---

**End of Chunk 2.** All 7 backend endpoints are wired up with 20 integration tests and 33 unit tests. Next chunk moves to the frontend.

---

## Chunk 3: Frontend — scaffold + CodeMirror + tree + editor

### Task 11: Regenerate `admin-ui/src/lib/api.types.ts`

**Files:**
- Modify: `admin-ui/src/lib/api.types.ts`

Same pattern as prior phases.

- [ ] **Step 1: Start backend in background**

Use `run_in_background: true`:
```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b
uv run uvicorn flexloop.main:app --port 8000
```

- [ ] **Step 2: Regenerate types**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b/admin-ui
sleep 2
npm run codegen
```

Expected: diff shows new entries for `PromptInfoResponse`, `ListPromptsResponse`, `PromptVersionResponse`, `PromptVersionUpdate`, `SetActiveRequest`, `SetActiveResponse`, `DiffResponse`.

- [ ] **Step 3: Kill the backend + commit**

```bash
cd ..
git add admin-ui/src/lib/api.types.ts
git commit -m "chore(admin-ui): regenerate api.types.ts for prompts schemas"
```

---

### Task 12: Install CodeMirror frontend dependencies

**Files:**
- Modify: `admin-ui/package.json` + `package-lock.json`

- [ ] **Step 1: Install the packages**

```bash
cd admin-ui
npm install --legacy-peer-deps @uiw/react-codemirror @codemirror/lang-markdown @codemirror/theme-one-dark
```

Expected: three new entries in `package.json`, no build errors.

- [ ] **Step 2: Verify the build still works**

```bash
npm run build
```

Expected: succeeds. Bundle size grows a little.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/package.json admin-ui/package-lock.json
git commit -m "chore(admin-ui): install @uiw/react-codemirror + markdown + one-dark"
```

---

### Task 13: Create `PromptTree` left panel component

**Files:**
- Create: `admin-ui/src/components/prompts/PromptTree.tsx`

- [ ] **Step 1: Write the component**

```tsx
/**
 * Left-panel tree view for the prompts editor.
 *
 * Lists every prompt name from ListPromptsResponse. Clicking a name
 * expands to show its versions. The active version (by "default" provider)
 * is marked with a small green dot. Selecting a version calls the
 * ``onSelect`` callback with ``{name, version}``.
 */
import { useState } from "react";

import type { components } from "@/lib/api.types";

type PromptInfo = components["schemas"]["PromptInfoResponse"];

type Props = {
  prompts: PromptInfo[];
  selected: { name: string; version: string } | null;
  onSelect: (sel: { name: string; version: string }) => void;
};

export function PromptTree({ prompts, selected, onSelect }: Props) {
  const [expanded, setExpanded] = useState<Set<string>>(
    () => new Set(selected ? [selected.name] : []),
  );

  const toggle = (name: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  return (
    <div className="text-sm">
      {prompts.map((p) => {
        const isOpen = expanded.has(p.name);
        const activeDefault = p.active_by_provider?.default;
        return (
          <div key={p.name} className="mb-1">
            <button
              type="button"
              className="w-full text-left px-2 py-1 rounded hover:bg-muted font-medium flex items-center gap-2"
              onClick={() => toggle(p.name)}
            >
              <span className="text-xs text-muted-foreground w-3">
                {isOpen ? "▾" : "▸"}
              </span>
              <span className="flex-1">{p.name}</span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {p.versions.length}
              </span>
            </button>
            {isOpen && (
              <div className="ml-5 mt-1 space-y-0.5">
                {p.versions.map((v) => {
                  const isSelected =
                    selected?.name === p.name && selected?.version === v;
                  const isActive = activeDefault === v;
                  return (
                    <button
                      type="button"
                      key={v}
                      onClick={() => onSelect({ name: p.name, version: v })}
                      className={
                        "w-full text-left px-2 py-1 rounded flex items-center gap-2 " +
                        (isSelected ? "bg-muted font-medium" : "hover:bg-muted/50")
                      }
                    >
                      {isActive ? (
                        <span
                          className="inline-block h-2 w-2 rounded-full bg-green-500"
                          aria-label="active version"
                        />
                      ) : (
                        <span className="inline-block h-2 w-2" />
                      )}
                      <span className="tabular-nums">{v}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

```bash
cd admin-ui && npx tsc --noEmit
```

Expected: green.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/components/prompts/PromptTree.tsx
git commit -m "feat(admin-ui): PromptTree left-panel component"
```

---

### Task 14: Create `PromptsPage` with basic load + select + read-only editor

**Files:**
- Create: `admin-ui/src/pages/PromptsPage.tsx`

- [ ] **Step 1: Write the page**

```tsx
/**
 * Admin Prompts editor page.
 *
 * Two-panel layout: PromptTree on the left, CodeMirror editor on the right.
 * This first iteration is READ-ONLY — the editor shows the selected
 * version's content but the Save / New version / Set active / Diff
 * toolbar actions are added in a later task.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import CodeMirror from "@uiw/react-codemirror";
import { markdown } from "@codemirror/lang-markdown";
import { oneDark } from "@codemirror/theme-one-dark";

import { PromptTree } from "@/components/prompts/PromptTree";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type ListResponse = components["schemas"]["ListPromptsResponse"];
type VersionResponse = components["schemas"]["PromptVersionResponse"];

const LIST_KEY = ["admin", "prompts", "list"];

function versionKey(name: string, version: string) {
  return ["admin", "prompts", "version", name, version];
}

export function PromptsPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<{ name: string; version: string } | null>(
    null,
  );
  const [buffer, setBuffer] = useState<string>("");

  const listQuery = useQuery({
    queryKey: LIST_KEY,
    queryFn: () => api.get<ListResponse>("/api/admin/prompts"),
  });

  // Auto-select the first prompt's active version on first load
  useEffect(() => {
    if (selected !== null || !listQuery.data) return;
    const first = listQuery.data.prompts[0];
    if (first && first.versions.length > 0) {
      setSelected({
        name: first.name,
        version: first.active_by_provider?.default ?? first.versions[0],
      });
    }
  }, [listQuery.data, selected]);

  const versionQuery = useQuery({
    queryKey: selected
      ? versionKey(selected.name, selected.version)
      : ["admin", "prompts", "version", "none"],
    queryFn: () =>
      api.get<VersionResponse>(
        `/api/admin/prompts/${selected!.name}/versions/${selected!.version}`,
      ),
    enabled: selected !== null,
  });

  // Sync the buffer with the loaded version content
  useEffect(() => {
    if (versionQuery.data) {
      setBuffer(versionQuery.data.content);
    }
  }, [versionQuery.data]);

  const isDirty = useMemo(
    () => versionQuery.data && buffer !== versionQuery.data.content,
    [versionQuery.data, buffer],
  );

  if (listQuery.isLoading) {
    return <div className="p-6">Loading prompts…</div>;
  }
  if (listQuery.isError || !listQuery.data) {
    return <div className="p-6">Failed to load prompts.</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">Prompts</h1>
        <p className="text-sm text-muted-foreground">
          Edit AI prompt templates. Changes take effect on the next generation
          — no server restart required.
        </p>
      </div>

      <div className="grid grid-cols-[240px_1fr] gap-4 min-h-[60vh]">
        {/* Left panel: tree */}
        <div className="border rounded-md p-2 overflow-auto">
          <PromptTree
            prompts={listQuery.data.prompts}
            selected={selected}
            onSelect={setSelected}
          />
        </div>

        {/* Right panel: editor */}
        <div className="border rounded-md p-2 flex flex-col">
          {selected === null ? (
            <div className="text-sm text-muted-foreground p-4">
              Select a prompt version from the tree.
            </div>
          ) : versionQuery.isLoading ? (
            <div className="text-sm text-muted-foreground p-4">
              Loading version…
            </div>
          ) : versionQuery.isError || !versionQuery.data ? (
            <div className="text-sm text-red-500 p-4">
              Failed to load version.
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-2">
                <div className="font-medium">
                  {selected.name} / {selected.version}
                  {isDirty && (
                    <span className="ml-2 text-xs text-amber-600 dark:text-amber-400">
                      • unsaved
                    </span>
                  )}
                </div>
              </div>
              <div className="flex-1 min-h-0 overflow-hidden border rounded">
                <CodeMirror
                  value={buffer}
                  extensions={[markdown()]}
                  theme={oneDark}
                  onChange={(v) => setBuffer(v)}
                  height="60vh"
                />
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
  // qc is unused in this iteration — toolbar actions in a later task will use it
  void qc;
}
```

- [ ] **Step 2: Type-check**

```bash
cd admin-ui && npx tsc --noEmit
```

Expected: green. If `void qc` causes a "never used" warning, remove the unused `const qc` entirely and add it back in the next task.

- [ ] **Step 3: Commit**

```bash
cd ..
git add admin-ui/src/pages/PromptsPage.tsx
git commit -m "feat(admin-ui): PromptsPage scaffold with tree + read-only editor"
```

---

### Task 15: Wire up `/ai/prompts` route and enable sidebar item

**Files:**
- Modify: `admin-ui/src/App.tsx`
- Modify: `admin-ui/src/components/AppSidebar.tsx`

- [ ] **Step 1: Add route in App.tsx**

Import:
```tsx
import { PromptsPage } from "@/pages/PromptsPage";
```

Route inside the authenticated layout, near the other `/ai/*` routes:
```tsx
<Route path="ai/prompts" element={<PromptsPage />} />
```

- [ ] **Step 2: Enable sidebar item**

In `admin-ui/src/components/AppSidebar.tsx` find the Prompts entry:

```tsx
{ label: "Prompts", to: "/ai/prompts", icon: FileText, disabled: true },
```

Remove `disabled: true`:

```tsx
{ label: "Prompts", to: "/ai/prompts", icon: FileText },
```

- [ ] **Step 3: Build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/App.tsx admin-ui/src/components/AppSidebar.tsx
git commit -m "feat(admin-ui): enable Prompts sidebar item and /ai/prompts route"
```

---

**End of Chunk 3.** The Prompts page loads, displays the tree, and shows the selected version's content in a CodeMirror editor. Saving and version management come next.

---

## Chunk 4: Frontend — toolbar + variable inspector + diff dialog

### Task 16: Add `VariableInspector` right sidebar + wire into `PromptsPage`

**Files:**
- Create: `admin-ui/src/components/prompts/VariableInspector.tsx`
- Modify: `admin-ui/src/pages/PromptsPage.tsx`

- [ ] **Step 1: Create the variable inspector**

```tsx
/**
 * Right-sidebar variable inspector.
 *
 * Parses ``{{variable_name}}`` from the current editor buffer and lists
 * them so the admin knows what context the prompt expects. Updates live
 * as the user types (no backend round-trip).
 */
const VAR_RE = /\{\{(\w+)\}\}/g;

function extractVariables(content: string): string[] {
  const seen = new Set<string>();
  for (const match of content.matchAll(VAR_RE)) {
    seen.add(match[1]);
  }
  return [...seen].sort();
}

type Props = {
  content: string;
};

export function VariableInspector({ content }: Props) {
  const variables = extractVariables(content);
  return (
    <div className="border rounded-md p-3 text-sm space-y-2">
      <div className="font-medium">Variables</div>
      {variables.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          No <code>{"{{variables}}"}</code> in this template.
        </p>
      ) : (
        <ul className="space-y-1">
          {variables.map((v) => (
            <li key={v}>
              <code className="text-xs px-1 py-0.5 rounded bg-muted">
                {`{{${v}}}`}
              </code>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire it into `PromptsPage`**

Change the layout grid to `[240px_1fr_220px]` and render the inspector in the third column:

In `PromptsPage.tsx`, find:

```tsx
<div className="grid grid-cols-[240px_1fr] gap-4 min-h-[60vh]">
```

Change to:

```tsx
<div className="grid grid-cols-[240px_1fr_220px] gap-4 min-h-[60vh]">
```

And after the editor panel's closing `</div>`, add the inspector column:

```tsx
{/* Right sidebar: variables */}
<div>
  {selected && <VariableInspector content={buffer} />}
</div>
```

Add the import:
```tsx
import { VariableInspector } from "@/components/prompts/VariableInspector";
```

- [ ] **Step 3: Type-check + commit**

```bash
cd admin-ui && npx tsc --noEmit
cd ..
git add admin-ui/src/components/prompts/VariableInspector.tsx admin-ui/src/pages/PromptsPage.tsx
git commit -m "feat(admin-ui): VariableInspector sidebar with live regex"
```

---

### Task 17: `PromptToolbar` with Save / New version / Set active buttons

**Files:**
- Create: `admin-ui/src/components/prompts/PromptToolbar.tsx`
- Modify: `admin-ui/src/pages/PromptsPage.tsx`

- [ ] **Step 1: Create the toolbar component**

```tsx
/**
 * Toolbar above the prompt editor.
 *
 * Save: PUT current buffer to the selected version
 * New version: POST to /versions — clones active
 * Set as active: PUT /active with the selected version
 * Diff: opens the DiffDialog
 */
import { Button } from "@/components/ui/button";

type Props = {
  isDirty: boolean;
  isSaving: boolean;
  isCreating: boolean;
  isSettingActive: boolean;
  canSetActive: boolean;
  onSave: () => void;
  onNewVersion: () => void;
  onSetActive: () => void;
  onOpenDiff: () => void;
};

export function PromptToolbar({
  isDirty,
  isSaving,
  isCreating,
  isSettingActive,
  canSetActive,
  onSave,
  onNewVersion,
  onSetActive,
  onOpenDiff,
}: Props) {
  return (
    <div className="flex items-center gap-2 pb-2 border-b">
      <Button
        size="sm"
        onClick={onSave}
        disabled={!isDirty || isSaving}
      >
        {isSaving ? "Saving…" : "Save"}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={onNewVersion}
        disabled={isCreating}
      >
        {isCreating ? "Cloning…" : "New version"}
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={onSetActive}
        disabled={!canSetActive || isSettingActive}
      >
        {isSettingActive ? "Setting…" : "Set as active"}
      </Button>
      <Button size="sm" variant="ghost" onClick={onOpenDiff}>
        Diff…
      </Button>
    </div>
  );
}
```

- [ ] **Step 2: Wire the toolbar into `PromptsPage`**

Add the necessary imports and mutations inside `PromptsPage`:

```tsx
import { useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { PromptToolbar } from "@/components/prompts/PromptToolbar";

// ... inside PromptsPage, after the existing useQuery calls:

const save = useMutation({
  mutationFn: ({ name, version, content }: { name: string; version: string; content: string }) =>
    api.put<VersionResponse>(
      `/api/admin/prompts/${name}/versions/${version}`,
      { content },
    ),
  onSuccess: (_data, variables) => {
    toast.success("Saved");
    qc.invalidateQueries({ queryKey: versionKey(variables.name, variables.version) });
  },
  onError: (e) => toast.error(e instanceof Error ? e.message : "Save failed"),
});

const createVersion = useMutation({
  mutationFn: ({ name }: { name: string }) =>
    api.post<VersionResponse>(`/api/admin/prompts/${name}/versions`, {}),
  onSuccess: (data, variables) => {
    toast.success(`Created ${data.version}`);
    qc.invalidateQueries({ queryKey: LIST_KEY });
    setSelected({ name: variables.name, version: data.version });
  },
  onError: (e) => toast.error(e instanceof Error ? e.message : "Create failed"),
});

const setActive = useMutation({
  mutationFn: ({ name, version }: { name: string; version: string }) =>
    api.put(`/api/admin/prompts/${name}/active`, { version, provider: "default" }),
  onSuccess: () => {
    toast.success("Active version updated");
    qc.invalidateQueries({ queryKey: LIST_KEY });
  },
  onError: (e) => toast.error(e instanceof Error ? e.message : "Set active failed"),
});
```

Between the "selected prompt" header and the CodeMirror in the editor panel, add:

```tsx
{selected && versionQuery.data && (
  <PromptToolbar
    isDirty={!!isDirty}
    isSaving={save.isPending}
    isCreating={createVersion.isPending}
    isSettingActive={setActive.isPending}
    canSetActive={
      // Can set active only if this version isn't already the default active
      listQuery.data.prompts.find((p) => p.name === selected.name)?.active_by_provider?.default
        !== selected.version
    }
    onSave={() => save.mutate({
      name: selected.name,
      version: selected.version,
      content: buffer,
    })}
    onNewVersion={() => createVersion.mutate({ name: selected.name })}
    onSetActive={() => setActive.mutate({
      name: selected.name,
      version: selected.version,
    })}
    onOpenDiff={() => setDiffOpen(true)}
  />
)}
```

And add the diff-dialog state near the top of the component:

```tsx
const [diffOpen, setDiffOpen] = useState(false);
```

Remove the `void qc;` line at the bottom of the component (qc is now used).

- [ ] **Step 3: Type-check**

```bash
cd admin-ui && npx tsc --noEmit
```

Expected: green.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/components/prompts/PromptToolbar.tsx admin-ui/src/pages/PromptsPage.tsx
git commit -m "feat(admin-ui): PromptToolbar + save/new-version/set-active mutations"
```

---

### Task 18: `DiffDialog` modal

**Files:**
- Create: `admin-ui/src/components/prompts/DiffDialog.tsx`
- Modify: `admin-ui/src/pages/PromptsPage.tsx`

- [ ] **Step 1: Create the dialog**

```tsx
/**
 * Modal showing the unified diff between the current version and another
 * version selected from a dropdown.
 *
 * Uses the shadcn Dialog primitive (already installed). Diff text renders
 * as a <pre> with per-line CSS coloring: `+` green, `-` red, `@@` gray.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { components } from "@/lib/api.types";

type DiffResponse = components["schemas"]["DiffResponse"];

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  name: string;
  currentVersion: string;
  availableVersions: string[];
};

function renderDiffLine(line: string, i: number) {
  let className = "text-muted-foreground";
  if (line.startsWith("+") && !line.startsWith("+++")) {
    className = "text-green-600 dark:text-green-400";
  } else if (line.startsWith("-") && !line.startsWith("---")) {
    className = "text-red-600 dark:text-red-400";
  } else if (line.startsWith("@@")) {
    className = "text-blue-600 dark:text-blue-400";
  }
  return (
    <div key={i} className={className}>
      {line || " "}
    </div>
  );
}

export function DiffDialog({
  open,
  onOpenChange,
  name,
  currentVersion,
  availableVersions,
}: Props) {
  // Default to comparing against the version just before the current one
  const otherVersions = availableVersions.filter((v) => v !== currentVersion);
  const [from, setFrom] = useState<string>(
    () => otherVersions[0] ?? currentVersion,
  );

  const diffQuery = useQuery({
    queryKey: ["admin", "prompts", "diff", name, from, currentVersion],
    queryFn: () =>
      api.get<DiffResponse>(
        `/api/admin/prompts/${name}/diff?from=${from}&to=${currentVersion}`,
      ),
    enabled: open && from !== currentVersion,
  });

  const lines = useMemo(
    () => (diffQuery.data?.diff ?? "").split("\n"),
    [diffQuery.data],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>
            Diff: {name} / {from} → {currentVersion}
          </DialogTitle>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <span className="text-sm">Compare against:</span>
          <Select value={from} onValueChange={setFrom}>
            <SelectTrigger className="w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {otherVersions.map((v) => (
                <SelectItem key={v} value={v}>
                  {v}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <pre className="font-mono text-xs whitespace-pre-wrap max-h-[50vh] overflow-auto bg-muted/30 p-3 rounded">
          {diffQuery.isLoading && "Loading diff…"}
          {diffQuery.isError && "Failed to load diff."}
          {diffQuery.data && lines.map((l, i) => renderDiffLine(l, i))}
          {!diffQuery.isLoading && lines.length <= 1 && diffQuery.data?.diff === "" && (
            <span className="text-muted-foreground">No differences.</span>
          )}
        </pre>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Wire the dialog into `PromptsPage`**

Add the import:

```tsx
import { DiffDialog } from "@/components/prompts/DiffDialog";
```

At the end of the JSX return (after the closing grid `</div>`), render the dialog:

```tsx
{selected && versionQuery.data && (
  <DiffDialog
    open={diffOpen}
    onOpenChange={setDiffOpen}
    name={selected.name}
    currentVersion={selected.version}
    availableVersions={
      listQuery.data.prompts.find((p) => p.name === selected.name)?.versions ?? []
    }
  />
)}
```

- [ ] **Step 3: Type-check + build**

```bash
cd admin-ui && npx tsc --noEmit && npm run build
```

Expected: both green.

- [ ] **Step 4: Commit**

```bash
cd ..
git add admin-ui/src/components/prompts/DiffDialog.tsx admin-ui/src/pages/PromptsPage.tsx
git commit -m "feat(admin-ui): DiffDialog modal with version selector + colored diff"
```

---

**End of Chunk 4.** Prompts editor is feature-complete for phase 4b scope. Next chunk runs smoke + merge.

---

## Chunk 5: Smoke test and merge

### Task 19: Write the smoke test checklist

**Files:**
- Create: `docs/admin-dashboard-phase4b-smoke-test.md` (at parent FlexLoop level)

- [ ] **Step 1: Write the checklist**

```markdown
# Phase 4b (Prompt editor) smoke test

Manual checklist + automated Playwright subset.

## Environment

- [ ] Backend running: `uv run uvicorn flexloop.main:app --port 8000`
- [ ] Admin UI built: `cd admin-ui && npm run build`
- [ ] `prompts/` directory has at least 2 prompts (`plan_generation`, `chat` or similar) with at least one version each
- [ ] Logged in as admin

## Prompts page

- [ ] Navigate to /admin/ai/prompts — sidebar item enabled, page loads
- [ ] Left tree shows all prompts, expandable
- [ ] Clicking a prompt expands to show versions with a green dot on the active version
- [ ] Clicking a version loads its content in the editor
- [ ] Editing the buffer shows the "• unsaved" indicator
- [ ] Variables sidebar updates live as you type `{{foo}}`

## Save

- [ ] Click Save with a dirty buffer — toast "Saved"
- [ ] Refresh the page — the saved content persists
- [ ] Save with no changes — button is disabled

## New version

- [ ] Click "New version" on a prompt with 2 versions — toast "Created v3"
- [ ] Left tree shows the new v3 with the same content as the active version
- [ ] Selected version auto-switches to v3

## Set as active

- [ ] Click "Set as active" on a non-active version — toast, tree's green dot moves
- [ ] Button becomes disabled (the version is now already active)
- [ ] Verify DB: `cat prompts/manifest.json` shows the new active version for "default"

## Diff

- [ ] Click "Diff…" — modal opens
- [ ] Compare-against dropdown lists all other versions
- [ ] Diff text renders with colored lines (+ green, - red, @@ blue)
- [ ] Close button dismisses the modal

## Delete (via direct API for now — no UI button in phase 4b scope)

- [ ] `curl -X DELETE -b cookies.txt http://localhost:8000/api/admin/prompts/foo/versions/v1` returns 204 for a non-active version
- [ ] Returns 409 for the active version
- [ ] Returns 409 for the last remaining version

## Security

- [ ] `curl http://localhost:8000/api/admin/prompts/../etc/passwd/versions/v1` returns 400 (invalid name)
- [ ] `curl http://localhost:8000/api/admin/prompts/plan_generation/versions/../../etc/passwd` returns 400 (invalid version)

## Regression checks

- [ ] iOS-facing endpoints still work: `curl http://localhost:8000/api/plans?user_id=1`
- [ ] Phase 4a Config page still loads at /admin/ai/config
- [ ] Generating a plan via `flexloop.routers.ai` still works — the existing PromptManager reads from the same filesystem so edits through phase 4b are picked up on the next generation

## Automated

- [ ] `uv run pytest -q` — full suite green (expected 383 tests)
- [ ] `cd admin-ui && npm run build` — succeeds
- [ ] Optional: `/tmp/smoke_phase4b.py` Playwright script
```

- [ ] **Step 2: Commit to the parent FlexLoop repo**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add docs/admin-dashboard-phase4b-smoke-test.md
git commit -m "docs(admin): phase 4b smoke test checklist"
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b
```

---

### Task 20: Run the automated Playwright smoke test

Phase 3 and 4a established a pattern: seed a fresh DB + prompts dir, start the backend with `with_server.py`, run a headless Playwright script. The script for 4b should cover:

1. Login
2. Navigate to /ai/prompts — page loads with tree
3. Click plan_generation → v2 — editor shows content
4. Type something, verify "• unsaved" appears, Save, verify toast + indicator clears
5. Click "New version" — verify v3 appears in the tree, auto-selected
6. Click "Set as active" on v1 — verify the green dot moves (via manifest.json on disk)
7. Open Diff dialog, select v1 vs v2, verify diff renders, close
8. Regression: GET /api/plans?user_id=1 returns 200

The prompts directory for the test should be a scratch copy so the smoke test doesn't modify the real `prompts/` in the worktree. Use an environment variable (e.g. `PROMPTS_DIR_OVERRIDE`) or override `get_prompts_dir` in the uvicorn process... actually this is awkward because `get_prompts_dir` is Python-level and the test runs the real backend. Simpler: **copy the real prompts/ into a tmp dir and start uvicorn with its working dir at the tmp parent**, OR add a `PROMPTS_DIR` env var that the router reads.

Simplest: **override `_DEFAULT_PROMPTS_DIR`** via an env var in the router. Update `get_prompts_dir` to:

```python
import os
_DEFAULT_PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts")).resolve()
```

This is a small change in the router source. Do this in Task 20 Step 0 before writing the smoke script.

- [ ] **Step 0: Support `PROMPTS_DIR` env var in the router**

Edit `src/flexloop/admin/routers/prompts.py` and replace:

```python
_DEFAULT_PROMPTS_DIR = Path("prompts").resolve()
```

With:

```python
import os
_DEFAULT_PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", "prompts")).resolve()
```

Run the existing tests to confirm nothing broke:

```bash
uv run pytest tests/test_admin_prompts.py -q
```

Commit:
```bash
git add src/flexloop/admin/routers/prompts.py
git commit -m "feat(admin): PROMPTS_DIR env var for test/smoke overrides"
```

- [ ] **Step 1: Create `/tmp/seed_phase4b_smoke.py`** that creates:
  - A scratch `/tmp/flexloop-phase4b-prompts/` directory with 2 prompts (plan_generation v1+v2, chat v1) and a `manifest.json`
  - An admin user in the DB (`smoketest / smoketest123`) via `init_db` + the seed migration

(Mirror `/tmp/seed_phase4a_smoke.py` structure; add file/dir creation for the prompts tmp dir.)

- [ ] **Step 2: Create `/tmp/smoke_phase4b.py`** (Playwright script) covering the 8 steps above.

- [ ] **Step 3: Reuse or recreate the playwright venv**

```bash
if [ ! -x /tmp/phase4a-playwright-venv/bin/python3 ]; then
  python3 -m venv /tmp/phase4b-playwright-venv
  /tmp/phase4b-playwright-venv/bin/pip install playwright
  /tmp/phase4b-playwright-venv/bin/playwright install chromium
else
  ln -sf /tmp/phase4a-playwright-venv /tmp/phase4b-playwright-venv
fi
```

- [ ] **Step 4: Run the smoke**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b
rm -f /tmp/flexloop-phase4b-smoke.db
rm -rf /tmp/flexloop-phase4b-prompts
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4b-smoke.db' \
  PROMPTS_DIR=/tmp/flexloop-phase4b-prompts \
  uv run python /tmp/seed_phase4b_smoke.py
DATABASE_URL='sqlite+aiosqlite:////tmp/flexloop-phase4b-smoke.db' \
  PROMPTS_DIR=/tmp/flexloop-phase4b-prompts \
  python3 /Users/flyingchickens/.claude/plugins/cache/anthropic-agent-skills/example-skills/b0cbd3df1533/skills/webapp-testing/scripts/with_server.py \
  --server 'uv run uvicorn flexloop.main:app --port 8000' \
  --port 8000 --timeout 60 \
  -- /tmp/phase4b-playwright-venv/bin/python3 /tmp/smoke_phase4b.py
```

Expected: ALL SMOKE TESTS PASSED.

- [ ] **Step 5: Mark the checklist as executed** — prepend a "Automated Playwright smoke executed YYYY-MM-DD — all checks ✅" note to the checklist and commit the update to the parent FlexLoop repo's docs.

---

### Task 21: Merge `feat/admin-dashboard-phase4b-prompts` to main

- [ ] **Step 1: Verify clean + commit count**

```bash
cd /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b
git status
git log --oneline main..HEAD | wc -l
```

Expected: clean, ~20+ commits.

- [ ] **Step 2: Fast-forward merge from the flexloop-server root**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git checkout main
git merge --ff-only feat/admin-dashboard-phase4b-prompts
```

- [ ] **Step 3: Full suite on main**

```bash
uv run pytest -q
```

Expected: 383 tests green.

- [ ] **Step 4: Push main**

```bash
git push origin main
```

- [ ] **Step 5: Bump parent submodule**

```bash
cd /Users/flyingchickens/Projects/FlexLoop
git add flexloop-server
git commit -m "chore: bump flexloop-server to admin dashboard phase 4b"
```

- [ ] **Step 6: Clean up worktree + feature branch**

```bash
cd /Users/flyingchickens/Projects/FlexLoop/flexloop-server
git worktree remove /Users/flyingchickens/Projects/flexloop-server-admin-dashboard-phase4b
git branch -d feat/admin-dashboard-phase4b-prompts
```

- [ ] **Step 7: Update memory status file**

Edit `/Users/flyingchickens/.claude/projects/-Users-flyingchickens-Projects-FlexLoop/memory/project_admin_dashboard_status.md`:
- Mark phase 4b COMPLETE with today's date
- Move phase 4c or 4d into "next up"

---

**End of Chunk 5.** Plan 4b is shipped: filesystem-backed prompt editor with CodeMirror, version management, diff view, and variable inspector.

---

## Summary

**Backend deliverables:**
- `src/flexloop/admin/prompt_service.py` — pure Python CRUD over the prompts filesystem (list, read, write with `fcntl.flock`, clone, set active, delete, diff, extract variables)
- `src/flexloop/admin/routers/prompts.py` — 7 admin endpoints + `get_prompts_dir` dependency (overridable via `PROMPTS_DIR` env var or FastAPI dependency override for tests)
- `src/flexloop/main.py` — register router
- 2 test files (~53 tests total): `test_admin_prompt_service.py` (33 unit tests), `test_admin_prompts.py` (20 integration tests)

**Frontend deliverables:**
- `admin-ui/src/pages/PromptsPage.tsx` — two-panel layout with tree, editor, toolbar, variables sidebar
- `admin-ui/src/components/prompts/` — 4 sub-components: `PromptTree`, `PromptToolbar`, `VariableInspector`, `DiffDialog`
- `admin-ui/package.json` — 3 new dependencies (`@uiw/react-codemirror`, `@codemirror/lang-markdown`, `@codemirror/theme-one-dark`)
- `admin-ui/src/App.tsx` + `AppSidebar.tsx` — new route + enabled sidebar item
- `admin-ui/src/lib/api.types.ts` — regenerated

**Docs:** `docs/admin-dashboard-phase4b-smoke-test.md`

**End state:** operators can edit AI prompts through a CodeMirror editor with syntax highlighting, manage versions (clone, set active, delete, diff), and see the variables each template references — without touching SSH or git. Next sub-plan: 4c (AI Playground) which will add the "Open in playground →" button back to this page's toolbar.
