import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.orchestrator import Orchestrator
from db.conversation_store import ConversationStore

app = FastAPI(
    title="Odoo Chatbot API",
    description="API pour le chatbot Odoo avec agents RAG et SQL",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orchestrator = Orchestrator()
store = ConversationStore()


class QuestionRequest(BaseModel):
    question: str
    session_id: str | None = None  # optionnel


class ChatResponse(BaseModel):
    answer: str
    agent_used: str
    session_id: str
    sql_query: str | None = None
    sources: list | None = None


@app.get("/")
def root():
    return {"name": "Odoo Chatbot API", "version": "1.0.0", "status": "running"}


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
    """Endpoint principal avec gestion de session"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La question ne peut pas être vide")

    # Créer une session si pas fournie
    session_id = request.session_id or str(uuid.uuid4())

    try:
        result = orchestrator.run(request.question, session_id=session_id)
        return ChatResponse(
            answer=result["answer"],
            agent_used=result["agent_used"],
            session_id=session_id,
            sql_query=result.get("sql_query"),
            sources=result.get("sources"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/history/{session_id}")
def get_history(session_id: str):
    """Retourne l'historique d'une session"""
    history = store.get_history(session_id)
    return {"session_id": session_id, "messages": history, "count": len(history)}


@app.delete("/history/{session_id}")
def clear_history(session_id: str):
    """Supprime l'historique d'une session"""
    store.clear(session_id)
    return {"message": f"Historique {session_id} supprimé"}


@app.get("/sessions")
def list_sessions():
    """Liste toutes les sessions actives"""
    sessions = store.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/sql/schema")
def get_schema():
    from db.schema_cache import SchemaCache
    cache = SchemaCache()
    schema = cache.load()
    return {"tables": list(schema.keys()), "count": len(schema)}
