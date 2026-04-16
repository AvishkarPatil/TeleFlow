import os
import tempfile
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_api_id: int
    telegram_api_hash: str
    bot_token: str
    user_session_string: str | None = None

    mongodb_uri: str
    mongodb_db_name: str = "savethefile"

    sudo_users: str = ""

    max_workers: int = 5
    max_tasks_per_user: int = 3
    temp_dir: str = os.path.join(tempfile.gettempdir(), "savethefile")

    log_level: str = "INFO"
    enable_health_server: bool = False
    health_port: int = 8080

    @property
    def sudo_user_ids(self) -> List[int]:
        if not self.sudo_users:
            return []
        return [int(uid.strip()) for uid in self.sudo_users.split(",") if uid.strip().isdigit()]

    @field_validator("log_level", mode="before")
    @classmethod
    def normalise_log_level(cls, v: str) -> str:
        return v.upper()


settings = Settings()
