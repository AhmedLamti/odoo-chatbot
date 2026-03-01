import logging
import requests
from agents.rag_agent import RAGAgent
from agents.sql_agent import SQLAgent
from config.settings import settings
from db.conversation_store import ConversationStore


logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Router principal - Analyse la question et route vers
    le bon agent (RAG ou SQL)
    """

    SYSTEM_PROMPT = """You are a router that classifies questions about Odoo.

    SQL agent handles:
    - Questions about counts and numbers (combien, how many, total, chiffre)
    - Questions asking for lists of data from the database
    - Questions about statistics and reports
    - Questions about specific records (commandes du mois, orders this month)

    RAG agent handles:
    - Questions starting with "Comment" (how to do something)
    - Questions about HOW to use or configure Odoo
    - Questions about features, modules, documentation
    - Questions about installation and setup steps
    - "Comment créer", "Comment configurer", "How to", "How do I"

    IMPORTANT: "Comment créer une facture" = RAG (how to create)
    IMPORTANT: "Combien de factures" = SQL (count data)

    Reply with ONLY one word: RAG or SQL
    """

    def __init__(self):
        self.rag_agent = RAGAgent(top_k=5)
        self.sql_agent = SQLAgent()
        self.store = ConversationStore()


    def _classify(self, question: str) -> str:
        """Classifie la question : RAG ou SQL"""
        try:
            response = requests.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_llm_model,
                    "messages": [
                        {"role": "system", "content": self.SYSTEM_PROMPT},
                        {"role": "user", "content": question},
                    ],
                    "stream": False,
                },
                timeout=30,
            )
            response.raise_for_status()
            decision = response.json()["message"]["content"].strip().upper()

            # Sécurité : si la réponse n'est pas claire → RAG par défaut
            if "SQL" in decision:
                return "SQL"
            return "RAG"

        except Exception as e:
            logger.error(f"Erreur classification: {e}")
            return "RAG"  # fallback

    def run(self, question: str, session_id: str = None) -> dict:
        """
        Route la question vers le bon agent
        Sauvegarde l'historique si session_id fourni
        """
        logger.info(f"Orchestrator - Question: '{question}'")

        # Classification
        agent_type = self._classify(question)
        logger.info(f"Routing → {agent_type} Agent")

        # Exécution avec session
        if agent_type == "SQL":
            result = self.sql_agent.run(question, session_id=session_id)
            response = {
                "answer": result["answer"],
                "agent_used": "SQL",
                "sql_query": result.get("sql_query"),
                "sources": None,
            }
        else:
            result = self.rag_agent.run(question, session_id=session_id)
            response = {
                "answer": result["answer"],
                "agent_used": "RAG",
                "sql_query": None,
                "sources": result.get("sources"),
            }

        # Sauvegarder dans l'historique
        if session_id:
            self.store.add_message(session_id, "user", question)
            self.store.add_message(session_id, "assistant", response["answer"])

        return response
