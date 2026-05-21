"""
agents/action_agent/tools.py

Fichier unique regroupant tous les outils de l'Action Agent pour Odoo :
Découverte, Recherche, CRUD, Actions Workflow et Confirmation.
"""

import json
from typing import Any, Dict, List, Optional, Union

from langchain_core.tools import tool
from core.odoo_client import odoo_client
from shared.utils import get_logger, safe_json

logger = get_logger(__name__)

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------


def _model_exists(model: str) -> bool:
    """Vérifie qu'un modèle existe pour retourner une erreur claire avant tout appel XML-RPC."""
    return bool(
        odoo_client.search_read("ir.model", [["model", "=", model]], ["id"], limit=1)
    )


# ---------------------------------------------------------
# DÉCOUVERTE (Modèles et Champs)
# ---------------------------------------------------------


@tool
def discover_model(intent: str) -> str:
    """
    Trouve le nom technique du modèle Odoo correspondant à une intention (ex: "client", "facture").
    À utiliser EN PREMIER quand le modèle cible n'est pas déjà connu.
    """
    try:
        results = odoo_client.search_read(
            "ir.model",
            [
                "|",
                ["name", "ilike", intent],
                ["model", "ilike", intent.lower().replace(" ", ".")],
            ],
            ["id", "model", "name"],
            limit=8,
        )
        if not results:
            return safe_json(
                {
                    "found": False,
                    "message": f"Aucun modèle Odoo trouvé pour '{intent}'.",
                }
            )
        return safe_json(
            {
                "found": True,
                "candidates": [
                    {"model": r["model"], "display_name": r["name"]} for r in results
                ],
            }
        )
    except Exception as exc:
        logger.error("discover_model — %s", exc)
        return safe_json({"error": str(exc)})


@tool
def get_model_fields(model: str) -> str:
    """
    Retourne les champs disponibles (nom, type, libellé) pour un modèle technique Odoo donné.
    À utiliser après discover_model pour connaître les filtres possibles.
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Le modèle '{model}' n'existe pas."})

        fields_meta = odoo_client.execute(
            model,
            "fields_get",
            [],
            {"attributes": ["string", "type", "required", "readonly"]},
        )
        useful_types = {
            "char",
            "text",
            "integer",
            "float",
            "boolean",
            "date",
            "datetime",
            "selection",
            "many2one",
            "one2many",
            "many2many",
        }
        cleaned = {
            fname: {
                "label": meta["string"],
                "type": meta["type"],
                "required": meta.get("required", False),
                "readonly": meta.get("readonly", False),
            }
            for fname, meta in fields_meta.items()
            if meta["type"] in useful_types and not fname.startswith("_")
        }
        return safe_json({"model": model, "fields": cleaned})
    except Exception as exc:
        logger.error("get_model_fields(%s) — %s", model, exc)
        return safe_json({"error": str(exc)})


# ---------------------------------------------------------
# LECTURE / RECHERCHE (CRUD - Read)
# ---------------------------------------------------------


@tool
def search_records(
    model: str, filters: str, fields: str = '["id", "name"]', limit: int = 10
) -> str:
    """
    Recherche des enregistrements dans n'importe quel modèle Odoo.
    filters: JSON string de tuples de domaine (ex: '[["name", "ilike", "Ahmed"]]').
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable."})
        records = odoo_client.search_read(
            model, json.loads(filters), json.loads(fields), limit=min(limit, 50)
        )
        return safe_json({"model": model, "count": len(records), "records": records})
    except Exception as exc:
        logger.error("search_records(%s) — %s", model, exc)
        return safe_json({"error": str(exc)})


# ---------------------------------------------------------
# ÉCRITURE (CRUD - Create, Update, Delete)
# ---------------------------------------------------------


