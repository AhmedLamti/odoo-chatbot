from langchain_core.tools import tool

from core.odoo_client import odoo_client
from shared.utils import get_logger, safe_json

logger = get_logger(__name__)


@tool
def execute_action(model: str, method: str, record_id: int) -> str:
    """
    Exécute une méthode workflow (bouton d'action) sur un enregistrement Odoo.

    Exemples courants :
      model="sale.order"     method="action_confirm"  → confirmer une commande
      model="account.move"   method="action_post"     → valider une facture
      model="purchase.order" method="button_confirm"  → confirmer un achat
      model="stock.picking"  method="button_validate" → valider une livraison

    ⚠️ Requiert une confirmation préalable via request_confirmation.
    """
    try:
        odoo_client.execute(model, method, [record_id])
        return safe_json({
            "success": True,
            "model": model,
            "method": method,
            "id": record_id,
            "message": f"✅ {method} exécuté sur {model} (id={record_id})",
        })
    except Exception as exc:
        logger.error("execute_action(%s.%s, id=%s) — %s", model, method, record_id, exc)
        return safe_json({"success": False, "error": str(exc)})


@tool
def send_email(partner_id: int, subject: str, body: str) -> str:
    """
    Envoie un email à un partenaire Odoo via mail.mail.

    Args:
        partner_id: ID entier du partenaire res.partner
                    (utiliser search_records pour le trouver).
        subject:    Objet de l'email.
        body:       Corps en texte brut (sera encapsulé dans une balise <p>).

    Vérifie que le partenaire possède une adresse email avant l'envoi.
    ⚠️ Requiert une confirmation préalable via request_confirmation.
    """
    try:
        partners = odoo_client.search_read(
            "res.partner", [["id", "=", partner_id]], ["name", "email"], limit=1
        )
        if not partners:
            return safe_json({"success": False, "error": f"Partenaire {partner_id} introuvable."})

        partner = partners[0]
        if not partner.get("email"):
            return safe_json({
                "success": False,
                "error": f"Le partenaire '{partner['name']}' n'a pas d'adresse email.",
            })

        mail_id = odoo_client.execute(
            "mail.mail", "create",
            {"subject": subject, "body_html": f"<p>{body}</p>", "email_to": partner["email"]},
        )
        odoo_client.execute("mail.mail", "send", [mail_id])

        return safe_json({
            "success": True,
            "message": f"✅ Email envoyé à '{partner['name']}' <{partner['email']}>",
        })
    except Exception as exc:
        logger.error("send_email(partner_id=%s) — %s", partner_id, exc)
        return safe_json({"success": False, "error": str(exc)})
