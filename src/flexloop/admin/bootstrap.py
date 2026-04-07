"""Admin bootstrap CLI — create the first admin and reset passwords.

Usage:
    uv run python -m flexloop.admin.bootstrap create-admin <username>
    uv run python -m flexloop.admin.bootstrap reset-admin-password <username>

Both commands prompt for a password interactively (using getpass for no echo).
"""
import asyncio
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from flexloop.admin.auth import hash_password
from flexloop.db.engine import async_session
from flexloop.models.admin_user import AdminUser


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


async def _cli_create_admin(username: str) -> None:
    password = _prompt_password()
    async with async_session() as db:
        try:
            user = await create_admin_user(db, username, password)
            await db.commit()
            print(f"Created admin user {user.username!r} (id={user.id}).")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


async def _cli_reset_admin_password(username: str) -> None:
    password = _prompt_password()
    async with async_session() as db:
        try:
            await reset_admin_password(db, username, password)
            await db.commit()
            print(f"Password reset for {username!r}.")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage:\n  python -m flexloop.admin.bootstrap create-admin <username>")
        print("  python -m flexloop.admin.bootstrap reset-admin-password <username>")
        sys.exit(2)

    command, username = sys.argv[1], sys.argv[2]
    if command == "create-admin":
        asyncio.run(_cli_create_admin(username))
    elif command == "reset-admin-password":
        asyncio.run(_cli_reset_admin_password(username))
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
