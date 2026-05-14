"""
Nœud orchestrateur : classifie la question et écrit la route dans l'état.
Pas d'outils — uniquement du raisonnement LLM.
"""
from __future__ import annotations

from Graph.state import OrchestratorState
from agents.orchestrator_agent.prompts import ROUTER_SYSTEM_PROMPT, ROUTER_USER_TEMPLATE
from shared.llm_factory import get_llm, LLMProvider
from shared.utils import get_logger

logger = get_logger(__name__)

_VALID_ROUTES = {"rag", "data", "action", "chat"}
_FALLBACK = "chat"

_llm = get_llm(LLMProvider.GROQ)


def orchestrator_node(state: OrchestratorState) -> dict:
    """Classifie la question et retourne {'route': ...}."""
    question = state["question"]
    logger.info(f"[orchestrator] Classification : '{question[:80]}'")

    route = _classify(question)
    logger.info(f"[orchestrator] Route → {route}")
    return {"route": route}


def _classify(question: str) -> str:
    try:
        response = _llm.invoke([
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": ROUTER_USER_TEMPLATE.format(question=question)},
        ])
        raw = response.content.strip().lower()
        if raw not in _VALID_ROUTES:
            logger.warning(f"[orchestrator] Réponse inattendue '{raw}' → fallback '{_FALLBACK}'")
            return _FALLBACK
        return raw
    except Exception as e:
        logger.error(f"[orchestrator] Erreur LLM ({e}) → fallback '{_FALLBACK}'")
        return _FALLBACK
