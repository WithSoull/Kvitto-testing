from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: PostgresDsn
    # Required on purpose: without a secret the webhook would accept anyone's requests.
    webhook_secret: SecretStr = Field(min_length=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
