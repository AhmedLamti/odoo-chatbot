import logging
import re
import requests
from agents.state import AgentState
from tools.schema_selector import SchemaSelector
from tools.sql_executor import SQLExecutor
from config.settings import settings
from db.conversation_store import ConversationStore

logger = logging.getLogger(__name__)

SQL_SYSTEM_PROMPT = """You are an expert Odoo 16 database analyst.
You generate precise PostgreSQL queries for an Odoo 16 database.

CRITICAL - Odoo 16 uses these EXACT table names (not older versions):
- Invoices / factures: account_move (NOT account_invoice which does NOT exist in Odoo 16)
  * Customer invoices: move_type = 'out_invoice'
  * Vendor bills: move_type = 'in_invoice'
  * Unpaid invoices: payment_state = 'not_paid'
  * Paid invoices: payment_state = 'paid'

- Customers / clients: res_partner WHERE customer_rank > 0
- All partners: res_partner
- Employees / employés: hr_employee (NOT res_partner)
- Products / produits: product_template (main) or product_product (variants)
- Product categories: product_category
- Sales orders: sale_order + sale_order_line
  * Revenue / chiffre d'affaires: SUM(amount_untaxed) FROM sale_order WHERE state IN ('sale','done')
- Purchase orders: purchase_order + purchase_order_line
- Stock levels: stock_quant
- Stock moves: stock_move
- Deliveries: stock_picking
- CRM leads: crm_lead
- Departments: hr_department
- Users: res_users
- Company: res_company
- Currency: res_currency
- Payments: account_payment

EXAMPLES:
Q: Combien de clients avons-nous ?
A: SELECT COUNT(*) FROM res_partner WHERE customer_rank > 0

Q: Combien d'employés avons-nous ?
A: SELECT COUNT(*) FROM hr_employee WHERE active = TRUE

Q: Liste des produits disponibles
A: SELECT name, list_price, type FROM product_template WHERE active = TRUE LIMIT 50

Q: Liste des produits
A: SELECT name, list_price FROM product_template WHERE active = TRUE LIMIT 50

Q: Quel est le chiffre d'affaires total ?
A: SELECT SUM(amount_untaxed) AS total FROM sale_order WHERE state IN ('sale', 'done')

Q: Liste des factures impayées
A: SELECT name, amount_total FROM account_move WHERE move_type = 'out_invoice' AND payment_state = 'not_paid' LIMIT 50

Q: Combien de commandes de vente avons-nous ?
A: SELECT COUNT(*) FROM sale_order WHERE state IN ('sale', 'done')

Rules:
- Generate ONLY SELECT queries, never INSERT/UPDATE/DELETE/DROP
- NEVER use account_invoice, it does not exist in Odoo 16
- Always use table aliases for clarity
- Limit results to 50 rows maximum unless specified
- Return ONLY the raw SQL query, no explanation, no markdown, no backticks
"""


def sql_node(state: AgentState) -> AgentState:
    """
    Node SQL — génération et exécution de requêtes SQL
    """
    question = state["question"]
    session_id = state.get("session_id")
    logger.info(f"SQL Node - Question: '{question}'")

    schema_selector = SchemaSelector()
    executor = SQLExecutor()

    # Schéma ciblé
    schema_text = schema_selector.get_relevant_schema(question)

    # Historique
    history_text = ""
    if session_id:
        store = ConversationStore()
        history_text = store.format_history(session_id)

    prompt = f"""Database schema:
{schema_text}

{history_text}

Generate SQL for: {question}"""

    try:
        # Générer SQL
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_sql_model,
                "messages": [
                    {"role": "system", "content": SQL_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        raw_sql = response.json()["message"]["content"].strip()

        # Nettoyer le SQL
        sql_query = _extract_sql(raw_sql)
        logger.info(f"SQL généré: {sql_query}")

        # Exécuter
        execution_result = executor.execute(sql_query)

        # Interpréter
        if execution_result["success"]:
            answer = _interpret_results(question, sql_query, execution_result)
        else:
            answer = f"Erreur SQL : {execution_result['error']}"

    except Exception as e:
        logger.error(f"Erreur SQL Node: {e}")
        sql_query = ""
        execution_result = {"success": False, "error": str(e)}
        answer = f"Erreur lors de la génération SQL : {e}"

    return {
        **state,
        "answer": answer,
        "sql_query": sql_query,
        "sql_result": execution_result,
    }


def _extract_sql(raw: str) -> str:
    """Extrait le SQL propre depuis la réponse du LLM"""
    raw = re.sub(r'```sql\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    lines = [l for l in raw.strip().split('\n')
             if not l.strip().startswith('--')]
    return '\n'.join(lines).strip()


def _interpret_results(question: str, sql: str, result: dict) -> str:
    """Interprète les résultats SQL en langage naturel"""
    prompt = f"""Question: {question}
SQL: {sql}
Results: {result['results'][:10]}
Row count: {result['row_count']}

Provide a clear, concise answer in the same language as the question."""

    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=60,
        )
        return response.json()["message"]["content"].strip()
    except Exception as e:
        return f"Résultat : {result['results']}"
