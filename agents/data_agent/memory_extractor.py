"""
Extrait un AgentMemory structuré depuis la trace de messages d'une exécution réussie.
Utilise le LLM pour résumer la question et identifier le pattern.
"""

import json
import logging
import re
from typing import Optional

from langchain_core.messages import BaseMessage, ToolMessage, AIMessage

from agents.data_agent.memory_store import AgentMemory
from tools.groq_client import call_groq

logger = logging.getLogger(__name__)

EXTRACTOR_SYSTEM = """Tu analyses une trace d'exécution d'un agent Odoo.
Extrais les informations clés et réponds UNIQUEMENT avec un JSON valide.

JSON attendu :
{
  "question_summary": "résumé en 1 phrase de la question posée",
  "question_type": "count_records | list_records | aggregate | chart | other",
  "odoo_model": "nom technique du modèle principal ex: res.partner",
  "domain_used": "domain Odoo utilisé ex: [('customer_rank', '>', 0)]",
  "tools_sequence": ["outil1", "outil2"],
  "final_answer_pattern": "pattern de réponse avec {placeholders} pour les valeurs dynamiques",
  "error_avoided": "description d'une erreur commise et corrigée, ou null"
}

Si le domaine n'est pas identifiable, mets "[]".
"""


def extract_memory(
        question: str,
        messages: list[BaseMessage],
) -> Optional[AgentMemory]:
    """
    Extrait un AgentMemory depuis les messages d'une exécution réussie.
    Retourne None si l'extraction échoue.
    """
    # Construire le résumé de trace pour le LLM extracteur
    trace_lines = [f"Question originale: {question}\n"]

    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                trace_lines.append(f"Outil appelé: {tc['name']}({json.dumps(tc['args'])[:120]})")
        elif isinstance(msg, ToolMessage):
            content_preview = str(msg.content)[:200]
            trace_lines.append(f"Résultat outil [{msg.name}]: {content_preview}")
        elif isinstance(msg, AIMessage) and msg.content:
            trace_lines.append(f"Réponse finale: {msg.content[:300]}")

    trace_text = "\n".join(trace_lines)

    try:
        # raw = call_cerebras(
        #     prompt=f"Trace à analyser:\n{trace_text}\n\nJSON:",
        #     system=EXTRACTOR_SYSTEM,
        #     max_tokens=400,
        #     temperature=0,
        # )
        raw = call_groq(  # ← au lieu de call_cerebras
            prompt=f"Trace à analyser:\n{trace_text}\n\nJSON:",
            system=EXTRACTOR_SYSTEM,
            max_tokens=400,
            temperature=0,
        )
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw).strip()
        data = json.loads(raw)

        return AgentMemory(
            question_summary=data.get("question_summary", question[:80]),
            question_type=data.get("question_type", "other"),
            odoo_model=data.get("odoo_model", "unknown"),
            domain_used=data.get("domain_used", "[]"),
            tools_sequence=data.get("tools_sequence", []),
            final_answer_pattern=data.get("final_answer_pattern", ""),
            error_avoided=data.get("error_avoided"),
        )

    except Exception as e:
        logger.warning(f"Extraction mémoire échouée: {e}")
        return None
