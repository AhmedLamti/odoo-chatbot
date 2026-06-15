# 12 — Technical Defense (Soutenance) Q&A

A curated bank of questions a jury is likely to ask, with **model answers** and **concept explanations**. Organized by theme. Each answer is written so you can speak it in ~30–90 seconds. Where a concept needs background, a short **"Concept"** box explains it.

> Tip for the defense: when asked "why X?", always give (1) the problem, (2) your choice, (3) the alternative you rejected and why. Every answer below follows that shape.

---

## A. General architecture

### Q1. Describe your system in two minutes.
It's a conversational AI assistant embedded in Odoo 16. A user asks a question in natural language (FR/EN); a FastAPI endpoint streams it into a **LangGraph orchestrator**. An **orchestrator/router agent** classifies the request into one of four routes — documentation, data, action, or chat — and dispatches it to a specialized agent. The **RAG agent** answers documentation questions grounded in the official Odoo docs via a self-correcting retrieval loop over a Qdrant vector index. The **data agent** answers questions about the company's live data by translating language into safe Odoo XML-RPC queries, using semantic schema discovery and a learned memory. The **action agent** performs write operations (create/update/delete/confirm/email) through XML-RPC, gated by human confirmation. The **chat agent** handles small talk. All agents draw their LLM from a single provider factory (Groq, Gemini, Cerebras, Fireworks, Anthropic), choosing the best model per task.

### Q2. Why a multi-agent architecture rather than one LLM call?
A single agent with every tool and a giant prompt mixes concerns and frequently picks the wrong tool or hallucinates. Four focused specialists each get a tight prompt and a small tool set → higher accuracy, independent testing, and per-agent model choice. It also isolates risk — only the action agent can write, only behind confirmation.

> **Concept — Agent.** An "agent" here is an LLM given a goal, a set of **tools** (functions it can call), and a loop in which it decides which tool to call next based on prior results (the **ReAct** pattern: Reason → Act → Observe), until it produces a final answer.

### Q3. What is LangGraph and why use it?
LangGraph models an application as a **graph of nodes over a shared, typed state**. Each node is `state → state-update`; edges (including **conditional** edges) decide what runs next. It gives explicit control flow, streaming of per-node updates, checkpointing per session, and human-in-the-loop pauses. A plain LangChain chain is linear and can't branch cleanly; raw orchestration would force me to reinvent state, streaming, and persistence. For an orchestrator-with-specialists, LangGraph is purpose-built.

### Q4. Walk through the lifecycle of one request.
POST `/api/chat/stream` → FastAPI runs the orchestrator in a worker thread and streams Server-Sent Events. The orchestrator builds the shared state and streams the graph: the router node classifies (one LLM call → `rag|data|action|chat`), a conditional edge routes to that agent, the agent runs its internal loop and writes `answer`/`steps`/`sources` (and for actions, `needs_confirmation` + `pending_action`) back to state, then the graph ends and the result streams back. For a write, the UI shows a confirmation and a *second* call to `/api/confirm-action` executes the staged tool.

### Q5. How does the shared state work? What's special about `messages`?
It's a `TypedDict` (`OrchestratorState`) every node reads/writes. Scalar fields use last-write-wins; the `messages` field uses the **`add_messages` reducer**, which *merges* new messages into the list instead of overwriting — so the conversation accumulates while `answer`, `route`, etc. are simply replaced.

> **Concept — Reducer.** In LangGraph, a reducer is a function that combines the previous value of a state field with the update a node returns. `add_messages` appends/merges message lists; without it, each node would clobber the history.

---

## B. Routing / orchestrator

### Q6. How does routing work, and why an LLM instead of keywords?
The router node sends the question to a fast model (Groq Llama-3.3) with a system prompt defining the four categories and examples, constrained to answer with **one word**. An LLM generalizes to paraphrases and two languages far better than a keyword list (which was the original design). The decision is cheap because it's a single token.

### Q7. What if the router returns something unexpected, or the LLM call fails?
It **falls back to `chat`**. Any invalid output or exception degrades gracefully to the harmless conversational agent — never a crash and never an accidental destructive route. This fail-safe default is a deliberate safety property.

