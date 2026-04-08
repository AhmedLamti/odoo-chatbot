"""
SQL Executor Node — avec gestion d'erreurs
"""

import logging
from agents.state import AgentState
from tools.sql_executor import SQLExecutor
from tools.cerebras_client import call_cerebras

logger = logging.getLogger(__name__)

INTERPRET_SYSTEM = """You are an Odoo data analyst.
Read the Results and summarize them.

CRITICAL RULES:
- ALWAYS respond in the SAME language as the question
- Question en français → réponse en français OBLIGATOIRE
- Question in English → answer in English
- Use EXACT numbers from Results, never calculate manually
- Present as a clean list if multiple rows
- 3-4 sentences max, no code, no SQL
"""


def sql_executor_node(state: AgentState) -> AgentState:
    agent_used = state.get("agent_used")
    logger.info(f"SQL Executor Node - agent='{agent_used}'")

    # Ne pas exécuter si une erreur upstream existe déjà
    if state.get("error"):
        return state

    try:
        executor = SQLExecutor()

        # ── Flow ACTION ──
        if agent_used == "ACTION":
            sql_query = state.get("action_sql_query", "")
            if not sql_query:
                return {
                    **state,
                    "action_sql_result": {"success": False, "error": "SQL vide"},
                    "error": "action_sql_query vide — action_parser n'a pas généré de SQL",
                    "error_origin": "sql_executor",
                }
            result = executor.execute(sql_query)
            if not result["success"]:
                return {
                    **state,
                    "action_sql_result": result,
                    "error": result["error"],
                    "error_origin": "sql_executor",
                }
            return {**state, "action_sql_result": result, "error": None}

        # ── Flow SQL / DASHBOARD ──
        question = state["question"]
        sql_query = state.get("sql_query", "")

        if not sql_query:
            return {
                **state,
                "sql_result": {"success": False, "error": "SQL vide"},
                "answer": "Erreur : aucune requête SQL générée.",
                "error": "sql_query vide",
                "error_origin": "sql_executor",
            }

        result = executor.execute(sql_query)

        if not result["success"]:
            return {
                **state,
                "sql_result": result,
                "answer": f"Erreur SQL : {result['error']}",
                "error": result["error"],
                "error_origin": "sql_executor",
            }

        answer = _interpret(question, sql_query, result)
        return {**state, "sql_result": result, "answer": answer, "error": None}

    except Exception as e:
        logger.error(f"Erreur SQL Executor: {e}")
        return {
            **state,
            "error": str(e),
            "error_origin": "sql_executor",
        }


def _interpret(question: str, sql: str, result: dict) -> str:
    try:
        lang = (
            "French"
            if any(
                w in question.lower()
                for w in [
                    "liste",
                    "combien",
                    "quel",
                    "quels",
                    "donne",
                    "affiche",
                    "facture",
                    "client",
                    "vendeur",
                ]
            )
            else "English"
        )
        return call_cerebras(
            prompt=f"Language to use: {lang}\nQuestion: {question}\n"
            f"Results: {result['results'][:10]}\nRow count: {result['row_count']}\n"
            f"Answer in {lang} using EXACT data from Results.",
            system=INTERPRET_SYSTEM,
            max_tokens=200,
            temperature=0,
        )
    except Exception as e:
        logger.error(f"Erreur interprétation: {e}")
        return f"Résultats : {result['results'][:5]}"
