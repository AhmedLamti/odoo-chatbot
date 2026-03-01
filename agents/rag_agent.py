import logging
import requests
import json
from tools.retriever import RAGRetriever
from config.settings import settings

logger = logging.getLogger(__name__)


class RAGAgent:
    """
    Agent RAG - Répond aux questions sur la documentation Odoo
    en utilisant les chunks indexés dans Qdrant
    """

    SYSTEM_PROMPT = """You are an expert Odoo consultant with deep knowledge of Odoo 16.
    Your role is to answer questions about Odoo based on the provided documentation context.

    Rules:
    - Answer ONLY based on the provided context
    - If the context doesn't contain enough information, say so clearly
    - Be precise and practical in your answers
    - If relevant, mention the Odoo module concerned
    - VERY IMPORTANT: Always answer in the SAME language as the question
    - If the question is in French, answer ENTIRELY in French
    - If the question is in English, answer ENTIRELY in English
    - If the question is in Arabic, answer ENTIRELY in Arabic
    """

    def __init__(self, top_k: int = 5):
        self.retriever = RAGRetriever(top_k=top_k)

    def _call_ollama(self, prompt: str) -> str:
        """Appel direct à Ollama API"""
        try:
            response = requests.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_llm_model,
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

    def run(self, question: str, session_id: str = None) -> dict:
        """
        Traite une question avec contexte historique
        """
        logger.info(f"RAG Agent - Question: '{question}'")

        # Récupérer le contexte RAG
        results = self.retriever.retrieve(question)

        if not results:
            return {
                "answer": "Je n'ai pas trouvé d'information pertinente dans la documentation Odoo.",
                "sources": [],
                "context_used": "",
            }

        # Construire le contexte documentaire
        context_parts = []
        sources = []
        for i, r in enumerate(results):
            context_parts.append(f"[Extrait {i + 1}]\n{r['content']}")
            source = r["metadata"].get("source", "unknown")
            url = r["metadata"].get("url", "")
            if source not in [s["source"] for s in sources]:
                sources.append({"source": source, "url": url, "score": r["score"]})

        context = "\n\n".join(context_parts)

        # Récupérer l'historique si session active
        history_text = ""
        if session_id:
            from db.conversation_store import ConversationStore
            store = ConversationStore()
            history_text = store.format_history(session_id)

        # Construire le prompt
        prompt = f"""Based on the following Odoo 16 documentation, answer the question.

    DOCUMENTATION CONTEXT:
    {context}

    {history_text}

    QUESTION: {question}

    ANSWER:"""

        # Appel LLM
        answer = self._call_ollama(prompt)

        logger.info("RAG Agent - Réponse générée")
        return {
            "answer": answer,
            "sources": sources,
            "context_used": context,
        }
