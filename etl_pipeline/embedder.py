import json
import os
import sys
from sentence_transformers import SentenceTransformer

# --- GESTION DES IMPORTS (Le "Bridge") ---
# On ajoute le dossier racine du projet au PATH pour pouvoir importer 'app' et 'config'
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# 1. On importe la config globale
from config import CHUNKS_PATH, EMBEDDING_MODEL

# 2. On réutilise ta fonction de connexion existante !
# C'est ici qu'on évite la redondance.
from app.database import get_db_connection

# Base URL Odoo
ODOO_DOC_BASE_URL = "https://www.odoo.com/documentation/17.0/applications/"

def embed_and_store():
    # A. Vérification fichier
    if not os.path.exists(CHUNKS_PATH):
        print(f"❌ Fichier introuvable : {CHUNKS_PATH}")
        return

    # B. Connexion via ton module app (Mode Admin = True pour écrire)
    print("🔌 Connexion à la base de données via app.database...")
    conn = get_db_connection(admin=True) 
    
    if not conn:
        print("❌ Impossible de se connecter (Vérifie app/database.py)")
        return
        
    cursor = conn.cursor()

    # C. Chargement Modèle
    print(f"🧠 Chargement du modèle {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    # D. Lecture JSON
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    total = len(chunks)
    print(f"🚀 Embedding de {total} éléments...")

    # E. Boucle d'insertion
    for i, chunk in enumerate(chunks):
        try:
            # Préparation des données
            text = chunk['text']
            
            # Calcul URL
            clean_name = chunk['source'].replace(".rst", ".html").replace(".md", ".html")
            url = ODOO_DOC_BASE_URL + clean_name
            
            # Calcul Vecteur
            vector = model.encode(text).tolist()

            # Insertion SQL
            sql = """
                INSERT INTO odoo_knowledge (source_file, category, content, embedding, url)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (chunk['source'], chunk['category'], text, vector, url))

            if i % 50 == 0:
                print(f"   Progression : {i}/{total}")

        except Exception as e:
            print(f"⚠️ Erreur ligne {i} : {e}")
            conn.rollback() # On annule juste cette ligne en cas d'erreur
            continue

    # F. Validation finale
    conn.commit()
    cursor.close()
    conn.close()
    print("✅ Terminé ! Base de données mise à jour proprement.")

# if __name__ == "__main__":
#     embed_and_store()