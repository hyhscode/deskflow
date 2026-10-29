from functools import lru_cache 
from pydantic import Field,SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict

class Settings(BaseSettings):
    app_env:str = "dev"
    app_name:str = "DeskFlow"
    database_url: str = "sqlite:///./deskflow.db"
    secret_key: SecretStr = SecretStr("dev-only-not-for-production")
    token_expire_minutes: int = Field(default=480, gt=0, le=10080)
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()