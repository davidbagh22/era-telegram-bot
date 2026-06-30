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
    init_data_max_age_seconds: int = 86400
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
    def effective_webhook_secret(self) -> str:
        if not self.webhook_secret:
            return ""
        return hashlib.sha256(self.webhook_secret.encode()).hexdigest()


@lru_cache
def get_settings() -> Settings:
    return Settings()
