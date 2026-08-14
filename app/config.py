import hashlib
from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_ids(value: object) -> list[int]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [int(item) for item in value]
    return [int(item.strip()) for item in str(value).split(",") if item.strip()]


IdList = Annotated[list[int], BeforeValidator(_parse_ids)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    bot_token: str = Field(min_length=10)
    public_base_url: str = ""
    webhook_secret: str = ""
    render_external_hostname: str = ""
    dev_auth_enabled: bool = False
    # Telegram regenerates initData fresh every time the Mini App is opened,
    # so this only needs to cover slow clients/networks — not multi-hour
    # reuse. Kept in line with the session token TTL (see auth.py).
    init_data_max_age_seconds: int = 3600
    miniapp_url: str = ""
    miniapp_auth_secret: str = ""
    # Shared only between the production API and the GitHub backup workflow.
    # It authenticates metadata callbacks; backup bytes and DB credentials are
    # never accepted by the HTTP endpoint.
    backup_report_secret: str = ""
    bot_username: str = ""
    database_url: str = "postgresql+asyncpg://era:era@db:5432/era"
    redis_url: str = "redis://redis:6379/0"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.5"

    era_channel_id: int | str = ""
    era_channel_url: str = "https://t.me/+kFak7gRKoA8xYTc6"
    era_pro_channel_url: str = "https://t.me/+WSagiElAvEsxMTI6"
    general_chat_id: int | None = None
    general_chat_url: str = "https://t.me/+Q6MzTrnR21dmZjgy"
    internal_department_chat_id: int | None = None
    internal_department_chat_url: str = "https://t.me/+zV8olVtkdc8yMWVi"
    external_department_chat_id: int | None = None
    external_department_chat_url: str = "https://t.me/+PsEYN685g1w5ZmEy"
    leaders_chat_id: int | None = None
    leaders_chat_url: str = "https://t.me/+V3OkO1PNwmhiY2Ni"
    admin_ids: IdList = Field(default_factory=list)
    timezone: str = "Asia/Yerevan"
    log_level: str = "INFO"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator(
        "bot_token",
        "miniapp_auth_secret",
        "webhook_secret",
        "backup_report_secret",
        mode="before",
    )
    @classmethod
    def strip_secret_whitespace(cls, value: object) -> object:
        # A trailing newline/space pasted into a Render env var is an easy,
        # silent mistake — aiogram's own HTTP calls to the Bot API tend to
        # tolerate it (it ends up in a URL/header that gets normalized
        # somewhere along the way), but our own HMAC checks
        # (app/api/security.py's verify_init_data/create_session_token)
        # hash this value byte-for-byte, so unstripped whitespace here would
        # make every genuine Telegram-signed initData look like a forgery
        # while every other bot API call kept working fine — the specific,
        # confusing failure mode that made this worth guarding against
        # rather than trusting the env var to already be clean.
        return value.strip() if isinstance(value, str) else value

    @property
    def chat_ids(self) -> set[int]:
        return {
            chat_id
            for chat_id in (
                self.general_chat_id,
                self.internal_department_chat_id,
                self.external_department_chat_id,
                self.leaders_chat_id,
            )
            if chat_id is not None
        }

    @property
    def effective_base_url(self) -> str:
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        if self.render_external_hostname:
            return f"https://{self.render_external_hostname}".rstrip("/")
        return ""

    @property
    def effective_miniapp_url(self) -> str:
        """URL for the bot's "Open ERA" WebApp button.

        Defaults to the Mini App bundled and served by this same service
        (see app/webapp.py::_mount_frontend) at "<base url>/app/". Set
        MINIAPP_URL explicitly only when the frontend is hosted elsewhere.

        Stays empty (button hidden) until MINIAPP_AUTH_SECRET is set, even
        if a base/miniapp URL is configured — without the secret, opening
        the Mini App would only show an auth error, so it is safer to keep
        the button hidden than to ship a visibly broken one.
        """
        if not self.miniapp_auth_secret:
            return ""
        if self.miniapp_url:
            return self.miniapp_url.rstrip("/")
        if self.effective_base_url:
            return f"{self.effective_base_url}/app/"
        return ""

    @property
    def effective_webhook_secret(self) -> str:
        if not self.webhook_secret:
            return ""
        return hashlib.sha256(self.webhook_secret.encode()).hexdigest()

    @property
    def is_render_deployment(self) -> bool:
        """True when running on Render, which sets RENDER_EXTERNAL_HOSTNAME
        for every deployed service. Used only to guard against accidentally
        leaving a developer-only bypass enabled in production — never to
        gate real authorization decisions."""
        return bool(self.render_external_hostname)

    def assert_safe_for_deployment(self) -> None:
        """Fail loudly at startup instead of silently accepting a dangerous
        configuration. Called once from app/webapp.py's lifespan."""
        if self.dev_auth_enabled and self.is_render_deployment:
            raise RuntimeError(
                "DEV_AUTH_ENABLED=true on a Render deployment would let anyone "
                "bypass Telegram initData verification by posting an arbitrary "
                "devTelegramId to /api/v1/miniapp/auth. Refusing to start — "
                "unset DEV_AUTH_ENABLED in the Render service environment."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
