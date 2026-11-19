"""Настройки приложения из переменных окружения (.env передаётся через env_file в compose)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    # extra="ignore": в .env лежат и чужие переменные (VPS_*, REGISTRY_*) — не падаем на них
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    mock_mode: bool = True
    docs_enabled: bool = True

    postgres_db: str = "autello"
    postgres_user: str = "autello"
    postgres_password: str = ""
    # Имя сервиса postgres в docker-compose — оно же DNS-имя во внутренней сети
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # Через запятую: http://localhost,https://autello.ru
    cors_origins: str = "http://localhost"
    # Заготовка под авторизацию /admin (следующий урок)
    admin_token: str = "change_me"

    @property
    def database_url(self) -> URL:
        # URL.create сам экранирует спецсимволы в пароле (@, :, / и т.п.)
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
