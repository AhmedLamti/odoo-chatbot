import logging
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.nodes.router_node import router_node
from agents.nodes.rag_node import rag_node
from agents.nodes.sql_node import sql_node
from agents.nodes.response_node import response_node
from agents.nodes.dashboard_node import dashboard_node

from db.conversation_store import ConversationStore

logger = logging.getLogger(__name__)


def decide_next_node(state: AgentState) -> str:
    """
    Fonction de routing — retourne le nom du prochain node
    """
    agent = state.get("agent_used", "RAG")
    logger.info(f"Routing → {agent}")
    return agent


def build_graph() -> StateGraph:
    """
    Construit et compile le graph LangGraph
    """
    graph = StateGraph(AgentState)

    # ── Ajouter les nodes ──
    graph.add_node("router", router_node)
    graph.add_node("RAG", rag_node)
    graph.add_node("SQL", sql_node)
    graph.add_node("DASHBOARD", dashboard_node)

    graph.add_node("response", response_node)

    # ── Point d'entrée ──
    graph.set_entry_point("router")

    # ── Edges conditionnels depuis le router ──
    graph.add_conditional_edges(
        "router",
        decide_next_node,
        {
            "RAG": "RAG",
            "SQL": "SQL",
            "DASHBOARD": "DASHBOARD",
        }
    )

    # ── Edges fixes vers response ──
    graph.add_edge("RAG", "response")
    graph.add_edge("SQL", "response")
    graph.add_edge("DASHBOARD", "response")

    # ── Point de sortie ──
    graph.add_edge("response", END)

    return graph.compile()


# Instance globale du graph
odoo_graph = build_graph()
