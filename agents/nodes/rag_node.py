import logging
from agents.state import AgentState
from tools.retriever import RAGRetriever
from tools.groq_client import call_groq
from db.conversation_store import ConversationStore

logger = logging.getLogger(__name__)

RAG_SYSTEM = """You are an expert Odoo 16 consultant.
Answer questions based ONLY on the provided documentation context.

RULES:
- The documentation context may be in English — this is normal, Odoo docs are in English
- ALWAYS answer in the SAME language as the question (French question → French answer, even if context is in English)
- Translate and adapt the documentation content into the question's language
- Be precise and practical, mention the relevant Odoo module when useful
- No hallucination — stick strictly to what the context says

CRITICAL: If the context does not contain enough information to answer the question,
reply ONLY with this exact phrase (in the question's language):
  French: "Je n'ai pas trouvé cette information dans la documentation Odoo."
  English: "I could not find this information in the Odoo documentation."
Do NOT attempt to answer from general knowledge. Do NOT invent steps or procedures.
"""


TRANSLATE_SYSTEM = """Translate the following question to English for Odoo documentation search.
Return ONLY the translated question, nothing else. No explanation."""


def _translate_to_english(question: str) -> str:
    """Traduit la question en anglais pour améliorer le matching avec la doc Odoo (anglais uniquement)"""
    english_indicators = ["how", "what", "where", "when", "which", "can i", "do i", "is it"]
    if any(question.lower().startswith(w) for w in english_indicators):
        return question
    try:
        translated = call_groq(
            prompt=question,
            system=TRANSLATE_SYSTEM,
            max_tokens=100,
            temperature=0,
        )
        logger.info(f"Question traduite pour recherche: '{question}' → '{translated}'")
        return translated
    except Exception as e:
        logger.warning(f"Traduction échouée, question originale utilisée: {e}")
        return question


def rag_node(state: AgentState) -> AgentState:
    question = state["question"]
    session_id = state.get("session_id")
    logger.info(f"RAG Node - Question: '{question}'")

    # Traduire en anglais pour matcher la doc Odoo (anglais uniquement dans Qdrant)
    search_query = _translate_to_english(question)

    retriever = RAGRetriever(top_k=8)
    results = retriever.retrieve(search_query)

    if not results:
        return {
            **state,
            "answer": "Je n'ai pas trouvé d'information pertinente dans la documentation Odoo.",
            "sources": [],
        }

    # Seuil bas car chunks petits = scores dilués mais toujours pertinents
    MIN_SCORE = 0.30
    results = [r for r in results if r.get("score", 0) >= MIN_SCORE]

    if not results:
        logger.warning(f"RAG - tous les scores < {MIN_SCORE}, aucun contexte pertinent")
        return {
            **state,
            "answer": "Je n'ai pas trouvé d'information suffisamment pertinente dans la documentation Odoo.",
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

    prompt = f"""DOCUMENTATION CONTEXT:
{context}

{history_text}

QUESTION: {question}

ANSWER (based strictly on the context above):"""

    try:
        answer = call_groq(
            prompt=prompt, system=RAG_SYSTEM, max_tokens=1000, temperature=0
        )
    except Exception as e:
        logger.error(f"Erreur RAG Groq: {e}")
        answer = "Erreur lors de la génération de la réponse."

    return {
        **state,
        "answer": answer,
        "sources": sources,
        "context_used": context,
    }
