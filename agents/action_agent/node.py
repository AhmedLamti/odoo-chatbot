"""
agents/action_agent/node.py

Point d'entrée LangGraph de l'action agent.

Responsabilités de ce fichier :
  1. Construire l'agent ReAct (LLM + outils)
  2. Exposer action_agent_node() — la fonction appelée par le graphe principal
  3. Exposer run_action_agent() — wrapper de commodité pour les tests / l'API

Aucune logique métier ici : tout est dans tools/ et prompts.py.
"""
import json

from langgraph.prebuilt import create_react_agent

from Graph.state import OrchestratorState
from agents.action_agent.prompts import SYSTEM_PROMPT
from agents.action_agent.tools import ACTION_AGENT_TOOLS
from shared.llm_factory import get_llm, LLMProvider
from shared.utils import get_logger

logger = get_logger(__name__)

# ── Construction de l'agent (une seule fois au démarrage) ─────────────────────

_llm = get_llm(LLMProvider.GROQ_LLAMA33)

def _build_agent(extra_context: str, llm):
    system = SYSTEM_PROMPT + extra_context
    return create_react_agent(
        model=llm,
        tools=ACTION_AGENT_TOOLS,
        prompt=system
    )



# ── Node LangGraph ────────────────────────────────────────────────────────────

def action_agent_node(state: OrchestratorState) -> dict:
    """
    Node LangGraph : reçoit l'état global, exécute l'agent, met à jour l'état.

    Appelé par graph/builder.py — ne jamais appeler directement depuis l'API.
    """
    question = state["question"]
    history = state.get("messages", [])
    session_id = state["session_id"]
    provider = state.get("llm_provider", None)

    llm = get_llm(provider) if provider else _llm
    odoo_user_email = state.get("odoo_user_email")
    odoo_api_key = state.get("odoo_api_key")
    credentials_context = f"""

        Credentials Odoo du user connecté :
        - odoo_user_email = {json.dumps(odoo_user_email)}
        - odoo_api_key = {json.dumps(odoo_api_key)}

        RÈGLE OBLIGATOIRE :
        Pour chaque appel aux outils suivants :
        discover_model,
        get_model_fields,
        search_records,
        create_record,
        update_record,
        delete_record,
        execute_action,
        send_email,

        tu dois TOUJOURS inclure :
        - odoo_user_email
        - odoo_api_key

        Exemple :
        search_record(
          model="sale.order",
          domain="[]",
          fields=["id", "name"],
          limit=10,
          odoo_user_email={json.dumps(odoo_user_email)},
          odoo_api_key={json.dumps(odoo_api_key)}
        )
        """

    agent = _build_agent(credentials_context + credentials_context, llm=llm)
    result = _run(question, session_id, history,agent)

    return {
        "messages": result["messages"],
        "answer": result["answer"],
        "needs_confirmation": result["needs_confirmation"],
        "confirmation_summary": result["confirmation_summary"],
        "pending_action": result["pending_action"],
        "active_agent": "action_agent",
    }


# ── Wrapper de commodité (tests / API directe) ────────────────────────────────

def run_action_agent(question: str, session_id: str, history: list | None = None) -> dict:
    """
    Exécute l'agent pour un tour utilisateur.

    Args:
        question:   Dernier message de l'utilisateur.
        session_id: Identifiant de session fourni par l'appelant (non utilisé en interne).
        history:    Liste de messages LangChain des tours précédents.

    Retourne :
        answer              – texte final de l'assistant
        messages            – liste de messages mise à jour
        needs_confirmation  – True si l'agent attend une approbation
        confirmation_summary – résumé lisible de l'action en attente
    """
    return _run(question, session_id, history or [])


# ── Logique interne ───────────────────────────────────────────────────────────

def _run(question: str, session_id: str, history: list,agent) -> dict:
    messages = list(history)
    messages.append(("user", question))

    response = agent.invoke({"messages": messages})
    answer: str = response["messages"][-1].content

    needs_confirmation, summary, pending_action = _extract_confirmation(response["messages"])

    return {
        "answer": answer,
        "messages": response["messages"],
        "needs_confirmation": needs_confirmation,
        "confirmation_summary": summary,
        "pending_action": pending_action,
    }


def _extract_confirmation(messages: list) -> tuple[bool, str, dict | None]:
    """
    Remonte la liste de messages pour détecter un payload WAITING_CONFIRMATION
    émis par request_confirmation.
    """
    for msg in reversed(messages):
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            continue

        try:
            data = json.loads(content)
            if data.get("status") == "WAITING_CONFIRMATION":
                return (
                    True,
                    data.get("summary", ""),
                    data.get("pending_action"),
                )
        except (json.JSONDecodeError, AttributeError):
            continue

    return False, "", None
