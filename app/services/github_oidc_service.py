from __future__ import annotations

import asyncio
from functools import lru_cache

import jwt
from fastapi import HTTPException

OIDC_ISSUER = "https://token.actions.githubusercontent.com"
OIDC_JWKS_URL = "https://token.actions.githubusercontent.com/.well-known/jwks"
BACKUP_AUDIENCE = "era-platform-backup"
EXPECTED_REPOSITORY = "davidbagh22/era-telegram-bot"
EXPECTED_REPOSITORY_ID = "1284995174"
EXPECTED_REF = "refs/heads/main"
EXPECTED_WORKFLOW_REF = (
    "davidbagh22/era-telegram-bot/.github/workflows/database-backup.yml@refs/heads/main"
)
ALLOWED_EVENTS = {"schedule", "workflow_dispatch"}


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(OIDC_JWKS_URL, cache_keys=True, lifespan=3600)


def _verify_sync(token: str) -> dict[str, object]:
    signing_key = _jwks_client().get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=BACKUP_AUDIENCE,
        issuer=OIDC_ISSUER,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
    )
    return claims


def _require_exact_backup_claims(claims: dict[str, object]) -> None:
    checks = {
        "repository": EXPECTED_REPOSITORY,
        "repository_id": EXPECTED_REPOSITORY_ID,
        "ref": EXPECTED_REF,
        "workflow_ref": EXPECTED_WORKFLOW_REF,
        "runner_environment": "github-hosted",
    }
    for key, expected in checks.items():
        if str(claims.get(key, "")) != expected:
            raise HTTPException(status_code=401, detail="invalid_backup_identity")
    if str(claims.get("event_name", "")) not in ALLOWED_EVENTS:
        raise HTTPException(status_code=401, detail="invalid_backup_identity")


async def verify_backup_workflow_token(token: str) -> dict[str, object]:
    if not token or len(token) > 12000:
        raise HTTPException(status_code=401, detail="invalid_backup_identity")
    try:
        claims = await asyncio.to_thread(_verify_sync, token)
    except HTTPException:
        raise
    except Exception as exc:
        # Do not include the token, claims, key material, or remote response in
        # the exception returned to callers/logs.
        raise HTTPException(status_code=401, detail="invalid_backup_identity") from exc
    _require_exact_backup_claims(claims)
    return claims


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="backup_identity_required")
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        raise HTTPException(status_code=401, detail="backup_identity_required")
    return value.strip()
