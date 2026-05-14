"""
agents/action_agent/tools/discovery.py

Outils de découverte : permettent au LLM de résoudre dynamiquement
les modèles Odoo et leurs champs, sans rien hard-coder.
"""
from langchain_core.tools import tool

from core.odoo_client import odoo_client
from shared.utils import get_logger, safe_json

logger = get_logger(__name__)


@tool
def discover_model(intent: str) -> str:
    """
    Trouve le nom technique du modèle Odoo correspondant à une intention
    en langage naturel (ex: "client", "commande de vente", "facture", "employé").

    Retourne une liste de modèles candidats avec leur nom affiché,
    pour que le LLM choisisse le plus pertinent avant toute opération.

    À utiliser EN PREMIER quand le modèle cible n'est pas déjà connu.
    """
    try:
        results = odoo_client.search_read(
            "ir.model",
            ["|",
             ["name", "ilike", intent],
             ["model", "ilike", intent.lower().replace(" ", ".")]],
            ["id", "model", "name"],
            limit=8,
        )
        if not results:
            return safe_json({
                "found": False,
                "message": f"Aucun modèle Odoo trouvé pour '{intent}'.",
            })
        return safe_json({
            "found": True,
            "candidates": [
                {"model": r["model"], "display_name": r["name"]}
                for r in results
            ],
        })
    except Exception as exc:
        logger.error("discover_model — %s", exc)
        return safe_json({"error": str(exc)})


@tool
def get_model_fields(model: str) -> str:
    """
    Retourne les champs disponibles (nom, type, libellé, obligatoire) pour
    un modèle technique Odoo donné (ex: "sale.order", "res.partner").

    À utiliser après discover_model pour connaître les champs sur lesquels
    filtrer ou écrire avant d'appeler search_records / create_record / update_record.
    """
    try:
        exists = odoo_client.search_read(
            "ir.model", [["model", "=", model]], ["id"], limit=1
        )
        if not exists:
            return safe_json({
                "error": f"Le modèle '{model}' n'existe pas dans cette instance Odoo.",
            })

        fields_meta = odoo_client.execute(
            model, "fields_get",
            [],
            {"attributes": ["string", "type", "required", "readonly"]},
        )

        useful_types = {
            "char", "text", "integer", "float", "boolean", "date",
            "datetime", "selection", "many2one", "one2many", "many2many",
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
