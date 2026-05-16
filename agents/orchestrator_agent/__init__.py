from __future__ import annotations

import logging
import uuid
from typing import Any

from Graph.builder import orchestrator_graph
from Graph.state import OrchestratorState

logger = logging.getLogger(__name__)

# Mapping nœud → label lisible pour le frontend
_NODE_LABELS = {
    "orchestrator": "Analyse de la question",
    "rag": "Recherche documentaire",
    "data": "Interrogation des données",
    "action": "Préparation de l'action",
    "chat": "Génération de la réponse",
}


def run_orchestrator(
        question: str,
        session_id: str | None = None,
        history: list | None = None,
        on_step=None,
        llm_provider=None,

) -> dict[str, Any]:
    session_id = session_id or str(uuid.uuid4())
    logger.info(f"[orchestrator] session={session_id} question='{question[:80]}'")

    initial_state: OrchestratorState = {
        "question": question,
        "session_id": session_id,
        "route": None,
        "messages": history or [],
        "answer": "",
        "sources": [],
        "steps": [],
        "needs_confirmation": False,
        "confirmation_summary": "",
        "metadata": {},
        "on_step": on_step,
        "llm_provider": llm_provider,
    }

    config = {"configurable": {"thread_id": session_id}}
    final_state = None
    step_num = 0

    # .stream() émet un dict par nœud exécuté au fur et à mesure
    for chunk in orchestrator_graph.stream(initial_state, config=config):
        for node_name, node_state in chunk.items():
            step_num += 1
            label = _NODE_LABELS.get(node_name, node_name)
            logger.info(f"[orchestrator] step {step_num} — {node_name}")

            # Appel du callback SSE si fourni
            if on_step:
                try:
                    on_step(step_num, label)
                except Exception as e:
                    logger.warning(f"[orchestrator] on_step error: {e}")

            # Garde le dernier état pour extraire la réponse finale
            final_state = node_state

    if final_state is None:
        return {"route": None, "answer": "", "sources": [], "steps": [],
                "needs_confirmation": False, "confirmation_summary": "", "metadata": {}}

    return {
        "route": final_state.get("route"),
        "answer": final_state.get("answer", ""),
        "sources": final_state.get("sources", []),
        "steps": final_state.get("steps", []),
        "needs_confirmation": final_state.get("needs_confirmation", False),
        "confirmation_summary": final_state.get("confirmation_summary", ""),
        "metadata": final_state.get("metadata", {}),
    }
