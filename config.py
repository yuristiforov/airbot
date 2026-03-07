from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    BOT_TOKEN: str
    WAQI_TOKEN: str
    DATA_DIR: str = "/app/data"
    LOG_LEVEL: str = "INFO"

    @property
    def db_path(self) -> str:
        return f"{self.DATA_DIR}/airbot.db"


settings = Settings()
