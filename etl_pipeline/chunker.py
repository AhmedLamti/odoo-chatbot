import json
import os
import sys

# --- CONFIGURATION DES IMPORTS ---
# On ajoute le dossier parent au path pour importer config.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import RAW_DOCS_PATH, CHUNKS_PATH

# Import de la librairie de découpage
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    print("❌ ERREUR : La librairie 'langchain_text_splitters' est manquante.")
    print("👉 Installe-la avec : pip install langchain-text-splitters")
    sys.exit(1)

def chunk_documents(chunk_size=1000, chunk_overlap=200):
    """
    Fonction principale pour découper la documentation (ETL Étape 2).
    Lit depuis RAW_DOCS_PATH et écrit dans CHUNKS_PATH.
    """
    
    # 1. Vérification du fichier source
    if not os.path.exists(RAW_DOCS_PATH):
        print(f"❌ Erreur : Le fichier source est introuvable : {RAW_DOCS_PATH}")
        print("   -> Lance d'abord l'étape 1 (Extraction).")
        return False

    # 2. Chargement des données brutes
    print(f"📖 Chargement de {RAW_DOCS_PATH}...")
    try:
        with open(RAW_DOCS_PATH, "r", encoding="utf-8") as f:
            raw_docs = json.load(f)
    except Exception as e:
        print(f"❌ Erreur lecture JSON : {e}")
        return False

    # 3. Configuration du Splitter
    # Separators : On essaie de couper d'abord aux paragraphes (\n\n), puis lignes (\n), etc.
    separators = ["\n\n", "\n", ".", " ", ""]
    
    print(f"✂️  Configuration du découpage : Size={chunk_size} | Overlap={chunk_overlap}")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=separators,
        length_function=len,
    )

    # 4. Traitement
    chunked_data = []
    total_docs = len(raw_docs)
    
    print(f"🔄 Traitement de {total_docs} documents...")

    for index, doc in enumerate(raw_docs):
        text = doc.get('content', '')
        if not text: 
            continue

        # Découpage du texte
        chunks = text_splitter.split_text(text)
        
        # Création des métadonnées pour chaque morceau
        for i, chunk in enumerate(chunks):
            chunked_data.append({
                # ID unique pour chaque morceau (ex: sales.rst_0, sales.rst_1)
                "id": f"{doc['source_file']}_{i}",
                
                # Le contenu texte
                "text": chunk,
                
                # Métadonnées conservées
                "source": doc['source_file'],
                "category": doc.get('category', 'general'),
                "full_path": doc.get('full_path', ''),
                "chunk_index": i
            })

    # 5. Sauvegarde
    print(f"✅ Terminé ! {len(chunked_data)} chunks générés.")
    
    # Création du dossier si nécessaire
    os.makedirs(os.path.dirname(CHUNKS_PATH), exist_ok=True)
    
    try:
        with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
            json.dump(chunked_data, f, indent=4, ensure_ascii=False)
        print(f"💾 Sauvegarde réussie dans : {CHUNKS_PATH}")
        return True
    except Exception as e:
        print(f"❌ Erreur sauvegarde : {e}")
        return False

# Bloc pour tester ce fichier seul
# if __name__ == "__main__":
#     chunk_documents()