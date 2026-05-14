"""
Logique de routage : décide quel agent exécuter après l'orchestrateur.
Séparé de builder.py pour rester lisible et testable isolément.
"""
from __future__ import annotations

from Graph.state import OrchestratorState

_FALLBACK = "chat"


def route_selector(state: OrchestratorState) -> str:
    """
    Fonction de sélection pour conditional_edges.
    Retourne le nom du nœud suivant.
    """
    return state.get("route", _FALLBACK)
