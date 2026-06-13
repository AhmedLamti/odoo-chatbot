"""
agents/action_agent/node.py

Point d'entrée LangGraph de l'action agent.

Responsabilités de ce fichier :
  1. Construire l'agent ReAct (LLM + outils)
  2. Exposer action_agent_node() — la fonction appelée par le graphe principal
  3. Exposer run_action_agent()  — wrapper de commodité pour les tests / l'API
  4. Streamer le raisonnement étape par étape via un callback (même pattern data agent)

Aucune logique métier ici : tout est dans tools.py et prompts.py.
"""
import json
from typing import Callable

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from Graph.state import OrchestratorState
from agents.action_agent.prompts import SYSTEM_PROMPT
from agents.action_agent.tools import ACTION_AGENT_TOOLS
from shared.llm_factory import get_llm, LLMProvider
from shared.utils import get_logger

logger = get_logger(__name__)

# ── LLM par défaut ─────────────────────────────────────────────────────────────

_llm = get_llm(LLMProvider.GROQ_LLAMA33)

# ── Libellés lisibles des outils ──────────────────────────────────────────────

TOOL_LABELS: dict[str, str] = {
    "discover_model": "Identification du modèle Odoo",
    "get_model_fields": "Récupération des champs du modèle",
    "search_records": "Recherche d'enregistrements",
    "create_record": "Création d'un enregistrement",
    "update_record": "Modification d'un enregistrement",
    "delete_record": "Suppression d'un enregistrement",
    "execute_action": "Exécution d'une action workflow",
    "send_email": "Envoi d'un email",
    "request_confirmation": "Demande de confirmation utilisateur",
}

# ── Type du callback de progression ───────────────────────────────────────────
# Signature : (numéro_étape: int, message: str) -> None
StepCallback = Callable[[int, str], None]


def _default_step_callback(step: int, message: str) -> None:
    """Affichage console — remplacé par un callback SSE/WebSocket en prod."""
    print(f"  Étape {step} — {message}")


# ── Formateurs d'étapes ────────────────────────────────────────────────────────


def _format_tool_args(tool_name: str, args: dict) -> str:
    """Résume les arguments d'un appel d'outil en une ligne lisible."""
    # On masque les credentials dans l'affichage
    clean = {k: v for k, v in args.items() if k not in ("odoo_user_email", "odoo_api_key")}

    if tool_name == "search_records":
        fields = json.loads(clean.get("fields", '["id","name"]'))
        return (
            f"modèle={clean.get('model', '?')}  "
            f"filters={clean.get('filters', '[]')}  "
            f"champs={fields[:4]}{'...' if len(fields) > 4 else ''}"
        )
    if tool_name in ("create_record", "update_record"):
        return f"modèle={clean.get('model', '?')}  values={str(clean.get('values', '{}'))[:60]}"
    if tool_name == "delete_record":
        return f"modèle={clean.get('model', '?')}  id={clean.get('record_id', '?')}"
    if tool_name == "execute_action":
        return (
            f"modèle={clean.get('model', '?')}  "
            f"méthode={clean.get('method', '?')}  "
            f"id={clean.get('record_id', '?')}"
        )
    if tool_name == "send_email":
        return f"partner_id={clean.get('partner_id', '?')}  sujet='{clean.get('subject', '?')}'"
    if tool_name == "discover_model":
        return f"intent='{clean.get('intent', '?')}'"
    if tool_name == "get_model_fields":
        return f"modèle={clean.get('model', '?')}"
    if tool_name == "request_confirmation":
        return f"type={clean.get('action_type', '?')}  résumé='{str(clean.get('action_summary', '?'))[:50]}'"

    return "  ".join(f"{k}={str(v)[:40]}" for k, v in clean.items())


def _format_tool_result(tool_name: str, content: str) -> str:
    """Résume le résultat d'un outil en une ligne lisible."""
    try:
        data = json.loads(content)
        if isinstance(data, int):
            return str(data)
        if isinstance(data, list):
            return f"{len(data)} enregistrement(s) retourné(s)"
        if isinstance(data, dict):
            # Cas confirmation
            if data.get("status") == "WAITING_CONFIRMATION":
                return f"⚠️ En attente de confirmation : {data.get('summary', '')[:60]}"
            if "count" in data:
                return f"{data['count']} enregistrement(s) trouvé(s)"
            if "error" in data:
                return f"❌ Erreur : {data['error'][:80]}"
            if "message" in data:
                return str(data["message"])[:100]
            return str(data)[:100]
    except Exception:
        pass
    result = content.strip()
    return result[:120] + ("..." if len(result) > 120 else "")


# ── Construction de l'agent ────────────────────────────────────────────────────


