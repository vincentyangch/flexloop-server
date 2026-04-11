"""Admin bootstrap CLI — create admins, reset passwords, set allowed origins.

Usage:
    uv run python -m flexloop.admin.bootstrap create-admin <username>
    uv run python -m flexloop.admin.bootstrap create-admin <username> --password-env FLEXLOOP_ADMIN_PW
    uv run python -m flexloop.admin.bootstrap reset-admin-password <username>
    uv run python -m flexloop.admin.bootstrap reset-admin-password <username> --password-env FLEXLOOP_ADMIN_PW
    uv run python -m flexloop.admin.bootstrap set-allowed-origins "https://foo.example.com,http://localhost:8000"

Password commands prompt interactively (getpass) unless --password-env is
given. --password-env reads the password from the named environment
variable — useful for agent-driven deploys where there is no TTY.
"""
import asyncio
import getpass
import os
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import hash_password
from flexloop.db.engine import async_session
from flexloop.models.admin_user import AdminUser
from flexloop.models.app_settings import AppSettings


async def create_admin_user(db: AsyncSession, username: str, password: str) -> AdminUser:
    """Create a new admin user. Raises ValueError if username exists."""
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    if result.scalar_one_or_none() is not None:
        raise ValueError(f"admin user {username!r} already exists")
    user = AdminUser(username=username, password_hash=hash_password(password))
    db.add(user)
    await db.flush()
    return user


async def reset_admin_password(db: AsyncSession, username: str, new_password: str) -> None:
    """Reset an existing admin's password. Raises ValueError if username unknown."""
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"admin user {username!r} not found")
    user.password_hash = hash_password(new_password)
    await db.flush()


async def set_allowed_origins(db: AsyncSession, origins: list[str]) -> None:
    """Overwrite ``app_settings.admin_allowed_origins`` on the singleton row.

    Raises ValueError if the row does not exist — callers should start the
    server once first to run the seed migration.
    """
    result = await db.execute(select(AppSettings).where(AppSettings.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        raise ValueError(
            "app_settings row not found — start the app once to run migrations first"
        )
    row.admin_allowed_origins = origins
    await db.flush()


def _read_password_from_env(var_name: str) -> str:
    """Read a password from an environment variable.

    Agent-deploy helper: lets non-interactive callers pass the admin
    password without a TTY.

    Raises ValueError if the variable is unset or the value is shorter
    than 8 characters.
    """
    pw = os.environ.get(var_name)
    if pw is None:
        raise ValueError(f"environment variable {var_name!r} is not set")
    if len(pw) < 8:
        raise ValueError(f"password from ${var_name} must be at least 8 characters")
    return pw


def _parse_origins(csv: str) -> list[str]:
    """Parse a comma-separated list of origins, strip whitespace, validate schemes.

    Raises ValueError if the list is empty after stripping, or if any
    entry lacks an ``http://`` or ``https://`` prefix.
    """
    origins = [o.strip() for o in csv.split(",") if o.strip()]
    if not origins:
        raise ValueError("at least one origin required")
    for origin in origins:
        if not (origin.startswith("http://") or origin.startswith("https://")):
            raise ValueError(
                f"origin must start with http:// or https://: {origin!r}"
            )
    return origins


def _prompt_password() -> str:
    while True:
        pw = getpass.getpass("Password: ")
        if len(pw) < 8:
            print("Password must be at least 8 characters. Try again.")
            continue
        confirm = getpass.getpass("Confirm: ")
        if pw != confirm:
            print("Passwords don't match. Try again.")
            continue
        return pw


def _resolve_password(password_env: str | None) -> str:
    """Return the password from --password-env if given, else prompt."""
    if password_env is not None:
        return _read_password_from_env(password_env)
    return _prompt_password()


async def _cli_create_admin(username: str, password_env: str | None = None) -> None:
    try:
        password = _resolve_password(password_env)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    async with async_session() as db:
        try:
            user = await create_admin_user(db, username, password)
            await db.commit()
            print(f"Created admin user {user.username!r} (id={user.id}).")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


async def _cli_reset_admin_password(username: str, password_env: str | None = None) -> None:
    try:
        password = _resolve_password(password_env)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    async with async_session() as db:
        try:
            await reset_admin_password(db, username, password)
            await db.commit()
            print(f"Password reset for {username!r}.")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


async def _cli_set_allowed_origins(csv: str) -> None:
    try:
        origins = _parse_origins(csv)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    async with async_session() as db:
        try:
            await set_allowed_origins(db, origins)
            await db.commit()
            print(f"Set admin_allowed_origins to: {origins}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


_USAGE = """\
Usage:
  python -m flexloop.admin.bootstrap create-admin <username> [--password-env VAR]
  python -m flexloop.admin.bootstrap reset-admin-password <username> [--password-env VAR]
  python -m flexloop.admin.bootstrap set-allowed-origins "<comma-separated origins>"

Flags:
  --password-env VAR    Read the password from environment variable VAR
                        instead of prompting (for non-interactive deploys).
"""


def _extract_flag(args: list[str], flag: str) -> tuple[list[str], str | None]:
    """Pop ``--flag VALUE`` from ``args`` and return (remaining, value or None).

    Raises SystemExit if the flag is given without a following value.
    """
    if flag not in args:
        return args, None
    i = args.index(flag)
    if i + 1 >= len(args):
        print(f"Error: {flag} requires a value", file=sys.stderr)
        sys.exit(2)
    value = args[i + 1]
    remaining = args[:i] + args[i + 2 :]
    return remaining, value


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(_USAGE, file=sys.stderr)
        sys.exit(2)

    command = args[0]
    args = args[1:]

    if command == "create-admin":
        args, password_env = _extract_flag(args, "--password-env")
        if not args:
            print(_USAGE, file=sys.stderr)
            sys.exit(2)
        username = args[0]
        asyncio.run(_cli_create_admin(username, password_env=password_env))
    elif command == "reset-admin-password":
        args, password_env = _extract_flag(args, "--password-env")
        if not args:
            print(_USAGE, file=sys.stderr)
            sys.exit(2)
        username = args[0]
        asyncio.run(_cli_reset_admin_password(username, password_env=password_env))
    elif command == "set-allowed-origins":
        if not args:
            print(_USAGE, file=sys.stderr)
            sys.exit(2)
        asyncio.run(_cli_set_allowed_origins(args[0]))
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        print(_USAGE, file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
