import logging
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from agents.nodes.router_node import router_node
from agents.nodes.rag_node import rag_node
from agents.nodes.sql_generator_node import sql_generator_node
from agents.nodes.sql_executor_node import sql_executor_node
from agents.nodes.response_node import response_node
from agents.nodes.chart_node import chart_node
from agents.nodes.analysis_node import analysis_node
from agents.nodes.action_parser_node import action_parser_node
from agents.nodes.action_confirm_node import action_confirm_node
from agents.nodes.action_executor_node import action_executor_node
from agents.nodes.error_handler_node import error_handler_node

logger = logging.getLogger(__name__)


# ── Helpers de vérification d'erreur ──────────────────────────────


def _has_error(state: AgentState) -> bool:
    return bool(state.get("error"))


# ── Edge functions ────────────────────────────────────────────────


def decide_next_node(state: AgentState) -> str:
    if _has_error(state):
        return "error_handler"
    agent = state.get("agent_used", "RAG")
    logger.info(f"Routing → {agent}")
    if agent in ("SQL", "DASHBOARD"):
        return "sql_generator"
    elif agent == "ACTION":
        return "action_parser"
    return "RAG"


def after_sql_generator(state: AgentState) -> str:
    if _has_error(state):
        return "error_handler"
    return "sql_executor"


def after_sql_executor(state: AgentState) -> str:
    if _has_error(state):
        # Pour ACTION : erreur SQL de résolution → pas bloquant, on continue vers confirm
        if state.get("agent_used") == "ACTION":
            return "action_confirm"
        return "error_handler"
    agent = state.get("agent_used")
    if agent == "DASHBOARD":
        return "chart"
    elif agent == "ACTION":
        return "action_confirm"
    return "response"


def after_rag(state: AgentState) -> str:
    if _has_error(state):
        return "error_handler"
    return "response"


def after_action_parser(state: AgentState) -> str:
    if _has_error(state):
        return "error_handler"
    return "sql_executor"


def after_action_confirm(state: AgentState) -> str:
    if _has_error(state):
        return "error_handler"
    return "response"


def after_chart(state: AgentState) -> str:
    if _has_error(state):
        return "error_handler"
    return "chart_analysis"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # ── Nodes ──
    graph.add_node("router", router_node)
    graph.add_node("RAG", rag_node)
    graph.add_node("sql_generator", sql_generator_node)
    graph.add_node("sql_executor", sql_executor_node)
    graph.add_node("chart", chart_node)
    graph.add_node("chart_analysis", analysis_node)
    graph.add_node("response", response_node)
    graph.add_node("action_parser", action_parser_node)
    graph.add_node("action_confirm", action_confirm_node)
    graph.add_node("action_executor", action_executor_node)
    graph.add_node("error_handler", error_handler_node)

    # ── Entry point ──
    graph.set_entry_point("router")

    # ── Router → RAG | sql_generator | action_parser | error_handler ──
    graph.add_conditional_edges(
        "router",
        decide_next_node,
        {
            "RAG": "RAG",
            "sql_generator": "sql_generator",
            "action_parser": "action_parser",
            "error_handler": "error_handler",
        },
    )

    # ── RAG → response | error_handler ──
    graph.add_conditional_edges(
        "RAG", after_rag, {"response": "response", "error_handler": "error_handler"}
    )

    # ── sql_generator → sql_executor | error_handler ──
    graph.add_conditional_edges(
        "sql_generator",
        after_sql_generator,
        {"sql_executor": "sql_executor", "error_handler": "error_handler"},
    )

    # ── action_parser → sql_executor | error_handler ──
    graph.add_conditional_edges(
        "action_parser",
        after_action_parser,
        {"sql_executor": "sql_executor", "error_handler": "error_handler"},
    )

    # ── sql_executor → chart | action_confirm | response | error_handler ──
    graph.add_conditional_edges(
        "sql_executor",
        after_sql_executor,
        {
            "chart": "chart",
            "action_confirm": "action_confirm",
            "response": "response",
            "error_handler": "error_handler",
        },
    )

    # ── chart → chart_analysis | error_handler ──
    graph.add_conditional_edges(
        "chart",
        after_chart,
        {"chart_analysis": "chart_analysis", "error_handler": "error_handler"},
    )

    # ── chart_analysis → response ──
    graph.add_edge("chart_analysis", "response")

    # ── action_confirm → response | error_handler ──
    graph.add_conditional_edges(
        "action_confirm",
        after_action_confirm,
        {"response": "response", "error_handler": "error_handler"},
    )

    # ── action_executor → response ──
    graph.add_edge("action_executor", "response")

    # ── error_handler → response ──
    graph.add_edge("error_handler", "response")

    # ── response → END ──
    graph.add_edge("response", END)

    return graph.compile()


odoo_graph = build_graph()


# Graph minimal pour exécution après confirmation
def build_executor_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("action_executor", action_executor_node)
    graph.add_node("error_handler", error_handler_node)
    graph.add_node("response", response_node)
    graph.set_entry_point("action_executor")

    def after_executor(state: AgentState) -> str:
        return "error_handler" if _has_error(state) else "response"

    graph.add_conditional_edges(
        "action_executor",
        after_executor,
        {"response": "response", "error_handler": "error_handler"},
    )
    graph.add_edge("error_handler", "response")
    graph.add_edge("response", END)
    return graph.compile()


executor_graph = build_executor_graph()
