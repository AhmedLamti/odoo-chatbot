import logging
from agents.state import AgentState
from tools.cerebras_client import call_cerebras

logger = logging.getLogger(__name__)

ROUTER_SYSTEM = """You classify an Odoo support question into exactly one agent. Reply with ONLY one word.

DASHBOARD: user explicitly asks for a chart, graph, plot, curve, or visual representation of data.
RAG: user asks HOW to do something, asks for configuration steps, installation, or Odoo documentation.
ACTION: user wants to CREATE, UPDATE, VALIDATE, SEND or MODIFY something directly in Odoo.
SQL: user asks for data, numbers, lists, counts, totals, or facts from the database.

CRITICAL RULES:
- ACTION = user wants to DO something in Odoo (créer, valider, ajouter, modifier, envoyer)
- RAG = user wants to KNOW HOW to do something (comment, how to)
- SQL = user wants to READ data (no modification)
- Questions about DATA or NUMBERS → SQL

Reply ONLY with one word: SQL or DASHBOARD or RAG or ACTION"""


def router_node(state: AgentState) -> AgentState:
    question = state["question"]
    logger.info(f"Router - Question: '{question}'")

    try:
        keyword_result = _keyword_fallback(question)

        if keyword_result in ("DASHBOARD", "RAG", "ACTION"):
            logger.info(f"Router (keywords) → {keyword_result}")
            return {**state, "agent_used": keyword_result, "error": None}

        result = (
            call_cerebras(
                prompt=f"Question: {question}\nAgent:",
                system=ROUTER_SYSTEM,
                max_tokens=10,
                temperature=0,
            )
            .strip()
            .upper()
        )

        if "DASHBOARD" in result:
            agent_used = "DASHBOARD"
        elif "RAG" in result:
            agent_used = "RAG"
        elif "ACTION" in result:
            agent_used = "ACTION"
        else:
            agent_used = "SQL"

        logger.info(f"Router (Cerebras) → {agent_used}")
        return {**state, "agent_used": agent_used, "error": None}

    except Exception as e:
        logger.error(f"Erreur router: {e}")
        return {
            **state,
            "agent_used": "SQL",  # fallback safe
            "error": str(e),
            "error_origin": "router",
        }


def _keyword_fallback(question: str) -> str:
    q = question.lower()

    dashboard_words = [
        "graphique",
        "chart",
        "courbe",
        "diagramme",
        "histogramme",
        "camembert",
        "pie chart",
        "bar chart",
        "visualise",
        "visualiser",
        "montre en graphique",
        "affiche en graphique",
        "évolution graphique",
        "plot",
        "visualisation",
        "en graphique",
        "sous forme de graphique",
    ]
    if any(w in q for w in dashboard_words):
        return "DASHBOARD"

    action_words = [
        "crée une commande",
        "créer une commande",
        "crée une facture",
        "créer une facture",
        "valide la facture",
        "valider la facture",
        "valide la commande",
        "valider la commande",
        "confirme la commande",
        "confirmer la commande",
        "ajoute un employé",
        "ajouter un employé",
        "crée un employé",
        "créer un employé",
        "mets à jour le stock",
        "mettre à jour le stock",
        "modifie le prix",
        "modifier le prix",
        "mets à jour le prix",
        "mettre à jour le prix",
        "envoie un email",
        "envoyer un email",
        "envoie un mail",
        "envoyer un mail",
        "update stock",
        "create order",
        "create invoice",
        "validate invoice",
        "send email",
        "add employee",
    ]
    if any(w in q for w in action_words):
        return "ACTION"

    rag_words = [
        "comment faire",
        "comment configurer",
        "comment créer",
        "comment installer",
        "comment utiliser",
        "comment activer",
        "comment paramétrer",
        "comment mettre en place",
        "comment générer",
        "how to",
        "how do i",
        "how can i",
        "how do you",
        "documentation",
        "tutoriel",
        "guide",
        "étapes pour",
        "steps to",
        "procédure",
        "procedure",
        "quelle est la procédure",
        "what are the steps",
    ]
    if any(w in q for w in rag_words):
        return "RAG"

    return "SQL"
