import logging
import requests
import json
import re
from tools.sql_executor import SQLExecutor
from db.schema_cache import SchemaCache
from config.settings import settings
from tools.schema_selector import SchemaSelector


logger = logging.getLogger(__name__)


class SQLAgent:
    """
    Agent SQL - Génère et exécute des requêtes SQL
    sur la base de données Odoo à partir de questions en langage naturel
    """

    SYSTEM_PROMPT = """You are an expert Odoo 16 database analyst.
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

    Rules:
    - Generate ONLY SELECT queries, never INSERT/UPDATE/DELETE/DROP
    - NEVER use account_invoice, it does not exist in Odoo 16
    - Always use table aliases for clarity
    - Limit results to 50 rows maximum unless specified
    - Return ONLY the raw SQL query, no explanation, no markdown, no backticks
    """

    def __init__(self):
        self.executor = SQLExecutor()
        self.schema_selector = SchemaSelector()

    def _call_ollama(self, prompt: str) -> str:
        """Appel à Ollama avec le modèle SQL"""
        try:
            response = requests.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_sql_model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            logger.error(f"Erreur Ollama: {e}")
            raise

    def _extract_sql(self, text: str) -> str:
        """Extrait la requête SQL du texte généré"""
        # Supprimer les backticks markdown
        text = re.sub(r'```sql\s*', '', text)
        text = re.sub(r'```\s*', '', text)
        # Nettoyer les espaces
        text = text.strip()
        # Prendre seulement la première requête SELECT
        match = re.search(r'(SELECT[\s\S]+?);?$', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text

    def _interpret_results(self, question: str, query: str, results: dict) -> str:
        """Interprète les résultats SQL en langage naturel"""
        formatted = self.executor.format_results(results)

        prompt = f"""Given this question about an Odoo database:
QUESTION: {question}

SQL Query executed:
{query}

Results:
{formatted}

Provide a clear, concise answer in the same language as the question.
If the question is in French, answer in French.
"""
        return self._call_ollama(prompt)

    def run(self, question: str, session_id: str = None) -> dict:
        """
        Traite une question SQL avec contexte historique
        """
        schema_text = self.schema_selector.get_relevant_schema(question)
        logger.info(f"SQL Agent - Question: '{question}'")

        # Récupérer l'historique
        history_text = ""
        if session_id:
            from db.conversation_store import ConversationStore
            store = ConversationStore()
            history_text = store.format_history(session_id)

        # Générer le SQL
        prompt = f"""Here is the Odoo 16 database schema:

    {schema_text}

    {history_text}

    Generate a PostgreSQL SELECT query to answer this question:
    {question}

    Return ONLY the SQL query, nothing else.
    """
        raw_sql = self._call_ollama(prompt)
        sql_query = self._extract_sql(raw_sql)
        logger.info(f"Requête générée: {sql_query}")

        # Exécuter
        execution_result = self.executor.execute(sql_query)

        # Interpréter
        if execution_result["success"]:
            answer = self._interpret_results(question, sql_query, execution_result)
        else:
            answer = f"Erreur lors de l'exécution : {execution_result['error']}"

        return {
            "answer": answer,
            "sql_query": sql_query,
            "execution_result": execution_result,
        }
