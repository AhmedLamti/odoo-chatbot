# 01 — Project Overview (Business & Functional)

## 1.1 The problem

**Odoo** is one of the most widely used open-source ERPs. A single Odoo instance can contain hundreds of database models (`res.partner`, `sale.order`, `account.move`, `stock.picking`, …) and thousands of fields. Two recurring frustrations exist for the people who use it:

1. **Getting information out is hard.**
   - *Documentation:* "How do I configure automatic invoicing?" → the user has to search the official docs, which are large and technical.
   - *Live data:* "How many active customers do we have? What's revenue per month?" → the user must either know SQL, build an Odoo *pivot view*, or ask a developer. Non-technical staff are blocked.

2. **Performing operations requires navigating deep menus.**
   - "Confirm Ahmed's draft sales order", "raise the price of the Chair to 50€", "email this customer" — each requires several clicks across different screens, and the user must know exactly where each object lives.

## 1.2 The solution

A **conversational AI assistant embedded in Odoo** that understands natural language (French and English) and covers three distinct needs through one chat box:

| Need | Example question | Handled by |
|------|------------------|-----------|
| **Knowledge / how-to** | "Comment configurer la comptabilité ?" | RAG agent (over the Odoo docs) |
| **Live business data** | "Combien de clients actifs avons-nous ?" / "Chiffre d'affaires par mois" | Data agent (Odoo XML-RPC) |
| **Operations / write actions** | "Confirme la commande de Ahmed" / "Augmente le prix de la chaise à 50€" | Action agent (XML-RPC + confirmation) |
| **General conversation** | "Bonjour", "Qui es-tu ?" | Chat agent |

The key design idea is **a single entry point with automatic routing**: the user never has to choose which "mode" they are in. An orchestrator decides on every message.

## 1.3 Value proposition

- **Democratizes data access** — anyone can ask business questions without SQL, pivots, or developer help.
- **Reduces operational friction** — multi-step ERP operations become one sentence.
- **Self-service documentation** — answers grounded in the *official* Odoo 16 docs, not hallucinated.
- **Safe by design** — read operations are free; any operation that *changes* data requires explicit confirmation, and runs under the *individual user's* Odoo permissions.
- **Multilingual** — answers in the same language as the question (FR/EN).
- **Transparent** — the assistant streams its reasoning steps live ("searching models…", "counting records…"), so the user sees *how* the answer was produced.

## 1.4 Target users (personas)

- **Business / operational staff** (sales, accounting, inventory) — ask data questions and perform routine operations without ERP expertise.
- **Managers** — quick KPIs and charts ("revenue per month", "top products") without waiting for a report.
- **New employees** — ask "how do I…" documentation questions.
- **Administrators / power users** — faster execution of routine record edits.

## 1.5 Functional scope (what it can do today)

- Answer documentation questions grounded in the official Odoo 16 docs (with sources).
- Answer quantitative questions on live data: counts, lists, aggregations, grouping by month/year, top-N rankings.
- Generate interactive charts (bar / line / pie) from query results.
- Create, update, delete records; run workflow methods (e.g. confirm an order, post an invoice); send emails — each behind a confirmation gate.
- Maintain per-session conversation history.
- Learn from past successful data queries (agent memory) to answer similar future questions more reliably.

## 1.6 Out of scope / roadmap

- **Predictive ML** (sales forecasting with Prophet/scikit-learn) — planned, not implemented.
- The **Odoo frontend module** (floating chat bubble + Discuss integration) is described in the root README but its source is **not part of this repository** — this repo is the **AI backend** (FastAPI + agents + ETL). The frontend consumes the backend's streaming API.

## 1.7 Why this is technically non-trivial (the "wow")

This is not a thin wrapper around a single LLM call. The hard parts:

- **Routing** the request to the right specialist reliably.
- **Schema grounding** — Odoo has too many models/fields to fit in a prompt, so the system performs *semantic search over the schema itself* to select only the relevant models and fields before generating a query.
- **Correctness of generated queries** against Odoo's real-world quirks (e.g. `customer_rank > 0` instead of a non-existent `is_customer`, JSONB translated fields, XML-RPC dot-notation limits, date-granularity grouping that the RPC layer doesn't support).
- **Self-correction** — the RAG agent grades its own answer and retries; the data agent learns from successful runs.
- **Safety** — write actions gated by human confirmation and scoped to the caller's credentials.

These are the topics the rest of the documentation drills into.
