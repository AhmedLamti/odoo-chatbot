from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # ── Ollama (embeddings uniquement) ──────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = ""

    # ── Cerebras (Router + SQL) ──────────────────────────────
    cerebras_api_key: str = ""
    cerebras_model: str = ""

    # ── Gemini (RAG) ─────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = ""

    # ── Groq (Chart + Analysis) ──────────────────────────────
    groq_api_key: str = ""
    groq_model: str = ""

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

    # ── Odoo XML-RPC (Phase 5 — Automatisation) ─────────────
    odoo_url: str = "http://localhost:8071"
    odoo_db: str = ""
    odoo_username: str = "admin"
    odoo_password: str = "admin"
    odoo_api_key: str = ""

    google_api_key: str = ""

    # ── LangSmith (optionnel — monitoring LangGraph) ─────────
    langchain_api_key: str = ""
    langchain_tracing_v2: str = "false"
    langchain_project: str = "odoo-chatbot"

    # ── App ──────────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"

    default_llm_provider: str = "gemini_flash"

    openai_api_key: str = "fw_TSbk9dvX73ixJaxWiQ2Rh"
    anthropic_api_key: str = ""

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
