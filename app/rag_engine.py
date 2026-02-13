import ollama
from sentence_transformers import SentenceTransformer
import sys
import os
import re

# --- GESTION DES IMPORTS ---
# On remonte d'un cran pour importer config et database
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import EMBEDDING_MODEL, LLM_MODEL
from app.database import get_db_connection

BLACKLIST_COUNTRIES = [
    "l10n", "localization", 
    "afghanistan", "albania", "algeria", "andorra", "angola", "argentina", "armenia", 
    "australia", "austria", "azerbaijan", "bahrain", "bangladesh", "belarus", "belgium", 
    "bolivia", "bosnia", "brazil", "bulgaria", "cambodia", "cameroon", "canada", 
    "chile", "china", "colombia", "costa rica", "croatia", "cyprus", "czech", 
    "denmark", "dominican republic", "ecuador", "egypt", "estonia", "ethiopia", 
    "finland", "france", "georgia", "germany", "ghana", "greece", "guatemala", 
    "hong kong", "hungary", "iceland", "india", "indonesia", "iran", "iraq", 
    "ireland", "israel", "italy", "jamaica", "japan", "jordan", "kazakhstan", 
    "kenya", "kuwait", "latvia", "lebanon", "lithuania", "luxembourg", "malaysia", 
    "malta", "mexico", "mongolia", "morocco", "myanmar", "nepal", "netherlands", 
    "new zealand", "nigeria", "norway", "oman", "pakistan", "panama", "paraguay", 
    "peru", "philippines", "poland", "portugal", "qatar", "romania", "russia", 
    "saudi arabia", "serbia", "singapore", "slovakia", "slovenia", "south africa", 
    "south korea", "spain", "sri lanka", "sweden", "switzerland", "taiwan", 
    "tanzania", "thailand", "tunisia", "turkey", "uganda", "ukraine", 
    "united arab emirates", "united kingdom", "united states", "uruguay", 
    "uzbekistan", "venezuela", "vietnam", "zambia", "zimbabwe"
]

# Pré-compilation du pattern regex pour optimiser la recherche de pays
# Au lieu de boucler sur chaque pays, on fait une seule recherche regex
BLACKLIST_PATTERN = re.compile(r'\b(' + '|'.join(re.escape(country) for country in BLACKLIST_COUNTRIES) + r')\b', re.IGNORECASE)

# On charge le modèle une seule fois au démarrage pour gagner du temps
print(f"⏳ Chargement du modèle RAG ({EMBEDDING_MODEL})...")
embedding_model = SentenceTransformer(EMBEDDING_MODEL)

def search_relevant_docs(question: str, limit: int = 20):
    """
    Transforme la question en vecteur et cherche les 'limit' morceaux les plus proches
    dans la base de données PostgreSQL (pgvector).
    """
    try:
        # 1. Vectorisation de la question
        query_vector = embedding_model.encode(question).tolist()
        
        # 2. Connexion DB (Lecture seule suffit)
        conn = get_db_connection(admin=False)
        cursor = conn.cursor()
        
        # 3. Requête de recherche vectorielle (Cosine Similarity)
        # L'opérateur <=> calcule la "distance". Plus c'est petit, plus c'est proche.
        sql = """
            SELECT content, url, source_file
            FROM odoo_knowledge
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """
        
        cursor.execute(sql, (query_vector, limit))
        results = cursor.fetchall()
        
        conn.close()
        #  ancien code : return results
        # # On retourne une liste propre de dictionnaires
        # return [
        #     {"content": row[0], "url": row[1], "source": row[2]} 
        #     for row in results
        # ]

        filtered_results = []
        question_lower = question.lower()

        for row in results:
            content, url, source = row
            
            # Sécurité : si l'URL est vide, on ignore
            if not url: 
                continue
            
            # Recherche optimisée : une seule recherche regex au lieu de boucler sur tous les pays
            country_match = BLACKLIST_PATTERN.search(url)
            
            # Si on trouve un pays dans l'URL et qu'il n'est pas dans la question, on pollue
            is_polluted = False
            if country_match:
                matched_country = country_match.group(0).lower()
                if matched_country not in question_lower:
                    is_polluted = True
            
            # Si le doc est propre, on le garde
            if not is_polluted:
                filtered_results.append({
                    "content": content, 
                    "url": url, 
                    "source": source
                })

            # On s'arrête dès qu'on a le nombre désiré de documents PROPRES
            if len(filtered_results) >= limit:
                break
        
        # Sécurité : Si on a tout filtré (trop strict), on rend au moins le 1er résultat brut
        # pour ne pas laisser l'IA sans rien.
        if not filtered_results and results:
            print("⚠️ Attention : Filtre trop strict, retour au document brut.")
            row = results[0]
            filtered_results.append({"content": row[0], "url": row[1], "source": row[2]})

        return filtered_results

    except Exception as e:
        print(f"❌ Erreur de recherche vectorielle : {e}")
        return []

def ask_odoo_rag(question: str):
    """
    Fonction principale : Récupère le contexte + Génère la réponse via LLM.
    """
    
    # 1. RECHERCHE (Retriever)
    print(f"🔎 Recherche d'infos pour : '{question}'...")
    relevant_docs = search_relevant_docs(question, limit=4) # On prend 4 morceaux

    if not relevant_docs:
        return "Je n'ai trouvé aucune information pertinente dans la documentation."

    # 2. CONSTRUCTION DU CONTEXTE
    # On colle les textes trouvés pour les donner à l'IA
    context_text = "\n\n---\n\n".join([doc['content'] for doc in relevant_docs])
    
    # On prépare les sources pour les afficher à la fin
    sources_urls = list(set([doc['url'] for doc in relevant_docs if doc['url']]))

    # 3. GÉNÉRATION (Generator)
    # Le Prompt Engineering est CRUCIAL ici.
    prompt = f"""
    Tu es un expert technique sur l'ERP Odoo.
    Utilise UNIQUEMENT le contexte ci-dessous pour répondre à la question de l'utilisateur.
    
    Règles strictes :
    - Si le contexte contient des informations sur des pays spécifiques (Mexique, Uruguay, etc.) mais que la question est générale, IGNORE ces pays et donne la procédure standard.
    - Si la réponse n'est pas dans le contexte, dis "Je ne trouve pas l'information dans la documentation officielle".
    - Ne jamais inventer de fausses fonctionnalités.
    - Sois clair, concis et pédagogique.
    - Réponds en français.

    CONTEXTE :
    {context_text}

    QUESTION DE L'UTILISATEUR :
    {question}
    """

    print(f"🤖 Génération de la réponse avec {LLM_MODEL}...")
    
    # Appel à Ollama
    response = ollama.chat(model=LLM_MODEL, messages=[
        {'role': 'user', 'content': prompt}
    ])
    
    ai_answer = response['message']['content']

    # 4. MISE EN FORME FINALE
    # On ajoute les sources à la fin de la réponse
    final_output = ai_answer + "\n\n📚 **Sources officielles :**\n"
    for url in sources_urls:
        final_output += f"- {url}\n"

    return final_output

# --- TEST RAPIDE ---
if __name__ == "__main__":
    # Test direct sans interface graphique
    q = input("Pose ta question sur Odoo : ")
    reponse = ask_odoo_rag(q)
    print("\n" + "="*50)
    print(reponse)
    print("="*50)