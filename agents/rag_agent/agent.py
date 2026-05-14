import logging

from langchain_groq import ChatGroq

from agents.rag_agent.evaluator import evaluate_relevance
from agents.rag_agent.retriever import retrieve, format_context, extract_sources
from agents.rag_agent.rewriter import rewrite_query
from config.settings import settings

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2

llm = ChatGroq(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    api_key=settings.groq_api_key,
    temperature=0,
)

GENERATE_PROMPT = """You are an expert Odoo 16 consultant.
Answer questions based ONLY on the provided documentation context.

RULES:
- ALWAYS answer in the SAME language as the question
- French question → French answer
- English question → English answer
- Be precise and practical
- If context is insufficient, say so clearly — do NOT invent

CRITICAL: If the context does not contain enough information,
reply ONLY with:
  French: "Je n'ai pas trouvé cette information dans la documentation Odoo."
  English: "I could not find this information in the Odoo documentation."
"""


def generate_answer(question: str, context: str) -> str:
    """
    Génère une réponse basée sur le contexte récupéré.
    """
    try:
        prompt = f"""DOCUMENTATION CONTEXT:
{context}

QUESTION: {question}

ANSWER (based strictly on the context above):"""

        response = llm.invoke([
            {"role": "system", "content": GENERATE_PROMPT},
            {"role": "user", "content": prompt}
        ])
        return response.content.strip()
    except Exception as e:
        logger.error(f"Erreur generate: {e}")
        return "Erreur lors de la génération de la réponse."


def run_rag_agent(state: dict) -> dict:
    """
    Flow complet de l'Agentic RAG — appelé par LangGraph comme node.
    """
    question = state["question"]
    logger.info(f"RAG Agent - Question: '{question}'")

    current_query = question
    answer = ""
    sources = []
    attempts = 0

    while attempts < MAX_ATTEMPTS:
        attempts += 1
        logger.info(f"Tentative {attempts}/{MAX_ATTEMPTS}")

        rewritten = rewrite_query(current_query)
        chunks = retrieve(rewritten, top_k=8)

        if not chunks:
            logger.warning("Aucun chunk trouvé")
            answer = (
                "Je n'ai pas trouvé cette information dans la documentation Odoo."
                if any(w in question.lower() for w in ["comment", "qu", "quel", "est"])
                else "I could not find this information in the Odoo documentation."
            )
            sources = []
            break

        context = format_context(chunks)
        sources = extract_sources(chunks)
        answer = generate_answer(question, context)

        verdict = evaluate_relevance(question, answer)

        if verdict == "RELEVANT":
            logger.info(f"Réponse acceptée à la tentative {attempts}")
            break

        if attempts < MAX_ATTEMPTS:
            logger.info("Réponse non pertinente — nouvelle tentative")
            current_query = f"{question} detailed steps configuration Odoo 16"

    return {
        "answer": answer,
        "sources": sources,
        "metadata": {
            "attempts": attempts,
            "rewritten_query": rewrite_query(question),
        },
    }
