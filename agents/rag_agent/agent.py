# ── agents/rag_agent/agent.py ─────────────────────────────────────────────────
# Node LangGraph du RAG Agent.
#
# Responsabilité unique : orchestrer les appels aux sous-modules
# (rewriter, retriever, evaluator) et retourner l'état LangGraph.
#
# Règles d'architecture :
#   - Pas de LLM instancié ici — toujours via llm_factory
#   - Pas de logique métier complexe — déléguer aux sous-modules
#   - Les constantes de configuration restent en haut du fichier
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from typing import Callable

from agents.rag_agent.evaluator import evaluate_relevance, RELEVANT
from agents.rag_agent.retriever import retrieve, format_context, extract_sources
from agents.rag_agent.rewriter  import rewrite_query
from shared.llm_factory          import get_llm, LLMProvider

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

_MAX_ATTEMPTS    = 2
_DEFAULT_PROVIDER = LLMProvider.GROQ_QWEN3

# Mots-clés français pour la détection de langue (heuristique légère).
_FRENCH_KEYWORDS = {"comment", "qu", "quel", "quelle", "est", "les", "des", "une", "un"}

_NOT_FOUND_FR = "Je n'ai pas trouvé cette information dans la documentation Odoo."
_NOT_FOUND_EN = "I could not find this information in the Odoo documentation."

# Libellés SSE des étapes
_STEPS = {
    "rewrite":  "Réécriture de la requête",
    "retrieve": "Recherche dans la documentation",
    "generate": "Génération de la réponse",
    "evaluate": "Évaluation de la pertinence",
    "retry":    "Nouvelle tentative — reformulation",
    "accepted": "Réponse acceptée",
}

# ── Prompt de génération ───────────────────────────────────────────────────────

_GENERATE_SYSTEM_PROMPT = """You are an expert Odoo 16 consultant.
Answer questions based ONLY on the provided documentation context.

RULES:
- ALWAYS answer in the SAME language as the question
- French question → French answer
- English question → English answer
- Be precise and practical
- If context is insufficient, say so clearly — do NOT invent

CRITICAL: If the context does not contain enough information, reply ONLY with:
  French : "Je n'ai pas trouvé cette information dans la documentation Odoo."
  English: "I could not find this information in the Odoo documentation."
"""

# ── Types ──────────────────────────────────────────────────────────────────────

StepCallback = Callable[[int, str], None]


def _default_step_callback(step: int, message: str) -> None:
    """Affichage console — remplacé par un callback SSE en production."""
    print(f"  Étape {step} — {message}")


# ── Helpers privés ─────────────────────────────────────────────────────────────


def _detect_not_found_message(question: str) -> str:
    """Retourne le message 'non trouvé' dans la langue de la question."""
    words = set(question.lower().split())
    return _NOT_FOUND_FR if words & _FRENCH_KEYWORDS else _NOT_FOUND_EN


def _generate_answer(question: str, context: str, llm) -> str:
    """
    Génère une réponse basée strictement sur le contexte documentaire.

    Args:
        question: Question originale de l'utilisateur.
        context:  Contexte formaté produit par retriever.format_context().
        llm:      Instance LangChain fournie par llm_factory.

    Returns:
        Réponse textuelle, ou message d'erreur générique.
    """
    try:
        user_prompt = (
            f"DOCUMENTATION CONTEXT:\n{context}\n\n"
            f"QUESTION: {question}\n\n"
            f"ANSWER (based strictly on the context above):"
        )
        response = llm.invoke([
            {"role": "system", "content": _GENERATE_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ])
        return response.content.strip()
    except Exception as exc:
        logger.error("[rag_agent] Erreur génération : %s", exc)
        return "Erreur lors de la génération de la réponse."


def _emit(callback: StepCallback, steps: list[str], key: str) -> None:
    """Enregistre une étape et appelle le callback SSE."""
    label = _STEPS[key]
    steps.append(label)
    callback(len(steps) - 1, label)


# ── Node LangGraph ─────────────────────────────────────────────────────────────


def run_rag_agent(state: dict) -> dict:
    """
    Node LangGraph — exécute le pipeline RAG complet.

    Lit depuis *state* :
        question     (str)           — obligatoire
        on_step      (callable|None) — callback SSE (step, message) -> None
        llm_provider (str|None)      — provider sélectionné par le frontend

    Écrit dans le state retourné :
        answer   (str)        — réponse finale
        sources  (list[dict]) — sources documentaires utilisées
        steps    (list[str])  — journal des étapes pour le frontend
        metadata (dict)       — infos de débogage
    """
    question = state["question"]
    callback = state.get("on_step") or _default_step_callback
    provider = state.get("llm_provider")
    llm      = get_llm(provider) if provider else get_llm(_DEFAULT_PROVIDER)

    logger.info("[rag_agent] question='%s'", question[:80])

    answer:          str        = ""
    sources:         list[dict] = []
    steps:           list[str]  = []
    final_rewritten: str        = question
    current_query:   str        = question

    for attempt in range(1, _MAX_ATTEMPTS + 1):

        # Réécriture
        _emit(callback, steps, "rewrite")
        rewritten       = rewrite_query(current_query, llm)
        final_rewritten = rewritten

        # Retrieval
        _emit(callback, steps, "retrieve")
        chunks = retrieve(rewritten, top_k=8)

        if not chunks:
            logger.warning("[rag_agent] Aucun chunk trouvé")
            answer  = _detect_not_found_message(question)
            sources = []
            break

        context = format_context(chunks)
        sources = extract_sources(chunks)

        # Génération
        _emit(callback, steps, "generate")
        answer = _generate_answer(question, context, llm)

        # Évaluation
        _emit(callback, steps, "evaluate")
        verdict = evaluate_relevance(question, answer, llm)

        if verdict == RELEVANT:
            _emit(callback, steps, "accepted")
            logger.info("[rag_agent] Réponse acceptée à la tentative %d", attempt)
            break

        if attempt < _MAX_ATTEMPTS:
            _emit(callback, steps, "retry")
            logger.info("[rag_agent] Réponse non pertinente — nouvelle tentative")
            current_query = f"{question} detailed steps configuration Odoo 16"

    return {
        "answer":  answer,
        "sources": sources,
        "steps":   steps,
        "metadata": {
            "handled_by":      "rag_agent",
            "attempts":        attempt,
            "rewritten_query": final_rewritten,
        },
    }
