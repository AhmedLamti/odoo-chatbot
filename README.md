# 🤖 Odoo AI Chatbot

An intelligent chatbot for Odoo 16 combining RAG (documentation) and SQL (database) agents.

## Architecture
```
User Question
      │
      ▼
┌─────────────────┐
│   Orchestrator  │  → Classifies: RAG or SQL
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────┐
│  RAG  │ │  SQL  │
│ Agent │ │ Agent │
└───┬───┘ └───┬───┘
    │         │
    ▼         ▼
 Qdrant   PostgreSQL
(Odoo 16  (Odoo 16
  docs)     data)
```

## Stack

| Component | Technology |
|-----------|-----------|
| LLM | Mistral (via Ollama) |
| SQL Generation | Qwen2.5-Coder (via Ollama) |
| Embeddings | nomic-embed-text (via Ollama) |
| Vector Store | Qdrant |
| Database | PostgreSQL (Odoo 16) |
| API | FastAPI |
| Orchestration | LangGraph |
| RAG | LlamaIndex |

## Project Structure
```
odoo-chatbot/
├── agents/
│   ├── orchestrator.py       # Router RAG/SQL
│   ├── rag_agent.py          # Documentation agent
│   └── sql_agent.py          # Database agent
├── etl/
│   ├── loader.py             # GitHub scraper (Odoo v16 docs)
│   ├── chunker.py            # RST chunker
│   ├── embedder.py           # Embeddings generator
│   ├── pipeline.py           # ETL pipeline
│   └── schema_extractor.py   # Odoo DB schema extractor
├── tools/
│   ├── retriever.py          # RAG retriever
│   ├── sql_executor.py       # SQL executor (read-only)
│   └── schema_selector.py    # Dynamic schema selector
├── db/
│   ├── vector_store.py       # Qdrant interface
│   ├── sql_connector.py      # PostgreSQL connector
│   ├── schema_cache.py       # Schema YAML cache
│   └── conversation_store.py # Session history
├── config/
│   └── settings.py           # Configuration
├── api/
│   └── main.py               # FastAPI endpoints
├── odoo_module/
│   └── chatbot_assistant/    # Odoo 16 module
├── tests/                    # 32/32 tests passing
└── scripts/
    ├── run_etl.py
    └── run_schema_extractor.py
```

## Prerequisites

- Ubuntu Linux
- Anaconda / Miniconda
- PostgreSQL with Odoo 16 database
- Ollama with models:
  - `mistral:latest`
  - `qwen2.5-coder:7b`
  - `nomic-embed-text`
- Docker (for Qdrant)

## Installation

### 1. Clone the repository
```bash
git clone https://github.com/AhmedLamti/odoo-chatbot.git
cd odoo-chatbot
```

### 2. Create Conda environment
```bash
conda create -n odoo-chatbot python=3.12.3
conda activate odoo-chatbot
pip install -r requirements.txt
pip install -e .
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Start Qdrant
```bash
docker run -d \
  --name qdrant \
  --restart always \
  -p 6333:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

### 5. Run ETL pipeline
```bash
# Index Odoo documentation
python scripts/run_etl.py

# Extract database schema
python scripts/run_schema_extractor.py
```

### 6. Start API
```bash
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| POST | `/chat` | Ask a question |
| GET | `/history/{session_id}` | Get conversation history |
| DELETE | `/history/{session_id}` | Clear history |
| GET | `/sessions` | List active sessions |
| GET | `/sql/schema` | Get DB schema |

### Chat Example
```bash
# RAG question (documentation)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Comment configurer la comptabilité dans Odoo ?"}'

# SQL question (database)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Combien de clients avons-nous ?"}'

# With session (conversation history)
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Et combien ont passé une commande ?", "session_id": "your-session-id"}'
```

## Environment Variables
```env
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=mistral:latest
OLLAMA_SQL_MODEL=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=nomic-embed-text

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=your_odoo_db
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=odoo_docs

# GitHub
GITHUB_TOKEN=your_github_token
```

## Running Tests
```bash
pytest tests/ -v
# 32/32 tests passing
```

## Odoo Integration

Install the `chatbot_assistant` module located in `odoo_module/` into your Odoo 16 addons path.

## License

MIT
