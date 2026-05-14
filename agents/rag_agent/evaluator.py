import logging

from langchain_groq import ChatGroq

from config.settings import settings

logger = logging.getLogger(__name__)

llm = ChatGroq(
    model="meta-llama/llama-4-scout-17b-16e-instruct",
    api_key=settings.groq_api_key,
    temperature=0,
)

EVALUATE_PROMPT = """You are a relevance evaluator for Odoo documentation answers.

Given a question and an answer, evaluate if the answer is relevant and complete.

Reply with ONLY one of these two words:
- RELEVANT if the answer correctly addresses the question using the documentation
- NOT_RELEVANT if the answer is incomplete, off-topic, or says it could not find information
"""


def evaluate_relevance(question: str, answer: str) -> str:
    """
    Évalue si la réponse est pertinente par rapport à la question.
    Retourne 'RELEVANT' ou 'NOT_RELEVANT'.
    """
    try:
        response = llm.invoke([
            {"role": "system", "content": EVALUATE_PROMPT},
            {"role": "user", "content": f"Question: {question}\nAnswer: {answer}"}
        ])
        result = response.content.strip().upper()
        if "NOT_RELEVANT" in result:
            verdict = "NOT_RELEVANT"
        else:
            verdict = "RELEVANT"
        logger.info(f"Évaluation: {verdict}")
        return verdict
    except Exception as e:
        logger.error(f"Erreur evaluator: {e}")
        return "RELEVANT"
