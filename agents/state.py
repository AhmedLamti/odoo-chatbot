from typing import TypedDict, Optional, List, Dict, Any


class AgentState(TypedDict):
    """
    State partagé entre tous les agents du graph
    """

    # Input
    question: str
    session_id: Optional[str]

    # Routing
    agent_used: Optional[str]  # RAG, SQL, DASHBOARD, ACTION

    # SQL Agent — données métier (lecture)
    sql_query: Optional[str]  # SQL généré par sql_generator_node
    sql_result: Optional[Dict[str, Any]]  # résultat exécuté par sql_executor_node

    # RAG Agent
    sources: Optional[List[Dict]]
    context_used: Optional[str]

    # Dashboard Agent (Phase 3)
    chart_html: Optional[str]
    chart_type: Optional[str]
    analysis: Optional[str]

    # Action Agent (Phase 5) — résolution IDs
    action_type: Optional[str]  # create_sale_order, validate_invoice, ...
    action_params: Optional[Dict[str, Any]]  # paramètres extraits par action_parser
    action_sql_query: Optional[
        str
    ]  # SQL de résolution IDs (action_parser → sql_executor)
    action_sql_result: Optional[
        Dict[str, Any]
    ]  # résultat résolution (sql_executor → action_confirm)
    action_result: Optional[Dict[str, Any]]  # résultat XML-RPC final

    # Confirmation (Phase 5)
    needs_confirmation: Optional[bool]  # True = attendre confirmation utilisateur
    confirmation_summary: Optional[str]  # résumé affiché avant exécution

    # ML Agent (Phase 4)
    prediction: Optional[Dict[str, Any]]

    # Response
    answer: Optional[str]
    error: Optional[str]  # message d'erreur si exception
    error_origin: Optional[str]  # nom du node qui a levé l'erreur

    # Conversation
    messages: Optional[List[Dict]]
