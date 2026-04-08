"""
Action Parser Node — Phase 5
Extrait l'action + paramètres en JSON ET génère le SQL de résolution des IDs
"""

import json
import logging
import re
from agents.state import AgentState
from tools.cerebras_client import call_cerebras

logger = logging.getLogger(__name__)

ACTION_PARSER_SYSTEM = """You extract a structured Odoo action from a natural language request.
Reply ONLY with a valid JSON object — no explanation, no markdown, no extra text.

Supported actions:
1. create_sale_order:   {"action": "create_sale_order", "partner_name": "...", "products": [{"name": "...", "qty": 1, "price": 0.0}]}
2. confirm_sale_order:  {"action": "confirm_sale_order", "order_name": "S00001"}
3. create_invoice:      {"action": "create_invoice", "partner_name": "...", "lines": [{"name": "...", "qty": 1, "price": 0.0}]}
4. validate_invoice:    {"action": "validate_invoice", "invoice_name": "INV/2024/00001"}
5. create_employee:     {"action": "create_employee", "name": "...", "job_title": "...", "department_name": "..."}
6. update_product_price:{"action": "update_product_price", "product_name": "...", "new_price": 0.0}
7. update_product_stock:{"action": "update_product_stock", "product_name": "...", "quantity": 0.0}
8. send_email:          {"action": "send_email", "partner_name": "...", "subject": "...", "body": "..."}

RULES:
- Extract ALL parameters mentioned
- Numbers must be numeric: "qty": 2 not "qty": "2"
- If unclear: {"action": "unknown", "reason": "..."}
"""


def action_parser_node(state: AgentState) -> AgentState:
    question = state["question"]
    logger.info(f"Action Parser Node - Question: '{question}'")

    # ── 1. Extraire l'action et ses paramètres ──
    try:
        raw = call_cerebras(
            prompt=f"Request: {question}\nJSON:",
            system=ACTION_PARSER_SYSTEM,
            max_tokens=300,
            temperature=0,
        ).strip()

        raw = re.sub(r"^```json?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()

        action_params = json.loads(raw)
        logger.info(f"Action parsée: {action_params}")

    except Exception as e:
        logger.error(f"Erreur parsing action: {e}")
        action_params = {"action": "unknown", "reason": str(e)}

    action_type = action_params.get("action", "unknown")

    # ── 2. Générer le SQL de résolution des IDs ──
    action_sql_query = _build_resolution_sql(action_type, action_params)
    logger.info(f"SQL résolution: {action_sql_query}")

    return {
        **state,
        "action_type": action_type,
        "action_params": action_params,
        "action_sql_query": action_sql_query,
    }


def _build_resolution_sql(action_type: str, params: dict) -> str:
    """
    Génère un SQL qui retourne tous les IDs et noms exacts nécessaires
    pour l'action — en une seule requête UNION pour sql_executor_node
    """

    if action_type == "create_sale_order":
        partner = params.get("partner_name", "")
        products = params.get("products", [])
        queries = [
            f"(SELECT 'partner' AS type, id::text, name FROM res_partner "
            f"WHERE name ILIKE '%{partner}%' AND customer_rank > 0 AND active = TRUE LIMIT 1)"
        ]
        for p in products:
            name = p.get("name", "")
            queries.append(
                f"(SELECT 'product' AS type, pp.id::text, "
                f"COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS name "
                f"FROM product_product pp "
                f"JOIN product_template pt ON pp.product_tmpl_id = pt.id "
                f"WHERE (pt.name->>'fr_FR' ILIKE '%{name}%' OR pt.name->>'en_US' ILIKE '%{name}%') "
                f"AND pt.active = TRUE LIMIT 1)"
            )
        return "\nUNION ALL\n".join(queries) + ";"

    elif action_type == "confirm_sale_order":
        order = params.get("order_name", "")
        return (
            f"SELECT 'order' AS type, id::text, name FROM sale_order "
            f"WHERE name ILIKE '%{order}%' ORDER BY id DESC LIMIT 1;"
        )

    elif action_type == "create_invoice":
        partner = params.get("partner_name", "")
        return (
            f"SELECT 'partner' AS type, id::text, name FROM res_partner "
            f"WHERE name ILIKE '%{partner}%' AND customer_rank > 0 AND active = TRUE LIMIT 1;"
        )

    elif action_type == "validate_invoice":
        invoice = params.get("invoice_name", "")
        return (
            f"SELECT 'invoice' AS type, am.id::text, am.name, "
            f"am.state, am.amount_total::text, rp.name AS partner_name "
            f"FROM account_move am "
            f"JOIN res_partner rp ON am.partner_id = rp.id "
            f"WHERE am.name ILIKE '%{invoice}%' AND am.move_type = 'out_invoice' LIMIT 1;"
        )

    elif action_type == "create_employee":
        dept = params.get("department_name", "")
        if dept:
            return (
                f"SELECT 'department' AS type, id::text, name FROM hr_department "
                f"WHERE name ILIKE '%{dept}%' LIMIT 1;"
            )
        return "SELECT 'no_resolution' AS type, '0' AS id, '' AS name;"

    elif action_type in ("update_product_price", "update_product_stock"):
        product = params.get("product_name", "")
        return (
            f"SELECT 'product_template' AS type, pt.id::text, "
            f"COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS name "
            f"FROM product_template pt "
            f"WHERE (pt.name->>'fr_FR' ILIKE '%{product}%' OR pt.name->>'en_US' ILIKE '%{product}%') "
            f"AND pt.active = TRUE LIMIT 1;"
        )

    elif action_type == "send_email":
        partner = params.get("partner_name", "")
        return (
            f"SELECT 'partner' AS type, id::text, name, email "
            f"FROM res_partner "
            f"WHERE name ILIKE '%{partner}%' AND active = TRUE LIMIT 1;"
        )

    return "SELECT 'no_resolution' AS type, '0' AS id, '' AS name;"
