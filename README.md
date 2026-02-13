# 🤖 Odoo Chatbot Intelligent

Assistant IA hybride combinant **RAG (Retrieval-Augmented Generation)** et **Text-to-SQL** pour répondre aux questions sur la documentation Odoo et les données de production.

## 📋 Description

Ce projet implémente un chatbot intelligent capable de :
- 📚 **Répondre aux questions techniques** sur Odoo en utilisant la documentation officielle (RAG)
- 📊 **Interroger la base de données Odoo** en langage naturel (Text-to-SQL)
- 🎯 **Router automatiquement** les questions vers le bon moteur (documentation vs données)

### Architecture

```
┌──────────────┐
│  Utilisateur │
└──────┬───────┘
       │ Question
       ▼
┌──────────────┐
│   Router     │ ◄── Ollama (Mistral)
└──────┬───────┘
       │
       ├─────────────┬─────────────┐
       │             │             │
       ▼             ▼             ▼
   "SQL"         "RAG"         "Autre"
       │             │
       ▼             ▼
┌─────────────┐  ┌──────────────┐
│ SQL Engine  │  │  RAG Engine  │
├─────────────┤  ├──────────────┤
│ • SQLCoder  │  │ • pgvector   │
│ • PostgreSQL│  │ • Mistral    │
└─────────────┘  └──────────────┘
```

## ✨ Fonctionnalités

### 1. **Moteur RAG (Documentation)**
- Recherche sémantique dans la documentation Odoo via pgvector
- Filtrage intelligent des résultats (exclusion des localisations pays)
- Génération de réponses contextuelles avec Ollama (Mistral)
- Sources affichées avec liens directs vers la documentation

### 2. **Moteur SQL (Données)**
- Conversion langage naturel → SQL avec SQLCoder
- Extraction automatique du schéma Odoo pertinent
- Exécution sécurisée avec utilisateur en lecture seule
- Interprétation des résultats en français

### 3. **Pipeline ETL**
- **Extraction** : Scraping de la documentation Odoo (RST/HTML)
- **Transformation** : Découpage intelligent (chunking) avec LangChain
- **Chargement** : Vectorisation (SentenceTransformers) et stockage PostgreSQL

## 🛠️ Stack Technique

| Composant | Technologie |
|-----------|-------------|
| **Langage** | Python 3.12 |
| **Base de données** | PostgreSQL 16 + pgvector |
| **LLM** | Ollama (Mistral, SQLCoder) |
| **Embeddings** | SentenceTransformers (all-MiniLM-L6-v2) |
| **Chunking** | LangChain Text Splitters |
| **Web Framework** | (À implémenter : FastAPI/Streamlit) |
| **Scraping** | BeautifulSoup4, Requests |

## 📁 Structure du Projet

```
odoo_chatbot/
├── app/
│   ├── __init__.py
│   ├── main.py              # Point d'entrée du chatbot
│   ├── router.py            # Classification des questions
│   ├── rag_engine.py        # Moteur de recherche documentaire
│   ├── sql_engine.py        # Générateur et exécuteur SQL
│   └── database.py          # Gestion des connexions PostgreSQL
├── etl_pipeline/
│   ├── run_pipeline.py      # Orchestrateur ETL
│   ├── scrapper.py          # Extraction documentation web
│   ├── extractor.py         # Extraction fichiers RST locaux
│   ├── chunker.py           # Découpage en morceaux
│   └── embedder.py          # Vectorisation et stockage
├── data/
│   ├── odoo_docs.json       # Documentation brute extraite
│   └── odoo_chunks.json     # Morceaux découpés
├── config.py                # Configuration centralisée
└── README.md
```

## 🚀 Installation

### Prérequis

- Python 3.12+
- PostgreSQL 16+ avec extension pgvector
- Ollama installé avec les modèles `mistral` et `sqlcoder`
- Odoo 16/17 déployé avec une base de données accessible

### 1. Cloner le dépôt

```bash
git clone https://github.com/AhmedLamti/odoo-chatbot.git
cd odoo-chatbot
```

### 2. Créer un environnement virtuel

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### 3. Installer les dépendances

```bash
pip install psycopg2-binary sentence-transformers ollama beautifulsoup4 requests langchain-text-splitters
```

### 4. Configurer PostgreSQL

```sql
-- Créer l'extension pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Créer la table de connaissances
CREATE TABLE odoo_knowledge (
    id SERIAL PRIMARY KEY,
    source_file TEXT,
    category TEXT,
    content TEXT,
    embedding vector(384),  -- Dimension du modèle all-MiniLM-L6-v2
    url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Créer un index pour la recherche vectorielle
CREATE INDEX ON odoo_knowledge USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Créer un utilisateur en lecture seule pour le chatbot
CREATE USER odoo_readonly WITH PASSWORD 'secure_pass';
GRANT CONNECT ON DATABASE your_odoo_db TO odoo_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO odoo_readonly;
```

### 5. Configurer Ollama

