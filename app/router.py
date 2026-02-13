import ollama
import sys
import os

# Import Config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import LLM_MODEL

def route_question(question: str):
    """
    Analyse l'intention de l'utilisateur.
    Retourne 'SQL' ou 'RAG'.
    """
    prompt = f"""
    Tu es un système de classification. Analyse la question suivante.
    
    Question : "{question}"
    
    Règles :
    1. Si la question demande des données dynamiques (combien, liste, qui, quel est le montant, statistiques) -> Réponds "SQL".
    2. Si la question demande une définition, une procédure ou de l'aide (comment faire, c'est quoi, explique) -> Réponds "RAG".
    
    Réponds UNIQUEMENT par le mot "SQL" ou "RAG". Rien d'autre.
    """
    
    response = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': prompt}])
    choice = response['message']['content'].strip().upper()
    
    # Sécurité au cas où l'IA bavarde
    if "SQL" in choice:
        return "SQL"
    return "RAG" # Par défaut, on va chercher dans la doc

if __name__ == "__main__":
    print(route_question("Comment créer une facture ?")) # Devrait dire RAG
    print(route_question("Combien de clients j'ai ?"))   # Devrait dire SQL