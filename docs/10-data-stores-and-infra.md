# 10 — Data Stores, Embeddings & Infrastructure

This document covers the supporting infrastructure: the vector store, embeddings, the relational connection, Odoo access, the API layer, persistence, configuration, and resilience.

## 10.1 Qdrant — the vector database

[db/vector_store.py](../db/vector_store.py) (`VectorStoreManager`). **Qdrant** stores high-dimensional vectors and answers nearest-neighbour queries fast.

- **Collections used:**
  - the **docs** collection (RAG) — chunks of the Odoo documentation;
  - **`odoo_models_v3`** / **`odoo_fields_v3`** (data agent) — the searchable Odoo schema;
  - **`agent_memories`** (data agent) — learned query patterns.
- **Vector size 768**, **distance = COSINE** (cosine similarity is the standard for normalized text embeddings — it measures *direction*/semantic similarity, not magnitude).
- `upsert` batches points (100) with UUID ids and a payload (`content` + metadata). `search` / `search_with_filter` return `[{content, metadata, score}]`; the filter variant uses Qdrant `FieldCondition` to restrict to e.g. a single `model_name`.

**Why Qdrant?** Open-source, runs locally in one Docker container, has native payload filtering (essential for the per-model field search), is fast, and integrates cleanly with LlamaIndex/LangChain. See [11-technology-rationale.md](11-technology-rationale.md).

## 10.2 Embeddings — bge-m3 via Ollama

[shared/embedding.py](../shared/embedding.py). A **singleton** (`@lru_cache(maxsize=1)`) `OllamaEmbedding` shared by chunker, embedder, retriever, and the memory/schema searches — so the model is loaded once.

- Model: **bge-m3** (768-dim), served **locally by Ollama**.
- `embed_documents(texts)` for ingestion (batch); `embed_query(text)` for retrieval (single).
- bge-m3 needs **no task prefix** (unlike `nomic-embed-text`, which wants `search_document:` / `search_query:`), so the prefixes are empty constants.

**Why local embeddings?** Free, private (documents never leave the machine), stable/deterministic, and removes a network dependency from the hot path. bge-m3 is **multilingual** — important for FR/EN questions — and strong on asymmetric short-query→long-passage retrieval.

## 10.3 Odoo XML-RPC client

[core/odoo_client.py](../core/odoo_client.py) — the live operational data path for the data and action agents.

- Authenticates by **API key** on `/xmlrpc/2/common`; caches `uid`; all calls go through `execute_kw` on `/xmlrpc/2/object`.
- Helpers: `search_read`, `search_count`, `read_group`, `fields_get`, plus generic `execute(model, method, *args, **kwargs)` for `create`/`write`/`unlink`/workflow methods.
- `_clean_domain` converts `None`→`False` (XML-RPC has no null) and preserves `|`/`&`/`!`. `fields_get` filters out binary/html/serialized and noise (`message_*`, `activity_*`, `website_*`).
- Auth and calls wrapped in `@with_retry`.

## 10.4 PostgreSQL connector (legacy/optional path)

[db/sql_connector.py](../db/sql_connector.py) — SQLAlchemy engine (`pool_pre_ping`, `pool_size=5`, `max_overflow=10`) for direct introspection and the earlier SQL execution path. [tools/sql_executor.py](../tools/sql_executor.py) adds a **SELECT-only guard**: queries must start with `SELECT` and are rejected if they contain `DROP/DELETE/INSERT/UPDATE/ALTER/CREATE/GRANT/REVOKE/TRUNCATE` (word-boundary regex), with retried execution and table formatting. As noted in [08](08-etl-and-indexing.md), the **live path is now XML-RPC**; this layer remains for schema extraction and history.

## 10.5 API layer — FastAPI + SSE

[api/main.py](../api/main.py).

- **`POST /api/chat/stream`** — the main endpoint. Runs the orchestrator in a worker **thread** and streams **Server-Sent Events** from a `queue.Queue`: incremental `step` events (live progress) then a `final` event (answer + route + steps + sources + confirmation fields). Errors are caught and returned as a generic safe message.
- **`POST /api/confirm-action`** — executes a staged write after user confirmation, via an **allow-list** of the five write tools (see [06-action-agent.md](06-action-agent.md)).
- **CORS** is restricted to the Odoo origin (`http://localhost:8071`).

**Why SSE + thread?** Agent runs take seconds and involve multiple LLM/tool calls. Streaming step events keeps the UI responsive and transparent; running the (synchronous) graph in a thread keeps the async event loop free to flush events.

## 10.6 Conversation persistence

[db/conversation_store.py](../db/conversation_store.py) — per-session history as JSON files (`data/conversations/{session_id}.json`), each message `{role, content, timestamp}`. Methods: `add_message`, `get_history`, `get_last_n`, `format_history`, `clear`, `list_sessions`. Simple, inspectable, zero-infra. (LangGraph's `MemorySaver` provides *in-process* short-term memory within a run; this store is the durable cross-call record.)

## 10.7 Configuration

[config/settings.py](../config/settings.py) — **Pydantic `BaseSettings`** loads everything from `.env`: Ollama, all LLM keys (Cerebras, Gemini/Google, Groq, OpenAI/Fireworks, Anthropic), PostgreSQL, Qdrant, GitHub token, Odoo URL/DB/credentials, LangSmith tracing, and app/log level. A computed `postgres_url` property builds the SQLAlchemy DSN. Centralizing config in a typed settings object means validation at startup and no scattered `os.getenv` calls.

## 10.8 Resilience — retry decorator

[utils/retry.py](../utils/retry.py) — `@with_retry(max_attempts=3, delay=1.0, backoff=2.0)` retries on exception with **exponential backoff** (1s → 2s → 4s), logging each attempt. Applied to Odoo auth/calls and the direct LLM client wrappers. This absorbs transient network blips and short-lived rate limits without bubbling failures to the user.

## 10.9 Observability

- The `steps` trace (streamed per node/tool) is both a UX feature and a debugging aid — you can see exactly which tools ran with which arguments.
- **LangSmith** tracing is wired through settings (`langchain_tracing_v2`, `langchain_project`) for optional deep tracing of LangGraph/LangChain runs.
- Module-level loggers (`shared/utils.get_logger`) throughout.

## 10.10 Deployment dependencies (runtime)

- **Qdrant** (Docker, port 6333) — vectors.
- **Ollama** (port 11434) with `bge-m3` pulled — embeddings.
- **Odoo 16** reachable over XML-RPC — live data/actions.
- **PostgreSQL** — only for the legacy/introspection path and conversation store is file-based.
- API keys for the chosen LLM providers.
- Python **3.12**, FastAPI + Uvicorn.
