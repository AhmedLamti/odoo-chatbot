# Odoo AI Platform — Technical & Business Documentation

> A multi-agent conversational AI platform that lets users talk to their **Odoo 16** ERP in natural language — asking documentation questions, querying live business data, and performing real ERP operations, all from a single chat interface.

This `docs/` folder is the complete reference for the project: business context, architecture, every subsystem, the rationale behind each technology, and a dedicated **technical defense (soutenance) Q&A**.

---

## How to read this documentation

If you have 10 minutes, read **01** and **02**. If you are preparing the defense, read everything and finish with **11** and **12**.

| # | Document | What it covers |
|---|----------|----------------|
| 00 | [README.md](README.md) | This index |
| 01 | [01-project-overview.md](01-project-overview.md) | Business problem, value proposition, users, use cases, scope |
| 02 | [02-architecture.md](02-architecture.md) | End-to-end architecture, request lifecycle, component map, diagrams |
| 03 | [03-orchestrator-and-graph.md](03-orchestrator-and-graph.md) | LangGraph orchestration, shared State, routing logic |
| 04 | [04-rag-agent.md](04-rag-agent.md) | Corrective RAG pipeline (rewrite → retrieve → generate → evaluate → retry) |
| 05 | [05-data-agent.md](05-data-agent.md) | Natural-language-to-data, two-level schema search, agent memory, charts |
| 06 | [06-action-agent.md](06-action-agent.md) | ERP write operations via XML-RPC, human-in-the-loop confirmation |
| 07 | [07-chat-agent.md](07-chat-agent.md) | Small-talk / fallback agent |
| 08 | [08-etl-and-indexing.md](08-etl-and-indexing.md) | Documentation ETL, schema extraction, vector indexing strategy |
| 09 | [09-llm-strategy.md](09-llm-strategy.md) | Multi-provider LLM factory and why each model is used per task |
| 10 | [10-data-stores-and-infra.md](10-data-stores-and-infra.md) | Qdrant, PostgreSQL, embeddings, API, persistence, retry |
| 11 | [11-technology-rationale.md](11-technology-rationale.md) | Justification of every major technology choice |
| 12 | [12-soutenance-qa.md](12-soutenance-qa.md) | Defense questions with detailed answers and concept explanations |
| 13 | [13-glossary.md](13-glossary.md) | Glossary of all key concepts and acronyms |

---

## One-paragraph summary

A user types a question in the Odoo chat UI. A FastAPI endpoint streams the request into a **LangGraph** orchestrator. An **orchestrator (router) agent** classifies the request into one of four routes — `rag`, `data`, `action`, or `chat` — and dispatches it to the matching specialized agent. The **RAG agent** answers Odoo *documentation* questions using a self-corrective retrieval loop over a Qdrant vector index of the official docs. The **data agent** answers questions about *the company's real data* by translating natural language into safe Odoo XML-RPC calls, using semantic schema discovery and a learned memory of past queries. The **action agent** performs *write* operations (create/update/delete/confirm/email) through XML-RPC, but only after explicit **human-in-the-loop confirmation**. The **chat agent** handles greetings and off-topic conversation. Every agent draws its LLM from a single **provider factory** that can switch between Groq, Google Gemini, Cerebras, Fireworks, and Anthropic Claude.

> ⚠️ **Note on the root `README.md`:** the repository's top-level README describes an earlier design (RAG + SQL + Plotly dashboard over PostgreSQL with Cerebras/Gemini/Groq). The codebase has since evolved into the 4-agent architecture documented here, where live data access is done through **Odoo XML-RPC** rather than direct SQL, and the LLM layer is provider-agnostic. Where the two disagree, **this documentation reflects the current code.**
