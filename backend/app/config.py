from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OER Social Learning"
    api_prefix: str = "/api"
    database_url: str = "postgresql+asyncpg://oer:oer@localhost:5434/oer_social"
    # CircuitNotion OpenAI-compatible API (https://circuitnotion.com/Api_Documentation)
    # Working host is api. (apis. does not resolve in DNS)
    openai_base_url: str = "https://api.circuitnotion.com/v1"
    openai_api_key: str = ""
    circuitnotion_api_key: str = ""  # preferred alias; falls back to openai_api_key
    openai_model: str = "circuit-2-turbo"
    # CircuitNotion: dall-e-3 currently fails upstream (proxy injects response_format).
    # Use gpt-image-2; never send response_format from this app.
    openai_image_model: str = "gpt-image-2"
    openai_image_quality: str = "low"  # low | medium | high — high is ~30x low on gpt-image-2
    openai_image_size: str = "1024x1024"
    # CircuitNotion OpenAI-compatible embeddings
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dims: int = 1536
    memory_embed_enabled: bool = True
    memory_embed_max_chunks_per_conversation: int = 12
    memory_embed_chunk_chars: int = 1800
    cors_origins: str = "http://localhost:3000"
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_name: str = "OER Admin"
    bootstrap_admin_sync: bool = True

    # Public base URL for Instagram (must be reachable by Meta, e.g. https://your.domain)
    public_base_url: str = "http://localhost:8000"
    media_dir: str = str(Path(__file__).resolve().parent / "media")

    # Auto-post when admin clicks Publish Social
    x_api_key: str = ""
    x_api_secret: str = ""
    x_access_token: str = ""
    x_access_token_secret: str = ""

    instagram_access_token: str = ""
    instagram_user_id: str = ""  # Instagram Business Account ID


settings = Settings()
