import os
import re
import json
import sys

# --- CONFIGURATION DES CHEMINS ---
# On ajoute le dossier parent au path pour pouvoir importer config.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import RAW_DOCS_PATH

# Chemin source (À adapter si ton dossier documentation n'est pas à la racine du projet)
# On suppose que le dossier "documentation" est à la racine du projet pfe_odoo_ai
SOURCE_ROOT = os.path.join(parent_dir, "documentation", "content", "applications")

def clean_rst(text):
    """ 
    Nettoyage agressif pour enlever le bruit RST.
    (Ton code d'origine, inchangé)
    """
    if ".. toctree::" in text: return "" 
    
    text = re.sub(r":\w+:", "", text) 
    text = re.sub(r"\.\. .*?::.*", "", text)
    text = re.sub(r"`([^`<]+) <[^>]+>`_", r"\1", text)
    text = re.sub(r":\w+:`([^`]+)`", r"\1", text)
    text = re.sub(r"^[=\-~`:\.'^]{3,}", "", text, flags=re.MULTILINE)
    
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if "/" in line and " " not in line: continue
        cleaned_lines.append(line)
    text = "\n".join(cleaned_lines)

    text = re.sub(r"\n\s*\n", "\n\n", text)
    return text.strip()

def extract_documentation():
    """
    Fonction principale appelée par le pipeline.
    """
    print(f"🚀 Démarrage de l'extraction depuis : {SOURCE_ROOT}")
    
    # Vérification que le dossier source existe
    if not os.path.exists(SOURCE_ROOT):
        print(f"❌ ERREUR : Le dossier source n'existe pas : {SOURCE_ROOT}")
        print("   -> Assure-toi d'avoir copié le dossier 'documentation' dans ton projet.")
        return False

    all_documents = []
    skipped_count = 0
    
    for current_root, dirs, files in os.walk(SOURCE_ROOT):
        for file in files:
            if file.endswith(".rst"):
                file_path = os.path.join(current_root, file)
                # On calcule la catégorie (ex: 'accounting')
                category = os.path.basename(os.path.dirname(file_path))
                
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        
                    cleaned_content = clean_rst(content)
                    
                    # Filtre de qualité (> 200 caractères)
                    if len(cleaned_content) > 200:
                        doc_entry = {
                            "source_file": file,
                            "category": category,
                            "full_path": file_path,
                            "content": cleaned_content
                        }
                        all_documents.append(doc_entry)
                    else:
                        skipped_count += 1
                        
                except Exception as e:
                    print(f"⚠️ Erreur sur {file}: {e}")
    
    print("-" * 30)
    print(f"✅ Extraction terminée.")
    print(f"🗑️  Documents ignorés (trop courts/index) : {skipped_count}")
    print(f"💾 Documents valides trouvés : {len(all_documents)}")
    
    # Création du dossier data s'il n'existe pas
    os.makedirs(os.path.dirname(RAW_DOCS_PATH), exist_ok=True)

    # Sauvegarde en JSON
    try:
        with open(RAW_DOCS_PATH, "w", encoding="utf-8") as json_file:
            json.dump(all_documents, json_file, indent=4, ensure_ascii=False)
        print(f"📂 Fichier sauvegardé : {RAW_DOCS_PATH}")
        return True
    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde JSON : {e}")
        return False

# Bloc pour tester ce fichier seul
# if __name__ == "__main__":
#     extract_documentation()