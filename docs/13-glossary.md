# 13 — Glossary

Quick definitions of every key term and acronym used in this project and documentation.

## AI / LLM concepts

- **LLM (Large Language Model)** — a neural network trained on large text corpora that predicts/generates text; here used for routing, generation, planning, judging, and extraction.
- **Agent** — an LLM given a goal, tools, and a loop to decide which tool to call next until it produces an answer.
- **Tool / Function calling** — a function the LLM can invoke with structured (JSON) arguments; the framework runs it and feeds the result back.
- **ReAct (Reason + Act)** — agent loop that alternates reasoning, tool actions, and observing results.
- **Prompt** — the instructions/context given to the LLM. **System prompt** sets role/rules; **user prompt** is the task.
- **Temperature** — randomness of LLM output; **0** = deterministic (used for all agents here).
- **In-context / few-shot learning** — steering the model by putting examples in the prompt, with no weight updates.
- **Hallucination** — confident but false LLM output; mitigated by RAG grounding and confirmation gates.
- **Token** — the unit LLMs read/produce (≈ a word piece); billing and limits are per token.

## Retrieval / RAG

- **RAG (Retrieval-Augmented Generation)** — retrieve relevant documents, then generate an answer grounded in them.
- **CRAG / Self-RAG** — RAG that evaluates its own retrieval/answer quality and self-corrects (re-query, re-rank, abstain).
- **Embedding / vector** — numeric representation of text meaning; similar texts map to nearby vectors.
- **Cosine similarity** — closeness of two vectors by the angle between them; standard metric for text embeddings.
- **Vector store / vector database** — a DB optimized for nearest-neighbor search over embeddings (here **Qdrant**).
- **ANN (Approximate Nearest Neighbor)** — fast, slightly-approximate nearest-vector search (Qdrant uses HNSW graphs).
- **Chunking** — splitting documents into retrievable pieces. **Semantic chunking** cuts on meaning boundaries.
- **Reranking** — a second-stage model re-scores top-k retrieval candidates for finer ordering (scaffolded, not yet implemented here).
- **Top-k** — how many nearest candidates to retrieve.
- **Recall vs. precision** — recall = did we retrieve the relevant items; precision = how many retrieved items are relevant. Level-1 search favors recall, Level-2 favors precision.
- **Hybrid retrieval** — combining dense (vector) and lexical (keyword) signals.

## Orchestration

- **LangChain** — framework of LLM building blocks (models, prompts, tools, retrievers).
- **LangGraph** — LangChain's library for building stateful, graph-structured agent applications.
- **Node** — a function `state → state-update` in the graph.
- **Edge / conditional edge** — a transition between nodes; conditional edges branch based on the state.
- **State** — the shared typed object (here `OrchestratorState`, a `TypedDict`) passed through the graph.
- **Reducer** — function that merges a node's update into a state field; `add_messages` appends conversation messages.
- **Checkpointer / MemorySaver** — persists graph state per `thread_id` for multi-turn continuity.
- **Streaming** — emitting partial results as the graph runs (here surfaced as `step` events).
- **Human-in-the-loop (HITL)** — a required human approval before a consequential action.

## Odoo

- **Odoo** — open-source ERP; **Odoo 16** is the targeted version.
- **ERP (Enterprise Resource Planning)** — integrated business software (sales, accounting, inventory, HR…).
- **Model** — an Odoo business object (e.g. `res.partner`, `sale.order`, `account.move`), backed by a DB table.
- **Field** — an attribute of a model; can be stored, **computed**, **related**, or **translated** (JSONB).
- **Domain** — an Odoo filter: a list of `[field, operator, value]` triples plus logical operators `&`, `|`, `!`.
- **`customer_rank` / `supplier_rank`** — integer flags on `res.partner`; `> 0` marks a customer / supplier (Odoo 16 idiom).
- **XML-RPC** — Odoo's remote API; `authenticate` on `/xmlrpc/2/common`, then `execute_kw` on `/xmlrpc/2/object`.
- **`execute_kw`** — generic RPC to call any method of any model.
- **`search_read`** — search + read records in one call.
- **`search_count`** — count matching records.
- **`read_group`** — server-side GROUP BY with aggregates (e.g. `amount_untaxed:sum`).
- **`fields_get`** — introspect a model's fields and types.
- **`create` / `write` / `unlink`** — ORM methods to create / update / delete records.
- **Workflow method / action** — model methods like `action_confirm` (confirm order), `action_post` (post invoice).
- **Access rights / record rules** — Odoo's server-side authorization, enforced because calls run as the authenticated user.
- **API key** — per-user secret (Personal Settings → Security) used instead of a password for RPC auth.
- **Discuss** — Odoo's messaging module (the chat-bubble/bot integration target; frontend not in this repo).

## Infrastructure / platform

- **Qdrant** — open-source vector database (Docker, port 6333), cosine collections, payload filtering.
- **Ollama** — local model server (port 11434); here serves the **bge-m3** embedding model.
- **bge-m3** — multilingual embedding model, 768-dim, no task prefix required.
- **PostgreSQL** — relational DB backing Odoo; used here for schema introspection / legacy SQL path.
- **SQLAlchemy** — Python SQL toolkit/ORM used by the Postgres connector.
- **FastAPI** — async Python web framework exposing the API.
- **Uvicorn** — ASGI server that runs FastAPI.
- **SSE (Server-Sent Events)** — one-way HTTP streaming, server→client; carries `step` and `final` events.
- **CORS** — browser policy controlling cross-origin requests; restricted to the Odoo origin.
- **Pydantic / BaseSettings** — typed data models / typed env-config loader.
- **Plotly** — interactive charting library; figures serialized to JSON for the frontend.
- **pandas / DataFrame** — tabular data handling used in chart generation and Python-side aggregation.
- **Exponential backoff** — retry strategy with increasing delays (1→2→4 s) via `@with_retry`.
- **LangSmith** — LangChain's tracing/observability platform (optional, wired via settings).

## Providers / models (LLM factory)

- **Groq** — ultra-low-latency inference provider (Llama-3.3-70B, Qwen3-32B, Llama-4-Scout).
- **Google Gemini** — `gemini-2.5-flash` (default agents) and `flash-lite` (cheap helpers).
- **Cerebras** — inference provider with a large free daily quota; used as a backup (Llama-3.3-70B).
- **Fireworks** — OpenAI-API-compatible host; used for reasoning (DeepSeek), Kimi, GPT-OSS.
- **Anthropic / Claude** — `ChatAnthropic` integration; recommended default for new LLM features.
- **Factory / Strategy pattern** — centralized provider selection (`LLMProvider` enum + `get_llm()`), avoiding vendor lock-in.

## Project-specific terms

- **Orchestrator / Router agent** — classifies a request into `rag | data | action | chat`.
- **RAG agent / Data agent / Action agent / Chat agent** — the four specialists.
- **Two-level schema search** — Level 1 vector search over the indexed schema, Level 2 LLM refinement + relation expansion.
- **MASTER_BOOST** — dictionary mapping business keywords → fields to boost during schema search.
- **AgentMemory** — a stored record of a past successful data query (model, domain, tool sequence, error avoided).
- **`pending_action` / `needs_confirmation`** — state fields staging a write that awaits human confirmation.
- **`steps`** — the human-readable, streamed execution trace shown live in the UI.
