import logging
from agents.state import AgentState
from tools.retriever import RAGRetriever
from tools.groq_client import call_groq
from db.conversation_store import ConversationStore

logger = logging.getLogger(__name__)

RAG_SYSTEM = """You are an expert Odoo 16 consultant.
Answer questions based ONLY on the provided documentation context.

RULES:
- Answer in the SAME language as the question (French → French, English → English)
- Be precise and practical
- If context is insufficient, say so clearly
- Mention the relevant Odoo module when useful
- No hallucination — stick to the context
"""


def rag_node(state: AgentState) -> AgentState:
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

    # Construire contexte
    context_parts = []
    sources = []
    for i, r in enumerate(results):
        context_parts.append(f"[Extrait {i + 1}]\n{r['content']}")
        source = r["metadata"].get("source", "unknown")
        url = r["metadata"].get("url", "")
        if source not in [s["source"] for s in sources]:
            sources.append({"source": source, "url": url, "score": r["score"]})

    context = "\n\n".join(context_parts)

    history_text = ""
    if session_id:
        store = ConversationStore()
        history_text = store.format_history(session_id)

    prompt = f"""DOCUMENTATION:
{context}

{history_text}

QUESTION: {question}

ANSWER:"""

    try:
        answer = call_groq(
            prompt=prompt, system=RAG_SYSTEM, max_tokens=1000, temperature=0
        )
    except Exception as e:
        logger.error(f"Erreur RAG Gemini: {e}")
        answer = "Erreur lors de la génération de la réponse."

    return {
        **state,
        "answer": answer,
        "sources": sources,
        "context_used": context,
    }
