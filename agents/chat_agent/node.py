from __future__ import annotations

from Graph.state import OrchestratorState
from agents.chat_agent.prompts import SYSTEM_PROMPT
from shared.llm_factory import get_llm, LLMProvider
from shared.utils import get_logger

logger = get_logger(__name__)

_llm = get_llm(LLMProvider.GROQ_LLAMA33)


def chat_node(state: OrchestratorState) -> dict:
    question = state["question"]
    logger.info(f"[chat_node] '{question[:60]}'")

    response = _llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ])
    return {
        "answer": response.content.strip(),
        "metadata": {"handled_by": "chat_agent"},
    }
