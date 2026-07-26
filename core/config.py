from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Research Agent API"
    environment: str = "development"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/research_agent"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""
    redis_url: str = "redis://localhost:6379/0"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    tavily_api_key: str = ""
    readonly_database_url: str = "postgresql+asyncpg://readonly_agent:readonly_pass@localhost:5432/research_agent"
    langsmith_api_key: str = ""
    langsmith_project: str = "research-agent-dev"
    langsmith_tracing: bool = False


settings = Settings()