### Q8. Why use a *fast* model for routing but a *reasoning* model for planning?
They're different tasks. Routing is a one-token classification where **latency** dominates → a fast model. Query planning decomposes a multi-model question and must respect RPC constraints — a **reasoning** task where correctness dominates → a reasoning model at temperature 0. Matching model to task is the whole point of the provider factory.

---

## C. RAG agent

### Q9. What is RAG and why did you need it?
Retrieval-Augmented Generation grounds the LLM's answer in retrieved documents instead of its parametric memory. I embed the query, find the most similar doc chunks in Qdrant, put them in the prompt, and instruct the model to answer **only** from that context. This gives accurate, **source-cited**, up-to-date answers and avoids hallucination — and updating knowledge is just re-running the ETL, no retraining.

> **Concept — Embedding & vector search.** An embedding maps text to a vector such that semantically similar texts are close in space. Retrieval finds the nearest vectors to the query vector (here by **cosine similarity**). This is "search by meaning", not keywords.

### Q10. Explain your corrective RAG loop.
Per question, up to two attempts: **rewrite** the query into concise English → **retrieve** top-8 chunks (keep only score ≥ 0.30) → **generate** an answer from the context → **evaluate** with a separate LLM judge returning RELEVANT / NOT_RELEVANT. If relevant, return; if not and an attempt remains, **augment** the query and loop. The dominant RAG failure is a retrieval miss; self-grading + one reformulated retry recovers many of those cheaply.

> **Concept — Corrective RAG (CRAG) / Self-RAG.** A family of techniques where the system evaluates its own retrieval/answer quality and takes corrective action (re-query, re-rank, abstain) rather than blindly returning the first generation.

### Q11. Why rewrite the query before retrieving?
The docs are indexed in English with technical vocabulary; the user asks in chatty French/English. Rewriting to a clean, keyword-dense English query aligns it with the indexed text and improves recall. It fails safe — if rewriting errors, the original question is used.

### Q12. Why the 0.30 score threshold?
To avoid feeding "garbage context" to the generator. If nothing is genuinely similar, it's better to answer "not found" than to summarize irrelevant text and hallucinate. Cosine scores run 0–1; 0.30 is the empirical floor for usefully-related chunks here.

### Q13. Your evaluator fails *open* (returns RELEVANT on error) but your rewriter fails *safe* (returns the original). Why the asymmetry?
Different risk profiles. A broken evaluator should not **block** a possibly-good answer, so it defaults to accept. A broken rewriter should not **lose the user's intent**, so it defaults to the original query. Each fallback preserves the most valuable property of its component.

### Q14. How do you handle French vs. English answers?
The generation prompt mandates answering in the question's language. For the fixed "not found" message I use a lightweight French-stopword heuristic to pick the language. The embedding model (bge-m3) is multilingual, so retrieval works across both.

### Q15. Do you re-rank retrieved results?
Not yet — `tools/reranker.py` is scaffolded but empty. Today precision comes from the cosine threshold plus the self-evaluation loop. A cross-encoder reranker is my planned next improvement; I can explain the tradeoff (better precision at the cost of an extra model call).

> **Concept — Reranking.** A second-stage model (often a cross-encoder that reads query+passage together) re-scores the top-k candidates from vector search for finer relevance ordering, at higher cost per candidate.

---

## D. Data agent (NL → data)

### Q16. How do you turn a question into a query when Odoo has thousands of fields?
**Two-level semantic schema discovery.** I pre-indexed the Odoo schema into Qdrant (one vector per model, one per field). At query time: Level 1 (`search_similar_models`) vector-searches for candidate models/fields, weighted by per-model importance plus a keyword-boost dictionary; Level 2 (`select_models`) asks a light LLM to trim to exactly what's needed and auto-expands one-hop relations. The planner then receives a small, correct schema slice instead of the whole ERP.

