import sys
import os
import time

# --- GESTION DES CHEMINS ---
# Cette astuce permet d'importer les fichiers frères (extractor, chunker...)
# même si on lance le script depuis la racine du projet.
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Import des modules que tu as créés
try:
    from extractor import extract_documentation
    from chunker import chunk_documents
    from embedder import embed_and_store
except ImportError as e:
    print(f"❌ Erreur d'import : {e}")
    print("   -> Vérifie que extractor.py, chunker.py et embedder.py sont bien dans le dossier etl_pipeline.")
    sys.exit(1)

def run_full_pipeline():
    """
    Exécute la chaîne complète : Extraction -> Découpage -> Vectorisation -> Stockage.
    """
    print("\n" + "="*60)
    print("🚀  DEMARRAGE DU PIPELINE ETL (Odoo AI Project)")
    print("="*60)
    
    start_time = time.time()

    # --- ÉTAPE 1 : EXTRACTION ---
    print("\n[1/3] 🕷️  EXTRACTION DU CONTENU (RST -> JSON)...")
    step1_start = time.time()
    
    # On lance la fonction. Si elle retourne False (échec), on arrête tout.
    if not extract_documentation():
        print("❌ Arrêt critique : L'extraction a échoué.")
        return

    print(f"   ⏱️  Temps étape 1 : {time.time() - step1_start:.2f}s")


    # --- ÉTAPE 2 : DÉCOUPAGE (CHUNKING) ---
    print("\n[2/3] ✂️  DÉCOUPAGE EN MORCEAUX (CHUNKING)...")
    step2_start = time.time()
    
    # On peut paramétrer la taille ici si besoin (ex: chunk_size=800)
    if not chunk_documents(chunk_size=1000, chunk_overlap=200):
        print("❌ Arrêt critique : Le découpage a échoué.")
        return

    print(f"   ⏱️  Temps étape 2 : {time.time() - step2_start:.2f}s")


    # --- ÉTAPE 3 : EMBEDDING & STOCKAGE ---
    print("\n[3/3] 🧠  VECTORISATION ET INSERTION SQL...")
    step3_start = time.time()
    
    try:
        embed_and_store()
    except Exception as e:
        print(f"❌ Erreur critique durant l'embedding : {e}")
        return

    print(f"   ⏱️  Temps étape 3 : {time.time() - step3_start:.2f}s")


    # --- FIN ---
    total_time = time.time() - start_time
    print("\n" + "="*60)
    print(f"✅ PIPELINE TERMINÉ AVEC SUCCÈS")
    print(f"⏱️  Temps total d'exécution : {total_time:.2f} secondes")
    print("="*60)

if __name__ == "__main__":
    # Optionnel : Demander confirmation pour éviter d'écraser/dupliquer par erreur
    print("⚠️  ATTENTION : Ce script va traiter toute la documentation.")
    print("Assure-toi que ta base de données est prête.")
    
    confirm = input("Voulez-vous lancer le traitement complet ? (y/n) : ")
    if confirm.lower() == 'y':
        run_full_pipeline()
    else:
        print("Opération annulée.")