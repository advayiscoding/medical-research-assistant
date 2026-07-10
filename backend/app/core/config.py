"""Application configuration.

Every tunable lives here and is loaded from environment variables (or a local
`.env` file in development). Nothing else in the codebase reads os.environ —
services receive a Settings object, which keeps configuration testable and
documented in exactly one place (12-factor app, factor III).
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "MedResearch AI"
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:3000"]

    # --- PostgreSQL (system of record) ---
    database_url: str = (
        "postgresql+asyncpg://medresearch:medresearch@localhost:5432/medresearch"
    )

    # --- Auth ---
    # The default exists so the app boots in dev; production MUST override it
    # (enforced in main.py at startup, not silently trusted).
    jwt_secret: str = "dev-only-secret-do-not-use-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # --- Claude API ---
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5"

    # --- Embeddings ---
    # Swappable: "NeuML/pubmedbert-base-embeddings" for biomedical-tuned vectors.
    # Changing models requires re-ingestion; the Chroma collection is versioned
    # by model name so stale vectors are never mixed with new ones.
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- ChromaDB (derived vector index) ---
    # chroma_host unset → embedded client persisting to chroma_persist_dir
    # (local dev). Set to a hostname to use the HTTP client (docker/cloud).
    chroma_host: str | None = None
    chroma_port: int = 8001
    chroma_persist_dir: str = "./chroma_data"

    # --- PubMed / NCBI E-utilities ---
    # Both optional. An API key raises the rate limit from 3 to 10 req/s;
    # an email is NCBI etiquette so they can contact heavy users.
    pubmed_api_key: str = ""
    pubmed_email: str = ""

    # --- Uploads ---
    upload_dir: str = "./uploads"
    max_upload_bytes: int = 25 * 1024 * 1024  # 25 MB


@lru_cache
def get_settings() -> Settings:
    """Cached accessor — one Settings instance per process.

    lru_cache (rather than a module-level instance) lets tests call
    get_settings.cache_clear() and construct fresh settings with overrides.
    """
    return Settings()