### Q17. Why two levels and not just vector search, or just an LLM?
Vector search gives **recall** (don't miss a relevant field) but can rank a wrong field high; the LLM gives **precision** (trim to the truly needed) but can't read thousands of fields. Combining them — broad recall then precise pruning — is what makes it reliable.

### Q18. What are the keyword boosts and why mix them with vectors?
A dictionary mapping ~75 French business terms to field names (e.g. "vendeur"→`user_id`, "montant"→`amount_total`). When the question contains a keyword, the matching field's score gets +2.0. This is **hybrid retrieval**: vectors capture semantics, the boosts inject domain priors so the field that *actually* answers a common question wins. Pure vector search sometimes gets this subtly wrong.

> **Concept — Hybrid retrieval.** Combining dense (vector/semantic) and sparse/lexical (keyword) signals. Dense handles paraphrase; lexical handles exact, high-signal terms. Together they beat either alone.

### Q19. Why query Odoo via XML-RPC instead of SQL? *(very likely question)*
Direct SQL bypasses Odoo's **access rights and record rules** (security risk), misses **computed/related fields** that exist only in the ORM, mishandles **translated JSONB fields** like `product.template.name`, and loses **per-user accountability** (one DB account). XML-RPC goes through the ORM: every read/write respects permissions, computed fields, and business logic, and is attributable to the real user. It's the officially supported, future-proof API. The project began with SQL and deliberately migrated.

### Q20. Give a concrete Odoo "gotcha" your system handles.
Several. (1) "Customers" aren't a flag — they're `res.partner` with `customer_rank > 0`. (2) `read_group` over XML-RPC doesn't accept `date_order:month` granularity, so I strip the granularity, run the group, then **re-group in Python** by truncating dates and summing. (3) Dot-notation (`order_id.user_id`) is allowed in `domain` but **forbidden** in `fields`/`groupby`, so the planner reads related models separately and **joins in Python**. These rules are encoded in the prompts, which is what prevents most generated-query failures.

### Q21. What is the ReAct pattern and where do you use it?
ReAct = the agent interleaves reasoning ("I need the model first") with actions (call a tool) and observations (read the result), looping until done. The data and action agents are ReAct agents built with `create_react_agent`. It lets the LLM dynamically chain tools — discover schema, plan, execute, format — rather than following a fixed script.

### Q22. Explain your agent memory. Isn't that just caching?
It's more than caching. After a **successful** run, an LLM extracts a structured `AgentMemory` (question summary, model, domain used, tool sequence, answer pattern, error avoided) and stores it as a vector in Qdrant. On a new question, I retrieve the top-3 similar past memories and inject them as worked examples into the prompt. So the agent reuses *procedures* that worked — including "errors to avoid" — improving reliability over time **without retraining**. I dedup at cosine ≥ 0.95 so it doesn't bloat. Plain caching would only help on *identical* questions; this helps on *similar* ones via semantic match.

> **Concept — In-context / few-shot learning.** Providing examples in the prompt so the model imitates the pattern at inference time — no weight updates. The memory turns the agent's own successes into dynamic few-shot examples.

### Q23. How do charts work end-to-end?
`generate_chart` loads the query result into a pandas DataFrame, builds a Plotly bar/line/pie figure, serializes it to JSON, and stores it in a module variable while returning only a short confirmation string to the LLM (so the big JSON doesn't bloat the context). The API fetches the chart separately via `get_last_chart()` and the frontend renders the interactive Plotly figure.

### Q24. How do you keep generated domains safe?
Domains arrive as strings and are parsed with `ast.literal_eval` (with a JSON fallback and `true/false/null` normalization) — not `eval`. The data path is read-oriented through XML-RPC, which also enforces the user's permissions. For the legacy SQL path there's a SELECT-only validator that blocks DROP/DELETE/UPDATE/etc.

---

## E. Action agent & safety

### Q25. How do you safely let an LLM modify the ERP?
Every write tool (create/update/delete/execute/email) is forbidden from running directly. The agent must first call `request_confirmation`, which returns a `WAITING_CONFIRMATION` payload and stops. The node lifts `needs_confirmation` + a human-readable summary + the staged `pending_action` into state; the UI shows Confirm/Cancel; only on confirm does a **separate** `/api/confirm-action` call execute the staged tool — and only if its name is in a five-tool **allow-list**. Human-in-the-loop + allow-list bounds what can ever happen automatically.

### Q26. How does the agent avoid acting on the wrong record?
The prompt enforces a protocol: never guess IDs. If the user names "Ahmed" or "the Chair", the agent must `search_records` to resolve the real ID first, and `get_model_fields` to learn valid field names, before any write. ID hallucination is the most dangerous failure for writes, so it's designed out.

### Q27. How is authentication and authorization handled?
Per-user **API-key** auth: credentials (`odoo_user_email`, `odoo_api_key`) come on each request, flow through state, and are passed into every Odoo tool, which builds an `OdooClient` that authenticates against `/xmlrpc/2/common` and caches the uid. **Authorization is delegated to Odoo** — calls run as that user, so Odoo's access rights and record rules apply. The agent has no privileged bypass; it can't do anything the user couldn't do in the UI.

### Q28. Why execute the confirmed action in a second HTTP call instead of resuming the graph?
It decouples "decide and stage" from "execute after yes", keeps the backend stateless between the two, and makes the confirmation explicit and auditable. LangGraph *can* pause mid-graph for human input, but the two-call design is simpler to reason about and the allow-list makes it safe.

---

## F. LLM platform

### Q29. Why support multiple LLM providers?
Different sub-tasks have different optima — routing needs **speed**, planning needs **reasoning**, agents need reliable **tool calling**, helpers need **low cost**; and free tiers rate-limit and vendors have outages. A provider **factory** lets me pick the best model per task, fail over to backups, control cost, and avoid lock-in — by editing one file or passing `llm_provider` per request.

> **Concept — Factory / Strategy pattern.** The `LLMProvider` enum selects a strategy; `get_llm()` is a factory that returns the concrete client. Callers depend on the abstraction, not the vendor SDK.

### Q30. Which model do you use where, and why?
Routing/chat/action/memory → Groq Llama-3.3 (fast, good tool calling). RAG generate+judge → Groq Qwen3. Default ReAct agents → Gemini 2.5 Flash (strong tool calling). Light helpers (`select_models`, `format_response`) → Gemini Flash-Lite (cheap, frequent). Query planning → Fireworks DeepSeek at temp 0 (reasoning). Backups → Cerebras / Fireworks Kimi for rate-limit failover.

### Q31. Why temperature 0 everywhere for agents?
Determinism and parseability. When generating routes, domains, and plans, I want repeatable, machine-readable output, not creativity. Temperature 0 makes the same input yield the same tool calls.

### Q32. How would you add a new model (e.g., a newer Claude)?
Add an enum value and a branch in `get_llm()` — one file. `ChatAnthropic` is already wired in, so a new Claude model is essentially a one-line model-id change. For new LLM features I'd default to the latest, most capable Claude model.

> **Honest note to volunteer:** the `ANTHROPIC_SONNET` enum name/value doesn't match the model the factory actually builds (`claude-haiku-4-5`). It's a labeling bug I'd clean up.

---

## G. Infrastructure & data stores

### Q33. Why Qdrant and not FAISS / pgvector / Pinecone?
Vs. FAISS: Qdrant is a full service with persistence and **payload filtering** (I need to filter field-vectors by `model_name`) — FAISS is just an index. Vs. pgvector: I don't want to couple vectors to the ERP's Postgres, and Qdrant has better ANN ergonomics. Vs. Pinecone: Qdrant is **open-source, self-hostable, free**, data stays local — one Docker container.

> **Concept — ANN (Approximate Nearest Neighbor).** Exact nearest-neighbor search is slow at scale; ANN indexes (e.g. HNSW graphs, which Qdrant uses) trade a tiny bit of accuracy for large speedups.

### Q34. Why bge-m3 embeddings via Ollama locally?
Local = free, **private** (text never leaves the host), deterministic, no hot-path network dependency. bge-m3 is **multilingual** (matches FR/EN) and strong at short-query→long-passage retrieval, with 768-dim vectors and no required task prefix.

### Q35. Why cosine similarity and 768 dimensions?
Cosine measures **direction** (semantic similarity) and is the standard for text embeddings, which are typically length-normalized. 768 is bge-m3's output dimension, so the collection is configured to match.

### Q36. Why semantic chunking of the docs instead of fixed-size?
Fixed windows cut mid-idea and split related sentences across chunks, hurting retrieval. I split first on RST section structure, then semantically (cut where consecutive-sentence cosine distance spikes), so each chunk is topically self-contained.

### Q37. Why FastAPI and SSE?
FastAPI is async, fast, and self-documenting (Swagger). SSE is the simplest one-way streaming transport to push live progress (`step`) events and the final answer to the chat UI, which matters because agent runs take several seconds. I run the synchronous graph in a worker thread so the event loop stays free to flush events.

> **Concept — SSE vs. WebSocket.** SSE is one-way (server→client) over plain HTTP, auto-reconnecting, ideal for streaming a response. WebSockets are bidirectional and heavier; unnecessary here since the client only needs to receive the stream.

### Q38. How do you handle transient failures and rate limits?
A `@with_retry` decorator with exponential backoff (3 attempts, 1→2→4s) wraps Odoo auth/calls and the direct LLM clients; plus provider failover via the factory. Most blips become a slightly slower success instead of a user-visible error.

### Q39. How is configuration managed?
Pydantic `BaseSettings` loads all secrets/params from `.env` once at startup with type validation — no scattered `os.getenv`, and misconfiguration fails fast.

### Q40. How do you persist conversations?
Per-session JSON files (`data/conversations/{id}.json`), messages as `{role, content, timestamp}`. Simple, inspectable, zero extra infra. LangGraph's `MemorySaver` gives in-process short-term memory within a run; this store is the durable cross-call record.

---

## H. Quality, testing, limits

### Q41. How do you know the system is correct?
Layered safeguards: prompt-encoded Odoo rules prevent the common query mistakes; the RAG self-evaluation loop catches retrieval misses; the data agent only saves memory from runs that didn't error; writes require human confirmation; and the streamed `steps` trace makes every run inspectable. The repo also carries a `tests/` suite for the agents (rag/data/action/orchestrator).

### Q42. What are the system's current limitations?
Reranking isn't implemented yet; some legacy code (raw-SQL tooling, old XML-RPC class, old retriever) coexists with the live path; the Anthropic enum mismatch; predictive ML is roadmap; and the root README is outdated relative to the code. I keep the legacy SQL/introspection layer because the schema-extraction pipeline still uses it.

### Q43. How would you scale this to many users / a large Odoo?
Stateless API behind a load balancer; Qdrant scales horizontally; embeddings can move to a GPU/Ollama cluster or a hosted embedding API; add caching of schema-search results; add a reranker; and use LangSmith tracing (already wired) to find slow nodes. XML-RPC per-user auth already supports multi-tenant correctness.

### Q44. Biggest technical challenge and how you solved it?
Making NL-to-data **reliable** on a huge ERP schema with real-world quirks. Solved by: (1) two-level semantic schema discovery so the planner sees only the relevant slice, (2) encoding Odoo/XML-RPC constraints (rank flags, JSONB names, dot-notation limits, date-granularity) into prompts and a Python regrouping step, and (3) an agent memory that learns from successful runs.

### Q45. If you restarted, what would you change?
Standardize on XML-RPC from day one (skip the SQL detour), implement reranking, fix the provider-enum labeling, add automated evals (a golden Q→answer set with retrieval/answer metrics), and consolidate the indexation script versions into one configurable pipeline.

---

## I. Rapid-fire concept checks (one-liners)

- **Vector / embedding?** A numeric representation of meaning; similar texts → nearby vectors.
- **Cosine similarity?** Angle-based closeness of two vectors, range −1..1 (0..1 for text).
- **RAG?** Retrieve relevant docs, then generate grounded in them.
- **CRAG?** RAG that evaluates and corrects its own retrieval/answer.
- **ReAct?** Reason→Act→Observe tool-use loop.
- **LangGraph node/edge/state?** Function / transition / shared typed dict.
- **Conditional edge?** Next node chosen by a function of the state.
- **Reducer (`add_messages`)?** Merges a state field instead of overwriting.
- **Tool (function calling)?** A function the LLM can invoke with structured args.
- **XML-RPC `execute_kw`?** Odoo's generic RPC to call any model method.
- **`read_group`?** Odoo's server-side GROUP-BY aggregation.
- **Domain (Odoo)?** A filter expressed as a list of `[field, op, value]` triples.
- **`customer_rank > 0`?** How Odoo 16 marks a partner as a customer.
- **Semantic chunking?** Splitting text on meaning boundaries, not fixed size.
- **Hybrid retrieval?** Dense (vector) + lexical (keyword) signals combined.
- **Factory pattern?** Centralized object creation behind an abstraction.
- **SSE?** One-way HTTP streaming, server→client.
- **Temperature 0?** Deterministic LLM output.
- **Human-in-the-loop?** A required human approval step before a consequential action.
- **Idempotency / fail-safe vs fail-open?** Degrade to a safe default vs. degrade to "allow" so users aren't blocked.
