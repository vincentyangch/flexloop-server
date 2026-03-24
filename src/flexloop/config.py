from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite+aiosqlite:///./flexloop.db"

    ai_provider: str = "openai"
    ai_model: str = "gpt-4o-mini"
    ai_api_key: str = ""
    ai_base_url: str = ""
    ai_temperature: float = 0.7
    ai_max_tokens: int = 2000
    ai_review_frequency: str = "block"
    ai_review_block_weeks: int = 6

    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env"}


settings = Settings()
