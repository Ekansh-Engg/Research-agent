from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Research Agent API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/research_agent"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    redis_url: str = "redis://localhost:6379/0"

settings = Settings()