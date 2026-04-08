import logging
import re
from db.sql_connector import SQLConnector
from utils.retry import with_retry

logger = logging.getLogger(__name__)

FORBIDDEN_KEYWORDS = [
    "DROP",
    "DELETE",
    "TRUNCATE",
    "INSERT",
    "UPDATE",
    "ALTER",
    "CREATE",
    "GRANT",
    "REVOKE",
]


class SQLExecutor:
    """
    Exécute les requêtes SQL avec validation de sécurité et retry PostgreSQL
    """

    def __init__(self):
        self.connector = SQLConnector()

    def validate_query(self, query: str) -> tuple[bool, str]:
        query_upper = query.upper().strip()

        # Doit commencer par SELECT (avec ou sans parenthèse pour UNION ALL)
        cleaned = query_upper.lstrip("(")
        if not cleaned.startswith("SELECT"):
            return False, "Seules les requêtes SELECT sont autorisées"

        for keyword in FORBIDDEN_KEYWORDS:
            pattern = r"\b" + keyword + r"\b"
            if re.search(pattern, query_upper):
                return False, f"Mot clé interdit détecté: {keyword}"

        return True, "OK"

    @with_retry(max_attempts=3, delay=0.5, backoff=2.0)
    def _execute_query(self, query: str) -> list:
        """Exécution avec retry sur les erreurs PostgreSQL transitoires"""
        return self.connector.execute_query(query)

    def execute(self, query: str) -> dict:
        query = query.strip().rstrip(";") + ";"

        is_valid, message = self.validate_query(query)
        if not is_valid:
            logger.warning(f"Requête rejetée: {message}")
            return {
                "success": False,
                "error": message,
                "query": query,
                "results": [],
                "row_count": 0,
            }

        try:
            logger.info(f"Exécution SQL: {query}")
            results = self._execute_query(query)
            logger.info(f"{len(results)} lignes retournées")
            return {
                "success": True,
                "query": query,
                "results": results,
                "row_count": len(results),
                "error": None,
            }
        except Exception as e:
            logger.error(f"Erreur exécution query: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "results": [],
                "row_count": 0,
            }

    def format_results(self, execution_result: dict) -> str:
        if not execution_result["success"]:
            return f"Erreur SQL: {execution_result['error']}"

        results = execution_result["results"]
        if not results:
            return "La requête n'a retourné aucun résultat."

        columns = list(results[0].keys())
        lines = [" | ".join(columns)]
        lines.append("-" * len(lines[0]))

        for row in results[:50]:
            lines.append(" | ".join(str(v) for v in row.values()))

        if len(results) > 50:
            lines.append(f"... et {len(results) - 50} lignes supplémentaires")

        lines.append(f"\nTotal: {execution_result['row_count']} ligne(s)")
        return "\n".join(lines)
