"""
Error Handler Node — gestion centralisée des erreurs du graph
Reçoit state["error"] renseigné par n'importe quel node
et construit une réponse lisible pour l'utilisateur
"""

import logging
from agents.state import AgentState

logger = logging.getLogger(__name__)

# Messages d'erreur selon l'origine
ERROR_MESSAGES = {
    "router": "❌ Erreur de routage — impossible de déterminer le type de question.",
    "sql_generator": "❌ Erreur de génération SQL — impossible de construire la requête.",
    "sql_executor": "❌ Erreur d'exécution SQL — la base de données est inaccessible ou la requête est invalide.",
    "rag": "❌ Erreur RAG — impossible d'interroger la documentation.",
    "action_parser": "❌ Erreur d'analyse — impossible d'extraire l'action demandée.",
    "action_confirm": "❌ Erreur de confirmation — impossible de préparer le résumé de l'action.",
    "action_executor": "❌ Erreur d'exécution — impossible d'effectuer l'action dans Odoo.",
    "chart": "❌ Erreur de génération du graphique.",
    "unknown": "❌ Une erreur inattendue s'est produite.",
}


def error_handler_node(state: AgentState) -> AgentState:
    error = state.get("error", "Erreur inconnue")
    error_origin = state.get("error_origin", "unknown")
    logger.error(f"Error Handler - origin='{error_origin}' | error='{error}'")

    # Message de base selon l'origine
    base_message = ERROR_MESSAGES.get(error_origin, ERROR_MESSAGES["unknown"])

    # Ajouter le détail technique en mode development
    answer = f"{base_message}\n\nDétail : {error}"

    return {
        **state,
        "answer": answer,
        "error": None,  # reset pour ne pas polluer response_node
        "error_origin": None,
    }
