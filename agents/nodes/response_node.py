import logging
from agents.state import AgentState
from db.conversation_store import ConversationStore

logger = logging.getLogger(__name__)


def response_node(state: AgentState) -> AgentState:
    """
    Node final — sauvegarde l'historique et finalise la réponse
    """
    session_id = state.get("session_id")
    question = state.get("question", "")
    answer = state.get("answer", "")

    # Sauvegarder dans l'historique
    if session_id and question and answer:
        store = ConversationStore()
        store.add_message(session_id, "user", question)
        store.add_message(session_id, "assistant", answer)
        logger.info(f"Historique sauvegardé pour session: {session_id}")

    return state
