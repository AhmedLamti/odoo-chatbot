import logging
from agents.state import AgentState
from tools.cerebras_client import call_cerebras

logger = logging.getLogger(__name__)

# Prompt minimaliste — le modèle doit juste choisir parmi 3 mots
ROUTER_SYSTEM = """Classify the Odoo question. Reply with ONLY the agent name.

SQL: lists, counts, totals, amounts, unpaid, stock, employees data
DASHBOARD: graphique, chart, courbe, visualise, évolution graphique
RAG: comment faire, how to, comment configurer, documentation

Reply ONLY: SQL or DASHBOARD or RAG"""


def router_node(state: AgentState) -> AgentState:
    question = state["question"]
    logger.info(f"Router - Question: '{question}'")

    # Essayer d'abord le fallback par mots-clés (instantané)
    keyword_result = _keyword_fallback(question)

    # Si mots-clés suffisants → pas besoin d'appel API
    if keyword_result != "SQL":  # SQL est le défaut, donc appeler API seulement si RAG ou DASHBOARD détecté
        logger.info(f"Router (keywords) → {keyword_result}")
        return {**state, "agent_used": keyword_result}

    # Pour SQL vs RAG ambigus → appel Cerebras
    try:
        result = call_cerebras(
            prompt=f"Question: {question}\nAgent:",
            system=ROUTER_SYSTEM,
            max_tokens=10,
            temperature=0,
        ).strip().upper()

        if "DASHBOARD" in result:
            agent_used = "DASHBOARD"
        elif "RAG" in result:
            agent_used = "RAG"
        else:
            agent_used = "SQL"

    except Exception as e:
        logger.error(f"Erreur router API: {e}")
        agent_used = keyword_result

    logger.info(f"Router → {agent_used}")
    return {**state, "agent_used": agent_used}


def _keyword_fallback(question: str) -> str:
    q = question.lower()

    # DASHBOARD — mots très spécifiques
    dashboard_words = [
        "graphique", "chart", "courbe", "diagramme",
        "visualise", "montre en graphique", "affiche en graphique"
    ]
    if any(w in q for w in dashboard_words):
        return "DASHBOARD"

    # RAG — mots très spécifiques
    rag_words = [
        "comment faire", "comment configurer", "comment créer",
        "comment installer", "how to", "how do i",
        "what is", "qu'est-ce que", "expliquer", "documentation"
    ]
    if any(w in q for w in rag_words):
        return "RAG"

    # Tout le reste → SQL (listes, chiffres, données)
    return "SQL"
