from typing import TypedDict, Optional, List, Dict, Any


class AgentState(TypedDict):
    """
    State partagé entre tous les agents du graph
    """
    # Input
    question: str
    session_id: Optional[str]

    # Routing
    agent_used: Optional[str]          # RAG, SQL, DASHBOARD

    # SQL Agent
    sql_query: Optional[str]
    sql_result: Optional[Dict[str, Any]]

    # RAG Agent
    sources: Optional[List[Dict]]
    context_used: Optional[str]

    # Dashboard Agent (Phase 3)
    chart_html: Optional[str]
    chart_type: Optional[str]
    analysis: Optional[str]

    # ML Agent (Phase 4)
    prediction: Optional[Dict[str, Any]]

    # Response
    answer: Optional[str]
    error: Optional[str]

    # Conversation
    messages: Optional[List[Dict]]
