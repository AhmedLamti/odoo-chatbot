"""
SQL Generator Node — avec gestion d'erreurs
"""

import logging
import re
from agents.state import AgentState
from tools.schema_selector import SchemaSelector
from tools.cerebras_client import call_cerebras
from db.conversation_store import ConversationStore

logger = logging.getLogger(__name__)

SQL_SYSTEM = """You are an Odoo 16 PostgreSQL expert.

RULES:
1. ALWAYS use table aliases (so, sol, pt, pp, rp, am, he, po, sq, ru, ct)
2. ALWAYS prefix ALL columns with alias
3. product_template.name is JSONB → COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text)
4. Vendor/Salesperson name → sale_order.user_id → JOIN res_users ru → JOIN res_partner rp ON ru.partner_id = rp.id → rp.name
5. sale_order_line.name = product description (NEVER the salesperson name)
6. Sales: sale_order WHERE state IN ('sale', 'done') — NEVER account_move for sales revenue
7. Invoices: account_move WHERE move_type='out_invoice' AND state='posted'
8. Customers: res_partner WHERE customer_rank > 0 AND active = TRUE
9. COUNT(DISTINCT so.id) to avoid duplicates from JOINs
10. COUNT only when question has 'combien'/'how many' — otherwise SELECT the actual columns
11. 'meilleur/meilleures/top/liste' → SELECT columns ORDER BY amount/qty DESC LIMIT 10
12. NEVER JOIN sale_order_line unless question specifically needs product line details
13. ROUND(value::numeric, 2) for monetary amounts
14. Return ONLY the SQL query ending with semicolon — NO explanation
"""


def sql_generator_node(state: AgentState) -> AgentState:
    question = state["question"]
    session_id = state.get("session_id")
    logger.info(f"SQL Generator Node - Question: '{question}'")

    try:
        schema_selector = SchemaSelector()
        schema_text = schema_selector.get_relevant_schema(question)

        history_text = ""
        if session_id:
            store = ConversationStore()
            history_text = store.format_history(session_id)

        example = _get_example(question)

        raw_sql = call_cerebras(
            prompt=f"{schema_text}\n\n{example}\n\n{history_text}\nQuestion: {question}",
            system=SQL_SYSTEM,
            max_tokens=300,
            temperature=0,
        )
        sql_query = _extract_sql(raw_sql)
        logger.info(f"SQL généré: {sql_query}")
        return {**state, "sql_query": sql_query, "error": None}

    except Exception as e:
        logger.error(f"Erreur SQL Generator: {e}")
        return {
            **state,
            "sql_query": "",
            "error": str(e),
            "error_origin": "sql_generator",
        }


