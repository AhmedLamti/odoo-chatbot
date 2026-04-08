"""
Action Executor Node — Phase 5
Lit action_sql_result pour récupérer les IDs exacts résolus
"""

import logging
from agents.state import AgentState
from tools.odoo_xmlrpc import OdooXMLRPC

logger = logging.getLogger(__name__)


def action_executor_node(state: AgentState) -> AgentState:
    action_type = state.get("action_type", "unknown")
    action_params = state.get("action_params", {})
    sql_result = state.get("action_sql_result", {})
    logger.info(f"Action Executor Node - action='{action_type}'")

    # Parser les résultats SQL
    resolved = _parse_sql_result(sql_result)

    try:
        odoo = OdooXMLRPC()
        result = _dispatch(odoo, action_type, action_params, resolved)
    except ConnectionError as e:
        logger.error(f"Connexion Odoo échouée: {e}")
        result = {"success": False, "error": f"Connexion Odoo impossible : {e}"}
    except Exception as e:
        logger.error(f"Erreur Action Executor: {e}")
        result = {"success": False, "error": str(e)}

    answer = (
        f"✅ {result['message']}"
        if result.get("success")
        else f"❌ Erreur : {result.get('error')}"
    )

    return {
        **state,
        "needs_confirmation": False,
        "answer": answer,
        "action_result": result,
    }


def _parse_sql_result(sql_result: dict) -> dict:
    resolved = {}
    if not sql_result or not sql_result.get("success"):
        return resolved
    for row in sql_result.get("results", []):
        rtype = row.get("type", "unknown")
        if rtype not in resolved:
            resolved[rtype] = row
    return resolved


def _dispatch(odoo: OdooXMLRPC, action_type: str, params: dict, resolved: dict) -> dict:

    if action_type == "create_sale_order":
        partner_id = int(resolved.get("partner", {}).get("id", 0))
        products = params.get("products", [])
        product_id = int(resolved.get("product", {}).get("id", 0))
        # Injecter product_id résolu dans chaque produit
        products_with_ids = [{**p, "product_id": product_id} for p in products]
        return odoo.create_sale_order_by_id(partner_id, products_with_ids)

    elif action_type == "confirm_sale_order":
        order_name = resolved.get("order", {}).get("name", params.get("order_name"))
        return odoo.confirm_sale_order(order_name)

    elif action_type == "create_invoice":
        partner_id = int(resolved.get("partner", {}).get("id", 0))
        return odoo.create_invoice_by_id(partner_id, params.get("lines", []))

    elif action_type == "validate_invoice":
        invoice_name = resolved.get("invoice", {}).get(
            "name", params.get("invoice_name")
        )
        return odoo.validate_invoice(invoice_name)

    elif action_type == "create_employee":
        dept_id = int(resolved.get("department", {}).get("id", 0)) or None
        return odoo.create_employee(
            name=params["name"],
            job_title=params.get("job_title") or "",
            department_id=dept_id,
            department_name=params.get("department_name") or "",
        )

    elif action_type == "update_product_price":
        product_id = int(resolved.get("product_template", {}).get("id", 0))
        name = resolved.get("product_template", {}).get(
            "name", params.get("product_name", "")
        )
        return odoo.update_product_price_by_id(
            product_id, float(params["new_price"]), name
        )

    elif action_type == "update_product_stock":
        product_id = int(resolved.get("product_template", {}).get("id", 0))
        name = resolved.get("product_template", {}).get(
            "name", params.get("product_name", "")
        )
        return odoo.update_product_stock_by_id(
            product_id, float(params["quantity"]), name
        )

    elif action_type == "send_email":
        partner_name = resolved.get("partner", {}).get(
            "name", params.get("partner_name")
        )
        return odoo.send_email(
            partner_name=partner_name,
            subject=params.get("subject", "Message"),
            body=params.get("body", ""),
        )

    return {"success": False, "error": f"Action '{action_type}' non implémentée"}
