# 11 — Technology Rationale (Why each choice)

This document justifies every major technology and architectural decision. These are the "why did you use X?" questions a jury loves; the answers are concise and defensible.

## 11.1 Architecture decisions

### Why a multi-agent system instead of one big LLM/agent?
A single mega-prompt with all tools tends to pick the wrong tool, mix concerns, and hallucinate. Splitting into **four focused specialists** (route / docs / data / action) gives each a tight prompt and a small tool set → higher accuracy, easier testing, independent evolution, and the ability to use a **different model per agent**. It also isolates risk: only the action agent can write, and only behind confirmation.

### Why LangGraph (vs. plain LangChain chains, or raw orchestration)?
LangGraph models the app as a **stateful graph** with explicit control flow, conditional branching, streaming, checkpointing, and human-in-the-loop support — exactly what an orchestrator-with-specialists needs. Plain chains are linear and awkward for branching/looping; hand-rolled orchestration would reinvent state management, streaming, and persistence. LangGraph is purpose-built for **agentic** apps.

### Why XML-RPC for live data instead of generating raw SQL? *(important)*
This is the single most important defensible decision. Querying the Odoo PostgreSQL DB directly with generated SQL:
- **bypasses Odoo access rights and record rules** — a security hole;
- **misses computed/related fields** that exist only in the ORM, not as columns;
- **mishandles translated fields** (e.g. `product.template.name` is JSONB) and business logic;
- runs under a single DB account, losing **per-user accountability**.

Going through Odoo's **XML-RPC ORM API** means every read/write respects permissions, computed fields, and business constraints, and is **attributable to the real user**. It's the officially supported, future-proof integration surface. (The project started with SQL — see the root README — and deliberately migrated to XML-RPC; the SQL tooling remains only for introspection.)

### Why human-in-the-loop confirmation for writes?
LLMs are probabilistic and can target the wrong record. For irreversible operations (delete, post invoice, send email), a **confirmation gate** keeps a human as the final authority. Combined with an **allow-list** on the execution endpoint, this bounds what the system can ever do automatically. Safety > autonomy for ERP writes.

## 11.2 RAG & retrieval stack

### Why RAG instead of fine-tuning / a bigger prompt?
RAG **grounds** answers in the official docs → less hallucination, traceable **sources**, and trivial updates (re-run ETL when docs change) with **no retraining**. Fine-tuning is expensive, goes stale, and still hallucinates.

### Why corrective/self-evaluating RAG?
The dominant RAG failure is **retrieval miss**. A self-grading step + one reformulated retry recovers many misses cheaply, without a heavyweight agent framework. Fail-open evaluation ensures the loop never blocks a usable answer.

### Why Qdrant (vs. FAISS / pgvector / Pinecone)?
- vs. **FAISS**: Qdrant is a full service with persistence, payload storage, and **metadata filtering** (needed for per-model field search) — FAISS is just an index.
- vs. **pgvector**: avoids coupling vectors to the ERP's Postgres and gives better ANN ergonomics/filtering.
- vs. **Pinecone**: Qdrant is **open-source and self-hostable** → no per-vector cost, data stays local. One Docker container to run.

### Why semantic chunking of the docs?
Fixed-size windows cut mid-idea. **Structural (RST) + semantic** chunking keeps each chunk topically self-contained → higher retrieval precision.

### Why bge-m3 embeddings, served by Ollama (local)?
- **Local** → free, private (docs/queries never leave the host), deterministic, no hot-path network dependency.
- **bge-m3** → strong **multilingual** model (matches the FR/EN requirement) and good at asymmetric short-query→long-passage retrieval; needs no task prefix.

## 11.3 Data agent techniques

### Why semantic search over the schema (two levels)?
The ERP schema is far too large to prompt-stuff. **Level 1 (vectors + keyword boosts)** maximizes recall of relevant models/fields; **Level 2 (LLM)** maximizes precision by trimming to what's needed and expanding relations. This is what makes reliable NL-to-data on hundreds of models feasible.

### Why keyword boosts on top of vector search?
A pragmatic **hybrid retrieval**: vectors capture semantics, the boost dictionary injects **domain priors** so the field that truly answers a common business question (e.g. `user_id` for "salesperson") wins. Cheap, transparent, and effective.

### Why a separate reasoning model for query planning?
Decomposing multi-model questions and obeying XML-RPC dot-notation limits is a **reasoning** problem. A reasoning model at **temperature 0** produces stable, machine-readable plans; a fast chat model is less reliable here.

### Why agent memory?
Training-free, cheap **reliability gains** on recurring questions: the agent reuses domains/tool-sequences that previously worked and records "errors to avoid". It's retrieval-augmented *procedure* memory, with dedup so it doesn't bloat.

## 11.4 LLM platform

### Why a provider-agnostic factory and multiple providers?
Different sub-tasks have different optima (latency vs. reasoning vs. tool-calling vs. cost); free tiers rate-limit; vendors have outages. A **factory** lets us pick the best model per task, **fail over** to backups, **control cost**, and avoid **lock-in** — all by editing one file or passing `llm_provider` per request. (For brand-new LLM work, defaulting to the latest, most capable Claude models is recommended; `ChatAnthropic` is already integrated.)

### Why temperature 0 for agents?
Deterministic, repeatable tool calls and parseable outputs. Creativity is undesirable when generating domains, plans, and routes.

## 11.5 Platform & infra

### Why FastAPI + SSE?
FastAPI is async, fast, and auto-documents (Swagger). **Server-Sent Events** are the simplest one-way streaming transport for pushing live `step` updates and the final answer — perfect for a chat UX where runs take seconds.

### Why Pydantic settings?
Typed, validated configuration loaded once from `.env` — fails fast on misconfiguration, no scattered `os.getenv`.

### Why the retry decorator?
Free-tier LLMs and network calls fail transiently. **Exponential backoff** turns most blips into a slightly slower success instead of a user-visible error.

### Why Python 3.12?
Modern typing (`X | None`, `TypedDict` features), performance, and first-class support across LangChain/LangGraph/FastAPI/Qdrant clients.

## 11.6 Honest limitations (good to volunteer in a defense)
- **Reranking** is scaffolded but not implemented ([tools/reranker.py](../tools/reranker.py) is empty) — a cross-encoder reranker is a natural next step for RAG precision.
- Some **legacy** code coexists with the current path (raw-SQL tooling, `tools/odoo_xmlrpc.py`, older `RAGRetriever`) — kept for history/introspection, not on the live path.
- The `ANTHROPIC_SONNET` enum name/value doesn't match the model actually instantiated ([09-llm-strategy.md](09-llm-strategy.md)).
- The root `README.md` predates the current architecture; **this `docs/` set is authoritative**.
- **Predictive ML** is roadmap, not built.