def _extract_sql(raw: str) -> str:
    raw = re.sub(r"```sql\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    match = re.search(r"(SELECT\s+.*?;)", raw, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    if ";" in raw:
        return raw[: raw.index(";") + 1].strip()
    return raw.strip()


def _get_example(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ["vendeur", "commercial", "salesperson"]):
        return """EXAMPLE:
Q: Vendeurs des meilleures commandes
A: SELECT rp.name AS vendeur, COUNT(DISTINCT so.id) AS nb_commandes,
          ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires
   FROM sale_order so
   JOIN res_users ru ON so.user_id = ru.id
   JOIN res_partner rp ON ru.partner_id = rp.id
   WHERE so.state IN ('sale', 'done')
   GROUP BY rp.name ORDER BY chiffre_affaires DESC;"""
    if any(w in q for w in ["meilleure", "meilleures", "top commande", "best order"]):
        return """EXAMPLE:
Q: Meilleures commandes clients
A: SELECT so.name AS commande, rp.name AS client,
          ROUND(so.amount_untaxed::numeric, 2) AS montant_ht, so.date_order::date AS date
   FROM sale_order so JOIN res_partner rp ON so.partner_id = rp.id
   WHERE so.state IN ('sale', 'done') ORDER BY so.amount_untaxed DESC LIMIT 10;"""
    if any(
        w in q for w in ["chiffre", "affaires", "ca ", "revenue", "ventes par mois"]
    ):
        return """EXAMPLE:
Q: Chiffre d'affaires par mois
A: SELECT TO_CHAR(so.date_order, 'YYYY-MM') AS mois,
          ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires
   FROM sale_order so WHERE so.state IN ('sale', 'done')
   GROUP BY TO_CHAR(so.date_order, 'YYYY-MM') ORDER BY mois LIMIT 12;"""
    if any(w in q for w in ["facture", "invoice", "impayé"]):
        return """EXAMPLE:
Q: Factures impayées
A: SELECT am.name, rp.name AS client, ROUND(am.amount_residual::numeric, 2) AS restant,
          am.invoice_date_due AS echeance
   FROM account_move am JOIN res_partner rp ON am.partner_id = rp.id
   WHERE am.move_type = 'out_invoice' AND am.state = 'posted'
     AND am.payment_state IN ('not_paid', 'partial')
   ORDER BY am.invoice_date_due ASC LIMIT 20;"""
    if any(w in q for w in ["produit", "product", "vendu", "top produit"]):
        return """EXAMPLE:
Q: Top produits vendus
A: SELECT COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS produit,
          SUM(sol.product_uom_qty) AS quantite, ROUND(SUM(sol.price_subtotal)::numeric, 2) AS total
   FROM sale_order_line sol JOIN sale_order so ON sol.order_id = so.id
   JOIN product_product pp ON sol.product_id = pp.id
   JOIN product_template pt ON pp.product_tmpl_id = pt.id
   WHERE so.state IN ('sale', 'done')
   GROUP BY pt.name ORDER BY quantite DESC LIMIT 10;"""
    if any(w in q for w in ["client", "customer", "combien de client"]):
        return """EXAMPLE:
Q: Liste des clients
A: SELECT rp.name AS client, COUNT(DISTINCT so.id) AS nb_commandes,
          ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires
   FROM res_partner rp JOIN sale_order so ON rp.id = so.partner_id
   WHERE rp.customer_rank > 0 AND rp.active = TRUE AND so.state IN ('sale', 'done')
   GROUP BY rp.name ORDER BY chiffre_affaires DESC;"""
    if any(w in q for w in ["employé", "employee", "employe", "département"]):
        return """EXAMPLE:
Q: Employés par département
A: SELECT hd.name AS departement, COUNT(he.id) AS nombre
   FROM hr_employee he JOIN hr_department hd ON he.department_id = hd.id
   WHERE he.active = TRUE GROUP BY hd.name ORDER BY nombre DESC;"""
    if any(w in q for w in ["stock", "inventaire", "disponible"]):
        return """EXAMPLE:
Q: Stock disponible
A: SELECT COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS produit,
          SUM(sq.quantity) AS stock
   FROM stock_quant sq JOIN product_product pp ON sq.product_id = pp.id
   JOIN product_template pt ON pp.product_tmpl_id = pt.id
   WHERE sq.location_id IN (SELECT id FROM stock_location WHERE usage = 'internal')
   GROUP BY pt.name HAVING SUM(sq.quantity) > 0 ORDER BY stock DESC LIMIT 20;"""
    if any(w in q for w in ["achat", "purchase", "fournisseur"]):
        return """EXAMPLE:
Q: Top fournisseurs
A: SELECT rp.name AS fournisseur, ROUND(SUM(po.amount_untaxed)::numeric, 2) AS total_achats
   FROM purchase_order po JOIN res_partner rp ON po.partner_id = rp.id
   WHERE po.state IN ('purchase', 'done')
   GROUP BY rp.name ORDER BY total_achats DESC LIMIT 10;"""
    return """EXAMPLE:
Q: Meilleures commandes clients
A: SELECT so.name AS commande, rp.name AS client,
          ROUND(so.amount_untaxed::numeric, 2) AS montant_ht
   FROM sale_order so JOIN res_partner rp ON so.partner_id = rp.id
   WHERE so.state IN ('sale', 'done') ORDER BY so.amount_untaxed DESC LIMIT 10;"""
