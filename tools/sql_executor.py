import logging
import re
from db.sql_connector import SQLConnector

logger = logging.getLogger(__name__)

# Opérations interdites
FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "TRUNCATE", "INSERT",
    "UPDATE", "ALTER", "CREATE", "GRANT", "REVOKE"
]


class SQLExecutor:
    """
    Exécute les requêtes SQL générées par le SQL Agent
    avec validation de sécurité
    """

    def __init__(self):
        self.connector = SQLConnector()

    def validate_query(self, query: str) -> tuple[bool, str]:
        """
        Valide que la requête est safe (SELECT uniquement)
        """
        query_upper = query.upper().strip()

        # Doit commencer par SELECT
        if not query_upper.startswith("SELECT"):
            return False, "Seules les requêtes SELECT sont autorisées"

        # Vérifier les mots clés interdits
        for keyword in FORBIDDEN_KEYWORDS:
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, query_upper):
                return False, f"Mot clé interdit détecté: {keyword}"

        return True, "OK"

    def execute(self, query: str) -> dict:
        """
        Valide et exécute une requête SQL
        Retourne les résultats avec métadonnées
        """
        # Nettoyage
        query = query.strip().rstrip(";") + ";"

        # Validation
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

        # Exécution
        try:
            logger.info(f"Exécution SQL: {query}")
            results = self.connector.execute_query(query)
            logger.info(f"{len(results)} lignes retournées")
            return {
                "success": True,
                "query": query,
                "results": results,
                "row_count": len(results),
                "error": None,
            }
        except Exception as e:
            logger.error(f"Erreur SQL: {e}")
            return {
                "success": False,
                "error": str(e),
                "query": query,
                "results": [],
                "row_count": 0,
            }

    def format_results(self, execution_result: dict) -> str:
        """
        Formate les résultats SQL pour le LLM
        """
        if not execution_result["success"]:
            return f"Erreur SQL: {execution_result['error']}"

        results = execution_result["results"]
        if not results:
            return "La requête n'a retourné aucun résultat."

        # Header
        columns = list(results[0].keys())
        lines = [" | ".join(columns)]
        lines.append("-" * len(lines[0]))

        # Rows (max 50 pour éviter les réponses trop longues)
        for row in results[:50]:
            lines.append(" | ".join(str(v) for v in row.values()))

        if len(results) > 50:
            lines.append(f"... et {len(results) - 50} lignes supplémentaires")

        lines.append(f"\nTotal: {execution_result['row_count']} ligne(s)")
        return "\n".join(lines)
