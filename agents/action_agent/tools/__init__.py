from agents.action_agent.tools.actions import execute_action, send_email
from agents.action_agent.tools.confirmation import request_confirmation
from agents.action_agent.tools.crud import search_records, create_record, update_record, delete_record
from agents.action_agent.tools.discovery import discover_model, get_model_fields

ACTION_AGENT_TOOLS = [
    # ── Découverte (toujours en premier si le modèle est inconnu) ─────────
    discover_model,
    get_model_fields,
    # ── Lecture ───────────────────────────────────────────────────────────
    search_records,
    # ── Écriture (requièrent une confirmation) ────────────────────────────
    create_record,
    update_record,
    delete_record,
    # ── Workflow / communication (requièrent une confirmation) ────────────
    execute_action,
    send_email,
    # ── Verrou de confirmation ────────────────────────────────────────────
    request_confirmation,
]

__all__ = [
    "ACTION_AGENT_TOOLS",
    "discover_model",
    "get_model_fields",
    "search_records",
    "create_record",
    "update_record",
    "delete_record",
    "execute_action",
    "send_email",
    "request_confirmation",
]
