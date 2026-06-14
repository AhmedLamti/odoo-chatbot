import logging

from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

# ── Prompt ─────────────────────────────────────────────────────────────────────

_EVALUATE_PROMPT = """You are a relevance evaluator for Odoo documentation answers.

Given a question and an answer, evaluate if the answer is relevant and complete.

Reply with ONLY one of these two words:
- RELEVANT     if the answer correctly addresses the question using the documentation
- NOT_RELEVANT if the answer is incomplete, off-topic, or says it could not find
               information
"""

# ── Constantes publiques ───────────────────────────────────────────────────────

RELEVANT     = "RELEVANT"
NOT_RELEVANT = "NOT_RELEVANT"


# ── Fonction publique ──────────────────────────────────────────────────────────


def evaluate_relevance(question: str, answer: str, llm: BaseChatModel) -> str:
    """
    Évalue si *answer* répond correctement à *question*.

    Args:
        question: La question originale de l'utilisateur.
        answer:   La réponse générée par le RAG.
        llm:      Instance LangChain déjà construite par llm_factory.

    Returns:
        ``"RELEVANT"`` ou ``"NOT_RELEVANT"``.
        En cas d'erreur LLM, retourne ``"RELEVANT"`` (fail-open
        pour ne pas bloquer l'utilisateur).
    """
    try:
        response = llm.invoke([
            {"role": "system", "content": _EVALUATE_PROMPT},
            {
                "role": "user",
                "content": f"Question: {question}\nAnswer: {answer}",
            },
        ])
        raw     = response.content.strip().upper()
        verdict = NOT_RELEVANT if NOT_RELEVANT in raw else RELEVANT
        logger.info("[evaluator] verdict=%s", verdict)
        return verdict
    except Exception as exc:
        logger.error("[evaluator] Erreur lors de l'évaluation : %s", exc)
        return RELEVANT  # fail-open
