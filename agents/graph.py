import logging
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.nodes.router_node import router_node
from agents.nodes.rag_node import rag_node
from agents.nodes.sql_node import sql_node
from agents.nodes.response_node import response_node
from agents.nodes.chart_node import chart_node
from agents.nodes.analysis_node import analysis_node


logger = logging.getLogger(__name__)


def decide_next_node(state: AgentState) -> str:
    agent = state.get("agent_used", "RAG")
    logger.info(f"Routing → {agent}")
    if agent == "DASHBOARD":
        return "SQL"
    return agent


def after_sql(state: AgentState) -> str:
    if state.get("agent_used") == "DASHBOARD":
        return "chart"
    return "response"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # ── Nodes ──
    graph.add_node("router", router_node)
    graph.add_node("RAG", rag_node)
    graph.add_node("SQL", sql_node)
    graph.add_node("chart", chart_node)
    graph.add_node("response", response_node)
    graph.add_node("chart_analysis", analysis_node)

    # ── Entry point ──
    graph.set_entry_point("router")

    # ── Router → RAG ou SQL ──
    graph.add_conditional_edges(
        "router",
        decide_next_node,
        {
            "RAG": "RAG",
            "SQL": "SQL",
        }
    )

    # ── RAG → response ──
    graph.add_edge("RAG", "response")

    # ── SQL → chart (DASHBOARD) ou response (SQL) ──
    graph.add_conditional_edges(
        "SQL",
        after_sql,
        {
            "chart": "chart",
            "response": "response",
        }
    )

    # ── chart → analysis → response ──
    graph.add_edge("chart", "chart_analysis")
    graph.add_edge("chart_analysis", "response")
    # ── response → END ──
    graph.add_edge("response", END)

    return graph.compile()


odoo_graph = build_graph()
