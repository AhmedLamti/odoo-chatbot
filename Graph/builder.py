from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from Graph.routers import route_selector
from Graph.state import OrchestratorState

# from shared.checkpointer import get_checkpointer

# Noms de nœuds
NODE_ORCHESTRATOR = "orchestrator"
NODE_RAG = "rag"
NODE_DATA = "data"
NODE_ACTION = "action"
NODE_CHAT = "chat"


def build_graph():
    """Construit, compile et retourne le graphe orchestrateur."""
    # Import local des nodes pour éviter les cycles
    from agents.orchestrator_agent.node import orchestrator_node
    from agents.rag_agent.agent import run_rag_agent
    from agents.data_agent.agent import run_data_agent
    from agents.chat_agent.node import chat_node
    from agents.action_agent.node import action_agent_node
    builder = StateGraph(OrchestratorState)

    builder.add_node(NODE_ORCHESTRATOR, orchestrator_node)
    builder.add_node(NODE_RAG, run_rag_agent)
    builder.add_node(NODE_DATA, run_data_agent)
    builder.add_node(NODE_CHAT, chat_node)
    builder.add_node(NODE_ACTION, action_agent_node)

    builder.add_edge(START, NODE_ORCHESTRATOR)

    builder.add_conditional_edges(
        NODE_ORCHESTRATOR,
        route_selector,
        {
            NODE_RAG: NODE_RAG,
            NODE_DATA: NODE_DATA,
            NODE_ACTION: NODE_ACTION,
            NODE_CHAT: NODE_CHAT,
        },
    )

    for node in (NODE_RAG, NODE_DATA, NODE_ACTION, NODE_CHAT):
        builder.add_edge(node, END)

    return builder.compile()


# Singleton compilé une seule fois au démarrage
orchestrator_graph = build_graph()
