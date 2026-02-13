import os

# --- CONFIGURATION DE LA BASE DE DONNÉES ---
DB_HOST = "localhost"
DB_NAME = "test"

# Utilisateur Admin)
DB_USER_ADMIN = "odoo16"
DB_PASS_ADMIN = "odoo"

# Utilisateur Lecture Seule (Pour le Chatbot - Sécurité)
# Si tu ne l'as pas encore créé en SQL, utilise admin pour l'instant
DB_USER_RO = "odoo_readonly" 
DB_PASS_RO = "secure_pass"

# --- INTELLIGENCE ARTIFICIELLE ---
# Modèle pour transformer le texte en chiffres
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Modèle pour générer le texte (Ollama)
LLM_MODEL = "mistral"
LLM_MODEL_SQL = "sqlcoder"

# --- PATHS (Chemins des fichiers) ---
# Pour que Python trouve toujours les fichiers json, peu importe d'où on lance le script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

RAW_DOCS_PATH = os.path.join(DATA_DIR, "odoo_docs.json")
CHUNKS_PATH = os.path.join(DATA_DIR, "odoo_chunks.json")

# --- CONFIGURATION DU SCRAPER ---
# On cible la documentation des Applications Odoo 17 (version stable actuelle)
BASE_URL = "https://www.odoo.com/documentation/17.0/fr/applications"
# Pour le français, utilise : "https://www.odoo.com/documentation/17.0/fr/applications"

# Headers pour ne pas être bloqué (simule un navigateur)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}