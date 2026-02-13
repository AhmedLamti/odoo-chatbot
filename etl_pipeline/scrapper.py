import os
import json
import sys
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# --- CONFIGURATION DES CHEMINS ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import BASE_URL, HEADERS, RAW_DOCS_PATH



def is_valid_url(url):
    """
    Vérifie si l'URL appartient bien à la section documentation ciblée.
    """
    parsed = urlparse(url)
    return bool(parsed.netloc) and parsed.netloc == "www.odoo.com" and url.startswith(BASE_URL)

def get_page_content(url):
    """
    Télécharge et parse une page HTML.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return BeautifulSoup(response.content, "html.parser")
    except Exception as e:
        print(f"⚠️ Erreur de connexion sur {url} : {e}")
    return None

def clean_text(text):
    """
    Nettoyage simple des espaces et sauts de ligne.
    """
    if not text: return ""
    return re.sub(r'\s+', ' ', text).strip()

def extract_documentation_web():
    """
    Fonction principale de scraping.
    """
    print(f"🚀 Démarrage du scraping depuis : {BASE_URL}")
    
    visited_urls = set()
    urls_to_visit = [BASE_URL]
    all_documents = []
    
    # Limite de sécurité pour éviter une boucle infinie pendant les tests (mettre à 500 ou 1000 pour la prod)
    MAX_PAGES = 300 
    
    while urls_to_visit and len(visited_urls) < MAX_PAGES:
        current_url = urls_to_visit.pop(0)
        
        if current_url in visited_urls:
            continue
            
        print(f"🕷️ Scraping ({len(visited_urls) + 1}/{MAX_PAGES}) : {current_url}")
        soup = get_page_content(current_url)
        visited_urls.add(current_url)
        
        if not soup:
            continue

        # --- 1. Extraction du Contenu ---
        # La doc Odoo met généralement le contenu principal dans <main> ou <div role="main">
        main_content = soup.find("main") or soup.find("div", role="main") or soup.find("article")
        
        if main_content:
            # On enlève les éléments inutiles (boutons, navigation latérale dans le main, etc.)
            for garbage in main_content.find_all(["script", "style", "nav", "aside", "form"]):
                garbage.decompose()

            text_content = clean_text(main_content.get_text(separator="\n"))
            
            # Extraction du titre
            title_tag = soup.find("h1")
            title = title_tag.get_text().strip() if title_tag else "Sans titre"
            
            # Détermination de la catégorie (basée sur l'URL)
            # ex: .../applications/finance/accounting.html -> Category = finance
            path_parts = urlparse(current_url).path.split('/')
            try:
                # On essaie de prendre le dossier après "applications"
                app_index = path_parts.index("applications")
                category = path_parts[app_index + 1] if len(path_parts) > app_index + 1 else "general"
            except ValueError:
                category = "general"

            if len(text_content) > 300: # Garder uniquement les pages avec du contenu substantiel
                all_documents.append({
                    "source_url": current_url,
                    "title": title,
                    "category": category,
                    "content": text_content
                })
        
        # --- 2. Recherche de nouveaux liens (Crawling) ---
        # On cherche tous les liens <a> dans la page pour continuer l'exploration
        for link in soup.find_all("a", href=True):
            full_url = urljoin(current_url, link['href'])
            # On enlève les ancres (#section) pour éviter les doublons
            full_url = full_url.split('#')[0]
            
            if is_valid_url(full_url) and full_url not in visited_urls and full_url not in urls_to_visit:
                urls_to_visit.append(full_url)
        
        # Petite pause pour être poli envers le serveur d'Odoo
        time.sleep(0.1)

    print("-" * 30)
    print(f"✅ Scraping terminé.")
    print(f"💾 Documents récupérés : {len(all_documents)}")
    
    # Création du dossier data s'il n'existe pas
    os.makedirs(os.path.dirname(RAW_DOCS_PATH), exist_ok=True)

    # Sauvegarde
    try:
        with open(RAW_DOCS_PATH, "w", encoding="utf-8") as json_file:
            json.dump(all_documents, json_file, indent=4, ensure_ascii=False)
        print(f"📂 Données sauvegardées dans : {RAW_DOCS_PATH}")
        return True
    except Exception as e:
        print(f"❌ Erreur sauvegarde JSON : {e}")
        return False

# Bloc de test
if __name__ == "__main__":
    import re # Nécessaire si appelé directement pour la fonction clean_text
    extract_documentation_web()