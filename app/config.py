from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    admin_username: str = "admin"
    admin_password: str
    telegram_api_id: int
    telegram_api_hash: str
    database_url: str
    session_secret: str
    encryption_key: str

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
