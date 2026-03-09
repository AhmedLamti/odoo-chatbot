import logging
import requests
from agents.state import AgentState
from config.settings import settings

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """You are a router that classifies questions about Odoo.

DASHBOARD agent handles:
- Questions asking for CHARTS, GRAPHS, VISUALIZATIONS
- Questions with: graphique, chart, graph, visualise, montre, affiche, évolution
- Questions about trends over time
- Questions about distributions and proportions
- Questions about top/ranking with visual context

SQL agent handles:
- Questions about counts and numbers (combien, how many, total)
- Questions asking for lists of data
- Questions about specific records

RAG agent handles:
- Questions starting with "Comment" (how to do something)
- Questions about HOW to use or configure Odoo
- Questions about documentation and features

EXAMPLES:
"Montre-moi les ventes par mois" → DASHBOARD
"Graphique des ventes" → DASHBOARD
"Évolution du stock" → DASHBOARD
"Top 10 clients en graphique" → DASHBOARD
"Répartition des produits" → DASHBOARD
"Combien de clients ?" → SQL
"Liste des factures" → SQL
"Comment créer une facture ?" → RAG
"How to install inventory ?" → RAG

Reply with ONLY one word: RAG, SQL, or DASHBOARD
"""


def router_node(state: AgentState) -> AgentState:
    """
    Node de routing — classifie la question et met à jour le state
    """
    question = state["question"]
    logger.info(f"Router Node - Question: '{question}'")

    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "messages": [
                    {"role": "system", "content": ROUTER_PROMPT},
                    {"role": "user", "content": question},
                ],
                "stream": False,
            },
            timeout=30,
        )
        response.raise_for_status()
        agent = response.json()["message"]["content"].strip().upper()

        if "DASHBOARD" in agent:
            agent_used = "DASHBOARD"
        elif "SQL" in agent:
            agent_used = "SQL"
        else:
            agent_used = "RAG"

    except Exception as e:
        logger.error(f"Erreur router: {e}")
        agent_used = "RAG"

    logger.info(f"Router → {agent_used}")
    return {**state, "agent_used": agent_used}
