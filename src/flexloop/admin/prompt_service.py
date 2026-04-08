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
from collections.abc import Callable
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
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PromptServiceError(
            f"manifest at {path} is corrupted: {exc}"
        ) from exc


def _update_manifest_locked(
    prompts_dir: Path,
    mutator: "Callable[[dict], None]",
) -> None:
    """Read-modify-write the manifest atomically under an exclusive lock.

    ``mutator`` receives the parsed manifest dict and mutates it in place.
    The mutated dict is then written back to disk. The whole read-modify-
    write cycle happens inside a single ``LOCK_EX`` section so concurrent
    callers cannot race on the read step.
    """
    path = _manifest_path(prompts_dir)
    # Ensure the file exists so we can open it in r+ mode.
    if not path.exists():
        path.write_text("{}")
    with open(path, "r+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            raw = f.read()
            try:
                manifest = json.loads(raw) if raw else {}
            except json.JSONDecodeError as exc:
                raise PromptServiceError(
                    f"manifest at {path} is corrupted: {exc}"
                ) from exc
            mutator(manifest)
            f.seek(0)
            f.truncate()
            json.dump(manifest, f, indent=2)
        finally:
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
    try:
        return path.read_text()
    except OSError as exc:
        raise PromptServiceError(
            f"failed to read {path}: {exc}"
        ) from exc


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
    try:
        with open(path, "r+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.seek(0)
            f.truncate()
            f.write(content)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise PromptServiceError(
            f"failed to write {path}: {exc}"
        ) from exc


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
    try:
        source_content = source_path.read_text()
    except OSError as exc:
        raise PromptServiceError(
            f"failed to read {source_path}: {exc}"
        ) from exc

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
    try:
        with open(new_path, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(source_content)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError as exc:
        raise PromptServiceError(
            f"failed to create {new_path}: {exc}"
        ) from exc

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

    def _apply(manifest: dict) -> None:
        manifest.setdefault(name, {})[provider] = version

    _update_manifest_locked(prompts_dir, _apply)


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
