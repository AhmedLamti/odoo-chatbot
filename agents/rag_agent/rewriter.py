import logging

from langchain_groq import ChatGroq

from config.settings import settings

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    api_key=settings.groq_api_key,
    temperature=0,
)

REWRITE_PROMPT = """Tu es un expert en réécriture de requêtes pour les systèmes de recherche sémantique Odoo 16.
Ton objectif : transformer les requêtes utilisateur en formulations optimisées pour maximiser la pertinence des résultats de recherche dans la documentation Odoo 16.

Directives critiques :
- Réécris la requête en anglais clair et structuré
- Élimine le bruit linguistique (articles, prépositions inutiles, formulations conversationnelles)
- Ajoute des termes techniques Odoo pertinents si approprié
- Préserve l'intention originale de la requête
- Retourne UNIQUEMENT la requête réécrite, sans explications, sans commentaires, sans texte additionnel
- Maximum 10 mots

Exemples :
Requête entrante : "comment je configure les factures automatiques"
Requête réécrite : "configure automatic invoice generation Odoo 16"

Requête entrante : "Comment créer une commande de vente ?"
Requête réécrite : "create sale order Odoo 16"

Requête entrante : "Comment configurer la comptabilité ?"
Requête réécrite : "configure accounting settings Odoo 16"

Procède à la réécriture."""


def rewrite_query(question: str) -> str:
    """
    Réécrit la query en anglais pour matcher la doc Odoo.
    """
    try:
        response = llm.invoke([
            {"role": "system", "content": REWRITE_PROMPT},
            {"role": "user", "content": question}
        ])
        rewritten = response.content.strip()
        logger.info(f"Query réécrite: '{question}' → '{rewritten}'")
        return rewritten
    except Exception as e:
        logger.error(f"Erreur rewrite: {e}")
        return question
