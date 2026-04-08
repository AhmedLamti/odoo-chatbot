import os
import uuid
from agents.graph import odoo_graph, executor_graph
from agents.state import AgentState
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from db.conversation_store import ConversationStore
from config.settings import settings

# ── LangSmith (optionnel — actif si LANGCHAIN_API_KEY renseigné dans .env) ──
if settings.langchain_api_key:
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_TRACING_V2"] = settings.langchain_tracing_v2
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project

app = FastAPI(
    title="Odoo Chatbot API",
    description="API pour le chatbot Odoo avec agents RAG, SQL, DASHBOARD et ACTION",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = ConversationStore()

# ── Store en mémoire pour les actions en attente de confirmation ──
# key: session_id → value: AgentState complet (action_type, action_resolved, ...)
pending_actions: dict[str, AgentState] = {}


class QuestionRequest(BaseModel):
    question: str
    session_id: str | None = None


class ConfirmRequest(BaseModel):
    session_id: str


class ChatResponse(BaseModel):
    answer: str
    agent_used: str
    session_id: str
    sql_query: str | None = None
    sources: list | None = None
    chart_html: str | None = None
    chart_data: str | None = None
    needs_confirmation: bool = False  # ← frontend affiche boutons CONFIRMER/ANNULER


@app.get("/")
def root():
    return {"name": "Odoo Chatbot API", "version": "2.0.0", "status": "running"}


@app.get("/health")
def health():
    from db.sql_connector import SQLConnector
    from db.vector_store import VectorStoreManager

    db_ok = SQLConnector().test_connection()
    qdrant_info = VectorStoreManager().get_collection_info()
    return {
        "status": "ok",
        "postgres": "connected" if db_ok else "error",
        "qdrant": {
            "status": qdrant_info["status"],
            "vectors_count": qdrant_info["vectors_count"],
        },
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: QuestionRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question vide")

    session_id = request.session_id or str(uuid.uuid4())
    question = request.question.strip()

    # ── Détecter CONFIRMER / ANNULER ──
    if (
        question.upper() in ("CONFIRMER", "CONFIRM", "OUI", "YES")
        and session_id in pending_actions
    ):
        return _execute_confirmed_action(session_id)

    if (
        question.upper() in ("ANNULER", "CANCEL", "NON", "NO")
        and session_id in pending_actions
    ):
        pending_actions.pop(session_id, None)
        return ChatResponse(
            answer="❌ Action annulée.",
            agent_used="ACTION",
            session_id=session_id,
            needs_confirmation=False,
        )

    # ── Flow normal ──
    try:
        initial_state: AgentState = {
            "question": question,
            "session_id": session_id,
            "agent_used": None,
            "sql_query": None,
            "sql_result": None,
            "sources": None,
            "context_used": None,
            "chart_html": None,
            "chart_type": None,
            "action_type": None,
            "action_params": None,
            "action_resolved": None,
            "action_result": None,
            "needs_confirmation": False,
            "confirmation_summary": None,
            "prediction": None,
            "answer": None,
            "error": None,
            "messages": [],
        }

        final_state = odoo_graph.invoke(initial_state)

        # ── Si action en attente → sauvegarder le state pour /confirm ──
        if final_state.get("needs_confirmation"):
            pending_actions[session_id] = final_state

        return ChatResponse(
            answer=final_state["answer"],
            agent_used=final_state["agent_used"],
            session_id=session_id,
            sql_query=final_state.get("sql_query"),
            sources=final_state.get("sources"),
            chart_data=final_state.get("chart_html"),
            needs_confirmation=final_state.get("needs_confirmation", False),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/confirm", response_model=ChatResponse)
def confirm_action(request: ConfirmRequest):
    """Endpoint dédié pour confirmer une action depuis la bulle flottante"""
    session_id = request.session_id
    if session_id not in pending_actions:
        raise HTTPException(
            status_code=404, detail="Aucune action en attente pour cette session"
        )
    return _execute_confirmed_action(session_id)


@app.post("/cancel", response_model=ChatResponse)
def cancel_action(request: ConfirmRequest):
    """Endpoint dédié pour annuler une action depuis la bulle flottante"""
    session_id = request.session_id
    pending_actions.pop(session_id, None)
    return ChatResponse(
        answer="❌ Action annulée.",
        agent_used="ACTION",
        session_id=session_id,
        needs_confirmation=False,
    )


def _execute_confirmed_action(session_id: str) -> ChatResponse:
    """Exécute l'action confirmée via executor_graph"""
    saved_state = pending_actions.pop(session_id)
    try:
        final_state = executor_graph.invoke(saved_state)
        return ChatResponse(
            answer=final_state["answer"],
            agent_used="ACTION",
            session_id=session_id,
            needs_confirmation=False,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/{session_id}")
def get_history(session_id: str):
    history = store.get_history(session_id)
    return {"session_id": session_id, "messages": history, "count": len(history)}


@app.delete("/history/{session_id}")
def clear_history(session_id: str):
    store.clear(session_id)
    pending_actions.pop(session_id, None)
    return {"message": f"Historique {session_id} supprimé"}


@app.get("/sessions")
def list_sessions():
    sessions = store.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/sql/schema")
def get_schema():
    from db.schema_cache import SchemaCache

    cache = SchemaCache()
    schema = cache.load()
    return {"tables": list(schema.keys()), "count": len(schema)}
