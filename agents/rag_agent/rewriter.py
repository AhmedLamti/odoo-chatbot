# ── agents/rag_agent/rewriter.py ──────────────────────────────────────────────
# Réécriture de la requête utilisateur en anglais technique Odoo 16.
#
# Règle : aucun LLM instancié au niveau du module.
# Le LLM est toujours fourni par l'appelant (agent.py via llm_factory).
# ──────────────────────────────────────────────────────────────────────────────

import logging

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# ── Prompt ─────────────────────────────────────────────────────────────────────

_REWRITE_PROMPT = """Tu es un expert en réécriture de requêtes pour les systèmes
de recherche sémantique Odoo 16.

Ton objectif : transformer les requêtes utilisateur en formulations optimisées
pour maximiser la pertinence des résultats de recherche dans la documentation Odoo 16.

Directives critiques :
- Réécris la requête en anglais clair et structuré
- Élimine le bruit linguistique (articles, prépositions inutiles,
  formulations conversationnelles)
- Ajoute des termes techniques Odoo pertinents si approprié
- Préserve l'intention originale de la requête
- Retourne UNIQUEMENT la requête réécrite, sans explications,
  sans commentaires, sans texte additionnel
- Maximum 10 mots

Exemples :
Requête entrante : "comment je configure les factures automatiques"
Requête réécrite : "configure automatic invoice generation Odoo 16"

Requête entrante : "Comment créer une commande de vente ?"
Requête réécrite : "create sale order Odoo 16"

Requête entrante : "Comment configurer la comptabilité ?"
Requête réécrite : "configure accounting settings Odoo 16"

Procède à la réécriture."""


# ── Fonction publique ──────────────────────────────────────────────────────────


def rewrite_query(question: str, llm: BaseChatModel) -> str:
    """
    Réécrit *question* en anglais technique pour maximiser la pertinence
    de la recherche sémantique dans la documentation Odoo 16.

    Args:
        question: La question originale de l'utilisateur (toute langue).
        llm:      Instance LangChain déjà construite par llm_factory.

    Returns:
        La requête réécrite, ou *question* en cas d'erreur (fail-safe).
    """
    try:
        response = llm.invoke([
            {"role": "system", "content": _REWRITE_PROMPT},
            {"role": "user",   "content": question},
        ])
        rewritten = response.content.strip()
        logger.info("[rewriter] '%s' → '%s'", question[:60], rewritten[:60])
        return rewritten
    except Exception as exc:
        logger.error("[rewriter] Erreur lors de la réécriture : %s", exc)
        return question  # fallback : question originale
