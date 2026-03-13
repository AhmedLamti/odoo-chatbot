from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # ── Ollama (embeddings uniquement) ──────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"

    # Garder pour compatibilité schema_selector fallback
    ollama_llm_model: str = "llama3.2:3b"
    ollama_sql_model: str = "llama3.2:3b"

    # ── Cerebras (Router + SQL) ──────────────────────────────
    cerebras_api_key: str = ""
    cerebras_model: str = "llama3.1-8b"

    # ── Gemini (RAG) ─────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    # ── Groq (Chart + Analysis) ──────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # ── PostgreSQL ───────────────────────────────────────────
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: str

    # ── Qdrant ───────────────────────────────────────────────
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "odoo_docs"

    # ── GitHub ───────────────────────────────────────────────
    github_token: str

    # ── App ──────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
