from functools import lru_cache
import subprocess

from importlib.metadata import version as _pkg_version

from pydantic_settings import BaseSettings


@lru_cache
def _git_short_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True, timeout=2,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


@lru_cache
def _default_version() -> str:
    base = "0.1.0"
    try:
        base = _pkg_version("trade")
    except Exception:
        pass
    sha = _git_short_sha()
    return f"{base}+{sha}" if sha else base


class Settings(BaseSettings):
    admin_username: str = "admin"
    admin_password: str
    telegram_api_id: int
    telegram_api_hash: str
    database_url: str
    session_secret: str
    encryption_key: str
    app_version: str | None = None

    @property
    def version(self) -> str:
        return self.app_version or _default_version()

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
