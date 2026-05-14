import json

from langchain_core.tools import tool

from core.odoo_client import odoo_client
from shared.utils import get_logger, safe_json

logger = get_logger(__name__)


def _model_exists(model: str) -> bool:
    """Vérifie qu'un modèle existe pour retourner une erreur claire avant tout appel XML-RPC."""
    return bool(
        odoo_client.search_read("ir.model", [["model", "=", model]], ["id"], limit=1)
    )


@tool
def search_records(
        model: str,
        filters: str,
        fields: str = '["id", "name"]',
        limit: int = 10,
) -> str:
    """
    Recherche des enregistrements dans n'importe quel modèle Odoo.

    Args:
        model:   Nom technique du modèle (ex: "res.partner", "sale.order").
        filters: Tableau JSON de tuples de domaine Odoo
                 (ex: '[["name", "ilike", "Ahmed"], ["active", "=", true]]').
                 Passer '[]' pour aucun filtre.
        fields:  Tableau JSON de noms de champs à retourner
                 (ex: '["id","name","email"]'). Par défaut ["id", "name"].
        limit:   Nombre maximum d'enregistrements (défaut 10, max 50).
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable dans Odoo."})

        records = odoo_client.search_read(
            model,
            json.loads(filters),
            json.loads(fields),
            limit=min(limit, 50),
        )
        return safe_json({"model": model, "count": len(records), "records": records})
    except json.JSONDecodeError as exc:
        return safe_json({"error": f"JSON invalide dans filters ou fields : {exc}"})
    except Exception as exc:
        logger.error("search_records(%s) — %s", model, exc)
        return safe_json({"error": str(exc)})


@tool
def create_record(model: str, values: str) -> str:
    """
    Crée un nouvel enregistrement dans n'importe quel modèle Odoo.

    Args:
        model:  Nom technique du modèle (ex: "hr.employee").
        values: Objet JSON des valeurs de champs
                (ex: '{"name": "Alice", "job_title": "Ingénieure", "department_id": 3}').
                Pour les lignes One2many/Many2many, utiliser le format Odoo (0, 0, {...})
                encodé en tableau JSON : [[0, 0, {"field": "value"}]].

    ⚠️ Requiert une confirmation préalable via request_confirmation.
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable dans Odoo."})

        record_id = odoo_client.execute(model, "create", json.loads(values))

        readable = odoo_client.search_read(
            model, [["id", "=", record_id]], ["name", "display_name"], limit=1
        )
        label = (
            readable[0].get("name") or readable[0].get("display_name")
            if readable else str(record_id)
        )
        return safe_json({
            "success": True,
            "model": model,
            "id": record_id,
            "name": label,
            "message": f"✅ Enregistrement '{label}' créé dans {model} (id={record_id})",
        })
    except json.JSONDecodeError as exc:
        return safe_json({"error": f"JSON invalide dans values : {exc}"})
    except Exception as exc:
        logger.error("create_record(%s) — %s", model, exc)
        return safe_json({"success": False, "error": str(exc)})


@tool
def update_record(model: str, record_id: int, values: str) -> str:
    """
    Modifie un enregistrement existant dans n'importe quel modèle Odoo.

    Args:
        model:     Nom technique du modèle (ex: "product.template").
        record_id: ID entier de l'enregistrement à modifier.
        values:    Objet JSON des champs à mettre à jour
                   (ex: '{"list_price": 299.99}' ou '{"active": false}').

    ⚠️ Requiert une confirmation préalable via request_confirmation.
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable dans Odoo."})

        vals = json.loads(values)
        odoo_client.execute(model, "write", [record_id], vals)

        return safe_json({
            "success": True,
            "model": model,
            "id": record_id,
            "updated_fields": list(vals.keys()),
            "message": f"✅ Enregistrement {record_id} dans {model} mis à jour ({', '.join(vals.keys())})",
        })
    except json.JSONDecodeError as exc:
        return safe_json({"error": f"JSON invalide dans values : {exc}"})
    except Exception as exc:
        logger.error("update_record(%s, id=%s) — %s", model, record_id, exc)
        return safe_json({"success": False, "error": str(exc)})


@tool
def delete_record(model: str, record_id: int) -> str:
    """
    Supprime définitivement un enregistrement d'un modèle Odoo.

    Args:
        model:     Nom technique du modèle.
        record_id: ID entier de l'enregistrement à supprimer.

    ⚠️ Irréversible — toujours demander une confirmation explicite d'abord.
    """
    try:
        if not _model_exists(model):
            return safe_json({"error": f"Modèle '{model}' introuvable dans Odoo."})

        odoo_client.execute(model, "unlink", [record_id])
        return safe_json({
            "success": True,
            "model": model,
            "id": record_id,
            "message": f"✅ Enregistrement {record_id} supprimé de {model}",
        })
    except Exception as exc:
        logger.error("delete_record(%s, id=%s) — %s", model, record_id, exc)
        return safe_json({"success": False, "error": str(exc)})
