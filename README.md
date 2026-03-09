# 🤖 Odoo AI Platform

> Plateforme intelligente multi-agents intégrée à Odoo 16 — RAG + SQL + Dashboard + ML (coming soon)

![Python](https://img.shields.io/badge/Python-3.12-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-0.3.21-green)
![Odoo](https://img.shields.io/badge/Odoo-16-purple)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-teal)
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

- 💬 **Poser des questions** sur la documentation Odoo (RAG)
- 🗄️ **Interroger la base de données** sans écrire de SQL
- 📊 **Visualiser des données** sous forme de graphiques interactifs
- 🤖 **Chatbot intégré** dans Odoo via bulle flottante et module Discuss

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Odoo 16 Frontend                      │
│  ┌──────────────┐          ┌──────────────────────────┐  │
│  │Bulle flottante│         │   Module Discuss (Bot)   │  │
│  └──────┬───────┘          └───────────┬──────────────┘  │
└─────────┼──────────────────────────────┼────────────────┘
          │                              │
          └──────────────┬───────────────┘
                         │
             ┌───────────▼───────────┐
             │   FastAPI (port 8000) │
             └───────────┬───────────┘
                         │
             ┌───────────▼───────────┐
             │  LangGraph Orchestrator│
             │    (Router Node)       │
             └──┬──────┬─────────┬───┘
                │      │         │
          ┌─────┘  ┌───┘     ┌───┘
          ▼        ▼         ▼
      RAG Node  SQL Node  Dashboard Node
          │        │         │
          ▼        ▼         ▼
       Qdrant  PostgreSQL  Plotly
      (6031    (Odoo DB)  (Graphiques)
       chunks)
```

---

## Stack technique

| Catégorie | Technologie | Version |
|-----------|-------------|---------|
| LLM Local | Ollama | latest |
| RAG / Routing | mistral | latest |
| SQL | qwen2.5-coder | 7b |
| Embeddings | nomic-embed-text | latest |
| Agents | LangGraph | 0.3.21 |
| Vector Store | Qdrant | 1.17.0 |
| Base de données | PostgreSQL | 14+ |
| API | FastAPI | 0.110+ |
| Graphiques | Plotly | 6.x |
| Tests | pytest | 9.x |
| Odoo | Community | 16.0 |

---

## Installation

### Prérequis

- Python 3.12+
- Conda
- Docker
- Ollama
- Odoo 16 Community

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

### 4. Télécharger les modèles Ollama

```bash
ollama pull mistral
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
```

### 5. Configurer l'environnement

```bash
cp .env.example .env
# Éditer .env avec vos paramètres
```

### 6. Lancer le pipeline ETL

```bash
python scripts/run_schema_extractor.py
python scripts/run_etl.py
```

### 7. Démarrer l'API

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Configuration

Créer un fichier `.env` à la racine :

```env
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=mistral:latest
OLLAMA_SQL_MODEL=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=nomic-embed-text

# PostgreSQL (Odoo)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=Community16
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=odoo_docs

# GitHub (pour ETL)
GITHUB_TOKEN=ghp_...
```

---

## Utilisation

### Via la bulle flottante Odoo

1. Démarrer l'API sur le port 8000
2. Ouvrir Odoo 16
3. Cliquer sur la bulle violette en bas à droite
4. Poser vos questions en français ou anglais

### Via le module Discuss

1. Aller dans **Discuss → 🤖 Assistant IA**
2. Envoyer un message directement dans le canal

### Via l'API REST

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "Combien de clients avons-nous ?"}'
```

### Exemples de questions

```
# Agent RAG (Documentation)
"Comment configurer la comptabilité dans Odoo ?"
"How to create a sales order ?"
"Comment installer le module inventaire ?"

# Agent SQL (Base de données)
"Combien de clients avons-nous ?"
"Liste des factures impayées"
"Quel est le chiffre d'affaires total ?"
"Combien d'employés avons-nous ?"

# Agent Dashboard (Graphiques)
"Montre-moi les ventes par mois en graphique"
"Graphique des top 10 produits vendus"
"Répartition des clients par pays"
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
  "question": "Combien de clients avons-nous ?",
  "session_id": "optionnel"
}
```

### Format réponse

```json
{
  "answer": "Vous avez 2 clients.",
  "agent_used": "SQL",
  "session_id": "uuid",
  "sql_query": "SELECT COUNT(*) FROM res_partner WHERE customer_rank > 0",
  "sources": null,
  "chart_data": null
}
```

---

## Structure du projet

```
odoo-chatbot/
├── agents/
│   ├── graph.py                  # LangGraph - Graph principal
│   ├── state.py                  # State partagé entre agents
│   └── nodes/
│       ├── router_node.py        # Routing RAG/SQL/DASHBOARD
│       ├── rag_node.py           # Agent documentation
│       ├── sql_node.py           # Agent base de données
│       ├── dashboard_node.py     # Agent graphiques
│       └── response_node.py      # Sauvegarde historique
├── etl/
│   ├── loader.py                 # Scraper GitHub docs
│   ├── chunker.py                # Découpage RST intelligent
│   ├── embedder.py               # Génération embeddings
│   ├── schema_extractor.py       # Extraction schéma DB
│   └── pipeline.py               # Orchestration ETL
├── tools/
│   ├── retriever.py              # Recherche sémantique
│   ├── sql_executor.py           # Exécution SQL sécurisée
│   ├── schema_selector.py        # Sélection dynamique tables
│   └── chart_generator.py        # Génération graphiques Plotly
├── db/
│   ├── vector_store.py           # Opérations Qdrant
│   ├── sql_connector.py          # Connexion PostgreSQL
│   ├── schema_cache.py           # Cache schéma YAML
│   └── conversation_store.py     # Historique sessions JSON
├── api/
│   └── main.py                   # FastAPI endpoints
├── odoo_module/
│   └── chatbot_assistant/        # Module Odoo 16
│       ├── models/
│       │   └── chatbot_discuss.py # Intégration Discuss (async)
│       └── static/src/
│           ├── js/
│           │   ├── chatbot_widget.js  # OWL Component
│           │   ├── marked.min.js      # Markdown renderer
│           │   └── plotly.min.js      # Graphiques
│           ├── css/chatbot.css        # Styles Odoo 16
│           └── xml/chatbot_template.xml # Templates OWL
├── config/
│   └── settings.py               # Pydantic settings
├── tests/
│   ├── test_rag_agent.py         # 9/9 ✅
│   ├── test_sql_agent.py         # 13/13 ✅
│   └── test_orchestrator.py      # 10/10 ✅
└── scripts/
    ├── run_etl.py
    └── run_schema_extractor.py
```

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
✅ Phase 2 — LangGraph migration
✅ Phase 2 — Intégration Odoo (bulle flottante + Discuss)
🔄 Phase 3 — Dashboard & Graphiques (en cours)
🔜 Phase 4 — Prédiction ML (Prophet + scikit-learn)
🔜 Phase 5 — Automatisation Odoo (XML-RPC)
```

---

## Auteur

**Ahmed Lamti** — [GitHub](https://github.com/AhmedLamti)

---

## Licence

MIT
