# 🤖 Odoo AI Platform

> Plateforme intelligente multi-agents intégrée à Odoo 16 — RAG + SQL + Dashboard + ML (coming soon)

![Python](https://img.shields.io/badge/Python-3.12-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-0.3.21-green)
![Odoo](https://img.shields.io/badge/Odoo-16-purple)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-teal)
![Plotly](https://img.shields.io/badge/Plotly-6.x-orange)
![Tests](https://img.shields.io/badge/Tests-32%2F32-brightgreen)

---

## 📋 Table des matières

- [Présentation](#présentation)
- [Architecture](#architecture)
- [Stack technique](#stack-technique)
- [Installation](#installation)
- [Configuration](#configuration)
- [Utilisation](#utilisation)
- [API Endpoints](#api-endpoints)
- [Structure du projet](#structure-du-projet)
- [Roadmap](#roadmap)

---

## Présentation

**Odoo AI Platform** permet aux utilisateurs d'interagir avec leur système Odoo 16 en **langage naturel** :

- 💬 **Poser des questions** sur la documentation Odoo (RAG via Google Gemini)
- 🗄️ **Interroger la base de données** sans écrire de SQL (Cerebras)
- 📊 **Visualiser des données** sous forme de graphiques interactifs Plotly (Groq)
- 📈 **Analyser automatiquement** les graphiques avec des insights business (Groq)
- 🤖 **Chatbot intégré** dans Odoo via bulle flottante et module Discuss

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Odoo 16 Frontend                      │
│  ┌──────────────────┐     ┌──────────────────────────┐  │
│  │  Bulle flottante  │     │   Module Discuss (Bot)   │  │
│  │  (OWL Component) │     │   (Async Thread)         │  │
│  └────────┬─────────┘     └───────────┬──────────────┘  │
└───────────┼───────────────────────────┼────────────────┘
            │                           │
            └─────────────┬─────────────┘
                          │
              ┌───────────▼───────────┐
              │   FastAPI (port 8000) │
              └───────────┬───────────┘
                          │
              ┌───────────▼────────────┐
              │  LangGraph Orchestrator │
              │     (Router Node)       │
              └──┬───────────┬──────────┘
                 │           │
            ┌────┘       ┌───┘
            ▼            ▼
        RAG Node      SQL Node
      (Gemini API)  (Cerebras API)
                         │
                   ┌─────┴──────┐
                   │            │
               (SQL only)  (DASHBOARD)
                   │            │
                   │        Chart Node
                   │        (Groq API)
                   │            │
                   │       Analysis Node
                   │        (Groq API)
                   │            │
                   └─────┬──────┘
                         │
                  Response Node
```

---

## Stack technique

### APIs LLM — Architecture Multi-API

| Node | API | Modèle | Rôle |
|------|-----|--------|------|
| **Router** | Cerebras | llama3.1-8b | Routing ultra-rapide (keywords first) |
| **RAG** | Google Gemini | gemini-2.0-flash | Compréhension documentation |
| **SQL Gen** | Cerebras | llama3.1-8b | Génération requêtes SQL |
| **SQL Interpret** | Cerebras | llama3.1-8b | Interprétation résultats |
| **Chart** | Groq | llama-3.3-70b | Classification graphiques |
| **Analysis** | Groq | llama-3.3-70b | Insights business |
| **Embeddings** | Ollama | nomic-embed-text | Local, gratuit, stable |
| **Schema LLM** | Cerebras | llama3.1-8b | Sélection tables dynamique |

### Infrastructure

| Catégorie | Technologie | Version |
|-----------|-------------|---------|
| Agents | LangGraph | 0.3.21 |
| Vector Store | Qdrant | 1.17.0 |
| Base de données | PostgreSQL | 14+ |
| API | FastAPI | 0.110+ |
| Graphiques | Plotly | 6.x |
| Markdown | marked.js | latest |
| Tests | pytest | 9.x |
| Odoo | Community | 16.0 |

---

## Installation

### Prérequis

- Python 3.12+
- Conda
- Docker
- Ollama (pour les embeddings uniquement)
- Odoo 16 Community
- Clés API : Cerebras, Google Gemini, Groq

### 1. Cloner le projet

```bash
git clone https://github.com/AhmedLamti/odoo-chatbot.git
cd odoo-chatbot
```

### 2. Créer l'environnement

```bash
conda create -n odoo-chatbot python=3.12
conda activate odoo-chatbot
pip install -r requirements.txt
```

### 3. Démarrer Qdrant

```bash
docker run -d --name qdrant \
  -p 6333:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

### 4. Télécharger le modèle d'embeddings

```bash
ollama pull nomic-embed-text
```

### 5. Configurer l'environnement

```bash
cp .env.example .env
# Éditer .env avec vos clés API et paramètres
```

### 6. Lancer le pipeline ETL

```bash
python scripts/run_schema_extractor.py
python scripts/run_etl.py
```

### 7. Démarrer l'API

```bash
conda activate odoo-chatbot
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Configuration

Créer un fichier `.env` à la racine :

```env
# ── Ollama (embeddings uniquement) ──────────────
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_MODEL=nomic-embed-text

# ── Cerebras (Router + SQL) ──────────────────────
CEREBRAS_API_KEY=csk-...
CEREBRAS_MODEL=llama3.1-8b

# ── Google Gemini (RAG) ──────────────────────────
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.0-flash

# ── Groq (Chart + Analysis) ──────────────────────
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile

# ── PostgreSQL (Odoo) ────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=Community16
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo

# ── Qdrant ───────────────────────────────────────
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=odoo_docs

# ── GitHub (pour ETL docs) ───────────────────────
GITHUB_TOKEN=ghp_...
```

---

## Utilisation

### Via la bulle flottante Odoo

1. Démarrer l'API sur le port 8000
2. Ouvrir Odoo 16
3. Cliquer sur la bulle violette en bas à droite
4. Poser vos questions en français ou anglais
5. Cliquer sur un graphique pour l'agrandir en modal

### Via le module Discuss

1. Aller dans **Discuss → 🤖 Assistant IA**
2. Envoyer un message directement dans le canal
3. Le bot répond de manière asynchrone

### Via l'API REST

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Combien de clients avons-nous ?"}'
```

### Exemples de questions

```bash
# Agent RAG — Documentation (Gemini)
"Comment configurer la comptabilité dans Odoo ?"
"How to create a sales order ?"
"Comment installer le module inventaire ?"

# Agent SQL — Base de données (Cerebras)
"Combien de clients avons-nous ?"
"Liste des factures impayées"
"Quel est le chiffre d'affaires total ?"
"Meilleures commandes clients"
"Vendeurs par chiffre d'affaires"
"Stock disponible par produit"
"Employés par département"

# Agent Dashboard — Graphiques + Analyse (Groq)
"Graphique des ventes par mois"
"Courbe d'évolution du chiffre d'affaires"
"Répartition des clients par pays"
"Top 10 produits vendus en graphique"
"Graphique des employés par département"
```

---

## API Endpoints

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| GET | `/` | Info API |
| GET | `/health` | État des services |
| POST | `/chat` | Question → Réponse |
| GET | `/history/{id}` | Historique session |
| DELETE | `/history/{id}` | Supprimer historique |
| GET | `/sessions` | Lister sessions actives |
| GET | `/sql/schema` | Schéma base de données |
| GET | `/rag/search` | Recherche vectorielle |
| GET | `/docs` | Swagger UI |

### Format requête `/chat`

```json
{
  "question": "Graphique des ventes par mois",
  "session_id": "optionnel"
}
```

### Format réponse

```json
{
  "answer": "Voici le graphique...\n\n### 📊 Analyse\n...",
  "agent_used": "DASHBOARD",
  "session_id": "uuid",
  "sql_query": "SELECT ...",
  "sources": null,
  "chart_data": "{JSON Plotly}"
}
```

---

## Structure du projet

```
odoo-chatbot/
├── agents/
│   ├── graph.py                    # LangGraph — orchestration
│   ├── state.py                    # State partagé entre agents
│   └── nodes/
│       ├── router_node.py          # Routing keywords-first + Cerebras
│       ├── rag_node.py             # Agent documentation → Gemini
│       ├── sql_node.py             # Agent SQL → Cerebras
│       ├── chart_node.py           # Agent graphiques → Groq
│       ├── analysis_node.py        # Agent analyse business → Groq
│       └── response_node.py        # Sauvegarde historique
├── tools/
│   ├── cerebras_client.py          # Client Cerebras centralisé
│   ├── gemini_client.py            # Client Google Gemini
│   ├── groq_client.py              # Client Groq
│   ├── retriever.py                # Recherche sémantique Qdrant
│   ├── sql_executor.py             # Exécution SQL sécurisée
│   ├── schema_selector.py          # Sélection dynamique tables + sémantique
│   └── chart_generator.py          # Génération graphiques Plotly
├── config/
│   ├── settings.py                 # Pydantic settings (multi-API)
│   ├── schema_descriptions.py      # Descriptions sémantiques colonnes
│   └── few_shot_examples.py        # Exemples SQL + Dashboard
├── etl/
│   ├── loader.py                   # Scraper GitHub docs
│   ├── chunker.py                  # Découpage RST intelligent
│   ├── embedder.py                 # Génération embeddings Ollama
│   ├── schema_extractor.py         # Extraction schéma PostgreSQL
│   └── pipeline.py                 # Orchestration ETL
├── db/
│   ├── vector_store.py             # Opérations Qdrant
│   ├── sql_connector.py            # Connexion PostgreSQL
│   ├── schema_cache.py             # Cache schéma YAML
│   └── conversation_store.py       # Historique sessions JSON
├── api/
│   └── main.py                     # FastAPI endpoints
├── odoo_module/
│   └── chatbot_assistant/          # Module Odoo 16
│       ├── models/
│       │   └── chatbot_discuss.py  # Intégration Discuss async
│       └── static/src/
│           ├── js/
│           │   ├── chatbot_widget.js    # OWL Component
│           │   ├── marked.min.js        # Markdown renderer
│           │   └── plotly.min.js        # Graphiques interactifs
│           ├── css/chatbot.css          # Styles Odoo 16
│           └── xml/chatbot_template.xml # Templates OWL + Modal
├── tests/
│   ├── test_rag_agent.py           # 9/9 ✅
│   ├── test_sql_agent.py           # 13/13 ✅
│   └── test_orchestrator.py        # 10/10 ✅
├── scripts/
│   ├── run_etl.py
│   └── run_schema_extractor.py
├── data/
│   ├── schema.yaml                 # Schéma PostgreSQL extrait
│   └── conversations/              # Historique sessions JSON
├── .env.example
├── requirements.txt
└── README.md
```

---

## LangGraph — Flow des agents

```
Question
   │
   ▼
Router Node (keywords-first → Cerebras si ambigu)
   ├── RAG ──── Gemini ────────────────────────── Response Node
   ├── SQL ──── Cerebras ──────────────────────── Response Node
   └── DASHBOARD ── Cerebras ── Groq ── Groq ──── Response Node
                   (SQL gen)  (chart) (analysis)
```

---

## Fonctionnalités Odoo Module

### Bulle flottante
- Positionnée en bas à droite sur toutes les pages Odoo
- Rendu Markdown des réponses (marked.js)
- Graphiques interactifs Plotly intégrés
- Modal d'agrandissement au clic sur le graphique
- Spinner animé pendant le chargement
- Badge agent utilisé (RAG / SQL / DASHBOARD)
- Suggestions de questions au démarrage
- Historique de conversation par session

### Module Discuss
- Canal dédié **🤖 Assistant IA**
- Réponses asynchrones (thread Python séparé)
- Pas de blocage de l'interface Odoo

---

## Tests

```bash
conda activate odoo-chatbot
pytest tests/ -v
```

```
tests/test_orchestrator.py  → 10/10 ✅
tests/test_rag_agent.py     → 9/9  ✅
tests/test_sql_agent.py     → 13/13 ✅
─────────────────────────────────────
Total                       → 32/32 ✅
```

---

## Roadmap

```
✅ Phase 1 — RAG + SQL + API + Tests (32/32)
✅ Phase 2 — Migration LangGraph 0.3.21
✅ Phase 2 — Intégration Odoo (bulle flottante + Discuss async)
✅ Phase 3 — Dashboard & Graphiques (Plotly + Analyse business)
✅ Phase 3 — Architecture Multi-API (Cerebras + Gemini + Groq)
✅ Phase 3 — Schema sémantique (descriptions colonnes métier)
✅ Phase 3 — Router keywords-first (latence réduite)
🔜 Phase 4 — Prédiction ML (Prophet + scikit-learn)
🔜 Phase 5 — Automatisation Odoo (XML-RPC)
```

---

## Auteur

**Ahmed Lamti** — [GitHub](https://github.com/AhmedLamti)

---

## Licence

MIT