```bash
# Télécharger les modèles
ollama pull mistral
ollama pull sqlcoder
```

### 6. Configurer l'application

Modifier [config.py](config.py) avec vos paramètres :

```python
# Base de données
DB_HOST = "localhost"
DB_NAME = "votre_base_odoo"
DB_USER_RO = "odoo_readonly"
DB_PASS_RO = "secure_pass"

# Modèles IA
LLM_MODEL = "mistral"
LLM_MODEL_SQL = "sqlcoder"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
```

## 📖 Utilisation

### 1. Charger la documentation (une seule fois)

```bash
# Option A : Scraper depuis le web
python etl_pipeline/scrapper.py

# Option B : Pipeline complet (recommandé)
python etl_pipeline/run_pipeline.py
```

Ce processus va :
- Extraire la documentation Odoo 17
- La découper en morceaux de 1000 caractères
- Générer les embeddings
- Stocker dans PostgreSQL

### 2. Lancer le chatbot

```bash
python app/main.py
```

### Exemples de questions

**Questions Documentation (RAG) :**
```
Toi : Comment créer une facture dans Odoo ?
Toi : Quelle est la différence entre un bon de livraison et un bon de commande ?
Toi : Explique-moi le workflow d'une vente
```

**Questions Données (SQL) :**
```
Toi : Combien de clients j'ai dans la base ?
Toi : Quel est le montant total des ventes en janvier ?
Toi : Liste les 10 produits les plus vendus
```

## 🔧 Configuration Avancée

### Paramètres RAG

Dans [app/rag_engine.py](app/rag_engine.py) :

```python
# Nombre de documents à récupérer
limit = 20  # Plus = plus de contexte, mais plus lent

# Liste noire pour filtrer les localisations
BLACKLIST_COUNTRIES = ["france", "belgium", ...]
```

### Paramètres SQL

Dans [app/sql_engine.py](app/sql_engine.py) :

```python
# Schéma Odoo personnalisable
target_tables = (
    'res_partner',
    'sale_order',
    'product_template',
    # Ajouter vos tables...
)
```

### Tailles de chunking

Dans [etl_pipeline/chunker.py](etl_pipeline/chunker.py) :

```python
chunk_size = 1000      # Taille max d'un morceau
chunk_overlap = 200    # Chevauchement entre morceaux
```

## 🧪 Tests & Benchmarks

Le projet inclut un système de tests complet pour évaluer les performances et la qualité des réponses.

### Lancer le benchmark complet

```bash
python tests/benchmark.py
```

### Tests par composant

```bash
# Router uniquement
python tests/benchmark.py --router-only

# Moteur SQL uniquement
python tests/benchmark.py --sql-only

# Moteur RAG uniquement
python tests/benchmark.py --rag-only
```

### Métriques évaluées

- ✅ **Précision du router** : Classification SQL vs RAG
- 🎯 **Qualité SQL** : Requêtes valides et pertinentes
- 📚 **Qualité RAG** : Réponses complètes avec mots-clés pertinents
- ⏱️ **Performances** : Temps de génération et d'exécution

Les rapports sont sauvegardés dans `tests/results/` au format JSON.

📖 Voir [tests/README.md](tests/README.md) pour plus de détails.

## 📊 Performances

- **Recherche vectorielle** : ~100-200ms (avec index ivfflat)
- **Génération SQL** : ~2-5s (selon complexité)
- **Génération réponse RAG** : ~3-8s (selon longueur contexte)

## 🐛 Dépannage

### Erreur "pgvector extension not found"
```sql
CREATE EXTENSION vector;
```

### Erreur Ollama "model not found"
```bash
ollama list  # Vérifier les modèles installés
ollama pull mistral
```

### Erreur de connexion PostgreSQL
- Vérifier que PostgreSQL est démarré
- Vérifier les credentials dans [config.py](config.py)
- Tester manuellement : `psql -h localhost -U odoo_readonly -d your_db`

## 🔮 Roadmap

- [ ] Interface web (Streamlit/FastAPI)
- [ ] Support multilingue
- [ ] Cache des requêtes fréquentes
- [ ] Fine-tuning du modèle SQL
- [ ] Historique de conversation
- [ ] Export des réponses (PDF/Markdown)
- [ ] Feedback utilisateur sur la qualité des réponses

## 📝 Licence

Ce projet a été développé dans le cadre d'un Projet de Fin d'Études (PFE).

## 👤 Auteur

**Lamti Ahmed**
- GitHub: [@AhmedLamti](https://github.com/AhmedLamti)
- Email: lamti.ahmeed@gmail.com

## 🙏 Remerciements

- [Odoo](https://www.odoo.com) pour la documentation
- [Ollama](https://ollama.ai) pour les modèles LLM locaux
- [pgvector](https://github.com/pgvector/pgvector) pour la recherche vectorielle
- [SentenceTransformers](https://www.sbert.net/) pour les embeddings

---

⭐ Si ce projet vous a été utile, n'hésitez pas à mettre une étoile !