def _build_agent(extra_context: str, llm):
    system = SYSTEM_PROMPT + extra_context
    return create_react_agent(
        model=llm,
        tools=ACTION_AGENT_TOOLS,
        prompt=system,
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
    on_step = state.get("on_step", None)
    provider = state.get("llm_provider", None)
    odoo_user_email = state.get("odoo_user_email")
    odoo_api_key = state.get("odoo_api_key")

    llm = get_llm(provider) if provider else _llm

    credentials_context = f"""

Credentials Odoo du user connecté :
- odoo_user_email = {json.dumps(odoo_user_email)}
- odoo_api_key    = {json.dumps(odoo_api_key)}

RÈGLE OBLIGATOIRE :
Pour chaque appel aux outils suivants :
  discover_model, get_model_fields, search_records,
  create_record, update_record, delete_record,
  execute_action, send_email

tu dois TOUJOURS inclure :
  - odoo_user_email = {json.dumps(odoo_user_email)}
  - odoo_api_key    = {json.dumps(odoo_api_key)}

Exemple :
search_records(
  model="sale.order",
  filters='[]',
  fields='["id", "name"]',
  limit=10,
  odoo_user_email={json.dumps(odoo_user_email)},
  odoo_api_key={json.dumps(odoo_api_key)}
)
"""

    result = _run(
        question=question,
        session_id=session_id,
        history=history,
        credentials_context=credentials_context,
        llm=llm,
        on_step=on_step,
    )

    return {
        "messages": result["messages"],
        "answer": result["answer"],
        "steps": result["steps"],
        "needs_confirmation": result["needs_confirmation"],
        "confirmation_summary": result["confirmation_summary"],
        "pending_action": result["pending_action"],
        "active_agent": "action_agent",
    }


# ── Wrapper de commodité (tests / API directe) ────────────────────────────────


def run_action_agent(
        question: str,
        session_id: str,
        odoo_user_email: str,
        odoo_api_key: str,
        history: list | None = None,
        on_step: StepCallback | None = None,
        provider: str | None = None,
) -> dict:
    """
    Exécute l'agent pour un tour utilisateur.

    Args:
        question:         Dernier message de l'utilisateur.
        session_id:       Identifiant de session.
        odoo_user_email:  Email du compte Odoo.
        odoo_api_key:     Clé API Odoo.
        history:          Messages LangChain des tours précédents.
        on_step:          Callback (step: int, msg: str) pour le streaming du raisonnement.
        provider:         Fournisseur LLM optionnel (remplace le défaut).

    Returns:
        answer, messages, steps, needs_confirmation, confirmation_summary, pending_action
    """
    llm = get_llm(provider) if provider else _llm
    credentials_context = f"""

Credentials Odoo du user connecté :
- odoo_user_email = {json.dumps(odoo_user_email)}
- odoo_api_key    = {json.dumps(odoo_api_key)}

RÈGLE OBLIGATOIRE : inclure odoo_user_email et odoo_api_key dans chaque appel outil.
"""
    return _run(
        question=question,
        session_id=session_id,
        history=history or [],
        credentials_context=credentials_context,
        llm=llm,
        on_step=on_step,
    )


# ── Logique interne ───────────────────────────────────────────────────────────


def _run(
        question: str,
        session_id: str,
        history: list,
        credentials_context: str,
        llm,
        on_step: StepCallback | None = None,
) -> dict:
    callback = on_step or _default_step_callback
    agent = _build_agent(credentials_context, llm=llm)

    messages = list(history)
    messages.append(("user", question))

    all_messages: list = []
    steps: list[str] = []
    step_number = 1

    for event in agent.stream(
            {"messages": messages},
            stream_mode="updates",
    ):
        for _node_name, node_output in event.items():
            for msg in node_output.get("messages", []):
                all_messages.append(msg)

                # ── LLM appelle un ou plusieurs outils ────────────────────────
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc["name"]
                        label = TOOL_LABELS.get(tool_name, tool_name)
                        args_line = _format_tool_args(tool_name, tc.get("args", {}))
                        step_msg = f"{label}  ({args_line})"
                        steps.append(step_msg)
                        callback(step_number, step_msg)
                        step_number += 1

                # ── Résultat d'outil ──────────────────────────────────────────
                elif isinstance(msg, ToolMessage):
                    result_line = _format_tool_result(msg.name, str(msg.content))
                    step_msg = f"→ Résultat : {result_line}"
                    steps.append(step_msg)
                    callback(step_number, step_msg)
                    step_number += 1

                # ── Réponse finale (aucun tool_call) ──────────────────────────
                elif isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                    step_msg = "Formulation de la réponse finale"
                    steps.append(step_msg)
                    callback(step_number, step_msg)
                    step_number += 1

    answer: str = all_messages[-1].content if all_messages else ""
    if not isinstance(answer, str):
        answer = json.dumps(answer, ensure_ascii=False, default=str)

    needs_confirmation, summary, pending_action = _extract_confirmation(all_messages)

    return {
        "answer": answer,
        "messages": all_messages,
        "steps": steps,
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
