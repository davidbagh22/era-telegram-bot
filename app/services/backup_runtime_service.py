from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import make_url

from app.config import Settings


class BackupSnapshotError(RuntimeError):
    pass


@dataclass(slots=True)
class DatabaseSnapshot:
    path: Path
    checksum_sha256: str
    size_bytes: int


def derive_backup_encryption_key(settings: Settings) -> str:
    root = settings.miniapp_auth_secret.strip()
    if not root:
        raise BackupSnapshotError("backup_key_root_unavailable")
    return hmac.new(
        root.encode("utf-8"),
        b"era-platform-backup-encryption-v1",
        hashlib.sha256,
    ).hexdigest()


def _pg_environment(database_url: str) -> dict[str, str]:
    url = make_url(database_url)
    if not url.host or not url.database or not url.username:
        raise BackupSnapshotError("database_url_incomplete")
    env = os.environ.copy()
    env["PGHOST"] = url.host
    env["PGPORT"] = str(url.port or 5432)
    env["PGDATABASE"] = url.database
    env["PGUSER"] = url.username
    if url.password is not None:
        env["PGPASSWORD"] = url.password
    sslmode = url.query.get("sslmode")
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)
    return env


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _capture(command: str, *args: str, env: dict[str, str] | None = None) -> str:
    try:
        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise BackupSnapshotError(f"{command}_unavailable") from exc
    stdout, _ = await process.communicate()
    if process.returncode != 0:
        raise BackupSnapshotError(f"{command}_preflight_failed")
    return stdout.decode("utf-8", errors="replace").strip()


async def verify_pg_dump_compatibility(database_url: str) -> tuple[int, int]:
    """Return safe client/server majors without exposing connection material."""
    env = _pg_environment(database_url)
    client_text = await _capture("pg_dump", "--version", env=env)
    match = re.search(r"(\d+)(?:\.\d+)?$", client_text)
    if not match:
        raise BackupSnapshotError("pg_dump_version_unknown")
    client_major = int(match.group(1))

    server_version_num = await _capture(
        "psql",
        "--no-psqlrc",
        "--tuples-only",
        "--no-align",
        "--command=SHOW server_version_num",
        env=env,
    )
    if not server_version_num.isdigit():
        raise BackupSnapshotError("postgres_server_version_unknown")
    raw = int(server_version_num)
    server_major = raw // 10000 if raw >= 100000 else raw // 10000
    if client_major < server_major:
        raise BackupSnapshotError(
            f"pg_dump_client_too_old_client_{client_major}_server_{server_major}"
        )
    return client_major, server_major


async def create_database_snapshot(database_url: str) -> DatabaseSnapshot:
    fd, raw_path = tempfile.mkstemp(prefix="era-backup-", suffix=".dump")
    os.close(fd)
    path = Path(raw_path)
    try:
        path.chmod(0o600)
        env = _pg_environment(database_url)
        await verify_pg_dump_compatibility(database_url)
        try:
            process = await asyncio.create_subprocess_exec(
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(path),
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError as exc:
            raise BackupSnapshotError("pg_dump_unavailable") from exc
        await process.communicate()
        if process.returncode != 0 or not path.exists() or path.stat().st_size == 0:
            raise BackupSnapshotError("pg_dump_failed")
        checksum = await asyncio.to_thread(_sha256, path)
        return DatabaseSnapshot(
            path=path,
            checksum_sha256=checksum,
            size_bytes=path.stat().st_size,
        )
    except Exception:
        path.unlink(missing_ok=True)
        raise