@tool
def create_record(model: str, values: str) -> str:
    """
    Crée un nouvel enregistrement dans Odoo.
    ⚠️ Requiert une confirmation préalable via request_confirmation.
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable."})
        record_id = odoo_client.execute(model, "create", json.loads(values))
        return safe_json(
            {
                "success": True,
                "id": record_id,
                "message": f"✅ Créé dans {model} (id={record_id})",
            }
        )
    except Exception as exc:
        logger.error("create_record(%s) — %s", model, exc)
        return safe_json({"success": False, "error": str(exc)})


@tool
def update_record(model: str, record_id: int, values: str) -> str:
    """
    Modifie un enregistrement existant.
    ⚠️ Requiert une confirmation préalable via request_confirmation.
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable."})
        vals = json.loads(values)
        odoo_client.execute(model, "write", [record_id], vals)
        return safe_json(
            {
                "success": True,
                "message": f"✅ Enregistrement {record_id} mis à jour dans {model}",
            }
        )
    except Exception as exc:
        logger.error("update_record(%s, id=%s) — %s", model, record_id, exc)
        return safe_json({"success": False, "error": str(exc)})


@tool
def delete_record(model: str, record_id: int) -> str:
    """
    Supprime définitivement un enregistrement. ⚠️ Irréversible. Requiert confirmation.
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable."})
        odoo_client.execute(model, "unlink", [record_id])
        return safe_json(
            {
                "success": True,
                "message": f"✅ Enregistrement {record_id} supprimé de {model}",
            }
        )
    except Exception as exc:
        logger.error("delete_record(%s, id=%s) — %s", model, record_id, exc)
        return safe_json({"success": False, "error": str(exc)})


# ---------------------------------------------------------
# ACTIONS WORKFLOW & COMMUNICATION
# ---------------------------------------------------------


@tool
def execute_action(model: str, method: str, record_id: int) -> str:
    """
    Exécute une méthode workflow (ex: "action_confirm" sur une commande).
    ⚠️ Requiert une confirmation préalable.
    """
    try:
        odoo_client.execute(model, method, [record_id])
        return safe_json(
            {
                "success": True,
                "message": f"✅ {method} exécuté sur {model} (id={record_id})",
            }
        )
    except Exception as exc:
        logger.error("execute_action — %s", exc)
        return safe_json({"success": False, "error": str(exc)})


@tool
def send_email(partner_id: int, subject: str, body: str) -> str:
    """
    Envoie un email à un partenaire Odoo. Requiert confirmation.
    """
    try:
        partners = odoo_client.search_read(
            "res.partner", [["id", "=", partner_id]], ["name", "email"], limit=1
        )
        if not partners or not partners[0].get("email"):
            return safe_json(
                {"success": False, "error": "Partenaire ou email introuvable."}
            )
        mail_id = odoo_client.execute(
            "mail.mail",
            "create",
            {
                "subject": subject,
                "body_html": f"<p>{body}</p>",
                "email_to": partners[0]["email"],
            },
        )
        odoo_client.execute("mail.mail", "send", [mail_id])
        return safe_json(
            {"success": True, "message": f"✅ Email envoyé à {partners[0]['name']}"}
        )
    except Exception as exc:
        logger.error("send_email — %s", exc)
        return safe_json({"success": False, "error": str(exc)})


# ---------------------------------------------------------
# CONFIRMATION
# ---------------------------------------------------------


@tool
def request_confirmation(
    action_type: str, action_summary: str, tool_name: str, tool_args: str
) -> str:
    """
    Demande à l'utilisateur de confirmer une opération (Create, Update, Delete, Action) avant exécution.
    """
    try:
        parsed_args = json.loads(tool_args)
    except Exception:
        parsed_args = tool_args

    payload = {
        "status": "WAITING_CONFIRMATION",
        "action_type": action_type,
        "summary": action_summary,
        "pending_action": {"tool_name": tool_name, "tool_args": parsed_args},
        "message": f"⚠️ Confirmation requise\n\n{action_summary}\n\nCliquez sur **Confirmer**.",
        "instruction": "Retourne le champ 'message' à l'utilisateur. Stop.",
    }
    return json.dumps(payload, ensure_ascii=False)


# Liste exportable pour l'agent
ACTION_AGENT_TOOLS = [
    discover_model,
    get_model_fields,
    search_records,
    create_record,
    update_record,
    delete_record,
    execute_action,
    send_email,
    request_confirmation,
]
