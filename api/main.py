from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agents.action_agent.tools import create_record, update_record, delete_record, execute_action, send_email
from agents.orchestrator_agent import run_orchestrator

app = FastAPI(title="Odoo AI Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8071"],  # ton Odoo
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str | None = None
    llm_provider: str = "gemini_flash"
    odoo_user_email: str = Field(..., min_length=1)
    odoo_api_key: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    route: str
    answer: str
    sources: list[str] = []
    steps: list[str] = []
    needs_confirmation: bool = False
    confirmation_summary: str = ""
    metadata: dict = {}


# @app.post("/api/chat", response_model=ChatResponse)
# def chat(request: ChatRequest) -> ChatResponse:
#     result = run_orchestrator(
#         question=request.question,
#         session_id=request.session_id,
#         llm_provider=request.llm_provider,
#     )
#     return ChatResponse(**result)


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    import queue
    import threading

    step_queue: queue.Queue = queue.Queue()

    def on_step(step_num: int, message: str) -> None:
        step_queue.put({"type": "step", "step": step_num, "message": message})

    def run_agent() -> None:
        try:
            result = run_orchestrator(
                question=request.question,
                session_id=request.session_id or "default",
                on_step=on_step,
                llm_provider=request.llm_provider,
                odoo_user_email=request.odoo_user_email,
                odoo_api_key=request.odoo_api_key,
            )
            step_queue.put({
                "type": "final",
                "answer": result["answer"],
                "route": result["route"],
                "steps": result["steps"],
                "sources": result.get("sources", []),
                "needs_confirmation": result.get("needs_confirmation", False),
                "confirmation_summary": result.get("confirmation_summary", ""),
                "pending_action": result.get("pending_action"),
            })
        except Exception as exc:
            step_queue.put({
                "type": "error",
                "message": "Une erreur interne s'est produite. Veuillez réessayer.",
            })
        finally:
            step_queue.put(None)

    threading.Thread(target=run_agent, daemon=True).start()

    def generate():
        while True:
            item = step_queue.get()
            if item is None:
                yield "data: [DONE]\n\n"
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


class ConfirmActionRequest(BaseModel):
    confirmed: bool
    pending_action: dict


@app.post("/api/confirm-action")
def confirm_action(request: ConfirmActionRequest):
    if not request.confirmed:
        return {
            "success": False,
            "cancelled": True,
            "message": "Action annulée par l'utilisateur.",
        }

    pending = request.pending_action or {}
    tool_name = pending.get("tool_name")
    tool_args = pending.get("tool_args") or {}

    tools = {
        "create_record": create_record,
        "update_record": update_record,
        "delete_record": delete_record,
        "execute_action": execute_action,
        "send_email": send_email,
    }

    if tool_name not in tools:
        return {
            "success": False,
            "error": f"Action non autorisée ou inconnue: {tool_name}",
        }

    result = tools[tool_name].invoke(tool_args)

    try:
        return json.loads(result)
    except Exception:
        return {
            "success": True,
            "message": result,
        }
