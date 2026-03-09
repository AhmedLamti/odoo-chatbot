import logging
import requests
from agents.state import AgentState
from tools.retriever import RAGRetriever
from config.settings import settings
from db.conversation_store import ConversationStore

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """You are an expert Odoo consultant with deep knowledge of Odoo 16.
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


def rag_node(state: AgentState) -> AgentState:
    """
    Node RAG — recherche documentaire et génération de réponse
    """
    question = state["question"]
    session_id = state.get("session_id")
    logger.info(f"RAG Node - Question: '{question}'")

    retriever = RAGRetriever(top_k=5)
    results = retriever.retrieve(question)

    if not results:
        return {
            **state,
            "answer": "Je n'ai pas trouvé d'information pertinente dans la documentation Odoo.",
            "sources": [],
        }

    # Construire le contexte
    context_parts = []
    sources = []
    for i, r in enumerate(results):
        context_parts.append(f"[Extrait {i+1}]\n{r['content']}")
        source = r["metadata"].get("source", "unknown")
        url = r["metadata"].get("url", "")
        if source not in [s["source"] for s in sources]:
            sources.append({
                "source": source,
                "url": url,
                "score": r["score"]
            })

    context = "\n\n".join(context_parts)

    # Historique conversation
    history_text = ""
    if session_id:
        store = ConversationStore()
        history_text = store.format_history(session_id)

    prompt = f"""DOCUMENTATION CONTEXT:
{context}

{history_text}

QUESTION: {question}

ANSWER:"""

    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "messages": [
                    {"role": "system", "content": RAG_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        answer = response.json()["message"]["content"].strip()

    except Exception as e:
        logger.error(f"Erreur RAG LLM: {e}")
        answer = "Erreur lors de la génération de la réponse."

    return {
        **state,
        "answer": answer,
        "sources": sources,
        "context_used": context,
    }
