"""
Action Confirm Node — Phase 5
Lit action_sql_result pour construire le résumé de confirmation
"""

import logging
from agents.state import AgentState

logger = logging.getLogger(__name__)


def action_confirm_node(state: AgentState) -> AgentState:
    action_type = state.get("action_type", "unknown")
    action_params = state.get("action_params", {})
    sql_result = state.get("action_sql_result", {})
    logger.info(f"Action Confirm Node - action='{action_type}'")

    if action_type == "unknown":
        reason = action_params.get("reason", "Action non reconnue")
        return {
            **state,
            "needs_confirmation": False,
            "answer": (
                f"❌ Je n'ai pas pu comprendre l'action à effectuer.\n\n"
                f"Raison : {reason}\n\n"
                f"Exemples :\n"
                f"- « Crée une commande pour Azure Interior avec 2 Office Chair »\n"
                f"- « Valide la facture INV/2024/00001 »\n"
                f"- « Ajoute un employé Jean Dupont au département Ventes »\n"
                f"- « Mets le stock du produit Chaise à 50 unités »\n"
                f"- « Envoie un email à Azure Interior avec le sujet Relance »"
            ),
        }

    # Parser les résultats SQL en dict indexé par type
    resolved = _parse_sql_result(sql_result)

    # Vérifier les erreurs de résolution
    error = _check_resolution_errors(action_type, action_params, resolved)
    if error:
        return {
            **state,
            "needs_confirmation": False,
            "answer": f"❌ {error}",
        }

    summary = _build_summary(action_type, action_params, resolved)
    answer = (
        f"⚠️ **Confirmation requise**\n\n"
        f"{summary}\n\n"
        f"Tapez **CONFIRMER** pour valider ou **ANNULER** pour abandonner."
    )

    return {
        **state,
        "needs_confirmation": True,
        "confirmation_summary": summary,
        "answer": answer,
    }


def _parse_sql_result(sql_result: dict) -> dict:
    """Transforme les rows SQL en dict indexé par type"""
    resolved = {}
    if not sql_result or not sql_result.get("success"):
        return resolved
    for row in sql_result.get("results", []):
        rtype = row.get("type", "unknown")
        if rtype not in resolved:
            resolved[rtype] = row
    return resolved


def _check_resolution_errors(action_type: str, params: dict, resolved: dict) -> str:
    """Retourne un message d'erreur si une résolution a échoué"""
    if action_type == "create_sale_order":
        if "partner" not in resolved:
            return f"Client '{params.get('partner_name')}' introuvable dans Odoo"
        for p in params.get("products", []):
            if "product" not in resolved:
                return f"Produit '{p.get('name')}' introuvable dans Odoo"

    elif action_type == "confirm_sale_order":
        if "order" not in resolved:
            return f"Commande '{params.get('order_name')}' introuvable"

    elif action_type in ("create_invoice", "create_sale_order"):
        if "partner" not in resolved:
            return f"Client '{params.get('partner_name')}' introuvable"

    elif action_type == "validate_invoice":
        if "invoice" not in resolved:
            return f"Facture '{params.get('invoice_name')}' introuvable"

    elif action_type in ("update_product_price", "update_product_stock"):
        if "product_template" not in resolved:
            return f"Produit '{params.get('product_name')}' introuvable"

    elif action_type == "send_email":
        if "partner" not in resolved:
            return f"Contact '{params.get('partner_name')}' introuvable"
        if not resolved.get("partner", {}).get("email"):
            return (
                f"'{resolved['partner'].get('name')}' n'a pas d'adresse email dans Odoo"
            )

    return ""


def _build_summary(action_type: str, params: dict, resolved: dict) -> str:
    if action_type == "create_sale_order":
        client = resolved.get("partner", {}).get(
            "name", params.get("partner_name", "?")
        )
        lines = []
        for p in params.get("products", []):
            name = resolved.get("product", {}).get("name", p.get("name", "?"))
            qty = p.get("qty", 1)
            price = p.get("price", 0)
            lines.append(f"  • {name} × {qty} = **{qty * price:.2f} €**")
        products_str = "\n".join(lines) if lines else "  • (aucun produit)"
        return (
            f"Vous êtes sur le point de **créer une commande de vente** :\n"
            f"- Client : **{client}**\n"
            f"- Produits :\n{products_str}"
        )

    elif action_type == "confirm_sale_order":
        name = resolved.get("order", {}).get("name", params.get("order_name", "?"))
        return f"Vous êtes sur le point de **confirmer la commande** : **{name}**"

    elif action_type == "create_invoice":
        client = resolved.get("partner", {}).get(
            "name", params.get("partner_name", "?")
        )
        lines = params.get("lines", [])
        total = sum(l.get("qty", 1) * l.get("price", 0) for l in lines)
        return (
            f"Vous êtes sur le point de **créer une facture** :\n"
            f"- Client : **{client}**\n"
            f"- Montant estimé : **{total:.2f} €**"
        )

    elif action_type == "validate_invoice":
        row = resolved.get("invoice", {})
        name = row.get("name", params.get("invoice_name", "?"))
        client = row.get("partner_name", "?")
        amount = row.get("amount_total", "?")
        return (
            f"Vous êtes sur le point de **valider la facture** :\n"
            f"- Facture : **{name}**\n"
            f"- Client : **{client}**\n"
            f"- Montant : **{amount} €**"
        )

    elif action_type == "create_employee":
        name = params.get("name", "?")
        dept = resolved.get("department", {}).get(
            "name", params.get("department_name", "")
        )
        job = params.get("job_title", "")
        lines = [f"- Nom : **{name}**"]
        if job:
            lines.append(f"- Poste : **{job}**")
        if dept:
            lines.append(f"- Département : **{dept}**")
        return "Vous êtes sur le point d'**ajouter un employé** :\n" + "\n".join(lines)

    elif action_type == "update_product_price":
        name = resolved.get("product_template", {}).get(
            "name", params.get("product_name", "?")
        )
        new_price = params.get("new_price", "?")
        return (
            f"Vous êtes sur le point de **modifier le prix** :\n"
            f"- Produit : **{name}**\n"
            f"- Nouveau prix : **{new_price} €**"
        )

    elif action_type == "update_product_stock":
        name = resolved.get("product_template", {}).get(
            "name", params.get("product_name", "?")
        )
        qty = params.get("quantity", "?")
        return (
            f"Vous êtes sur le point de **modifier le stock** :\n"
            f"- Produit : **{name}**\n"
            f"- Nouvelle quantité : **{qty} unités**"
        )

    elif action_type == "send_email":
        row = resolved.get("partner", {})
        partner = row.get("name", params.get("partner_name", "?"))
        email = row.get("email", "?")
        subject = params.get("subject", "?")
        return (
            f"Vous êtes sur le point d'**envoyer un email** :\n"
            f"- Destinataire : **{partner}** ({email})\n"
            f"- Sujet : **{subject}**"
        )

    return f"Action : **{action_type}**"
