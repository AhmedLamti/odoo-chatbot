"""
État global du graphe orchestrateur.
Transit entre tous les nœuds via ce TypedDict.
"""
from __future__ import annotations

from typing import Annotated, Any, Optional, Callable

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class OrchestratorState(TypedDict):
    # ── Entrée utilisateur ────────────────────────────────────────────────────
    question: str
    session_id: str

    # ── Décision du router ────────────────────────────────────────────────────
    route: Optional[str]  # "rag" | "data" | "action" | "chat"

    # ── Historique de conversation ────────────────────────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Résultat final ────────────────────────────────────────────────────────
    answer: str
    sources: list[str]  # RAG uniquement
    steps: list[str]  # Data agent uniquement
    needs_confirmation: bool  # Action agent uniquement
    confirmation_summary: str  # Action agent uniquement
    metadata: dict[str, Any]
    on_step: Optional[Callable]
