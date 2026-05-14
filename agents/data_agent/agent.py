"""
Data Agent avec mémoire sémantique persistante et affichage des étapes de raisonnement.

Cycle de vie :
1. Nouvelle question → recherche des souvenirs pertinents dans Qdrant
2. Souvenirs injectés dans le system prompt comme exemples
3. Agent ReAct stream ses étapes en temps réel :
   - Étape 0  : résultat de la recherche mémorielle
   - Étape N  : appel d'outil (nom lisible + paramètres résumés)
   - Étape N+1: résultat de cet outil
   - Étape fin: formulation de la réponse finale
4. Si succès → extraction d'un nouveau souvenir → sauvegarde dans Qdrant
"""

import json
import logging
from typing import Callable

from langchain_core.messages import AIMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from agents.data_agent.memory_extractor import extract_memory
from agents.data_agent.memory_store import MemoryStore
from agents.data_agent.tools import (
    generate_chart,
    get_model_for_concept,
    odoo_fields_get,
    odoo_read_group,
    odoo_search_count,
    odoo_search_read,
)

logger = logging.getLogger(__name__)

# ── Prompt ─────────────────────────────────────────────────────────────────────

BASE_SYSTEM_PROMPT = """Tu es un agent expert Odoo 16 qui répond aux questions
sur les données de l'entreprise en utilisant les outils disponibles.

Tu as accès aux outils suivants:
- get_model_for_concept : trouve le nom technique d'un modèle Odoo
- odoo_fields_get       : liste les champs d'un modèle
- odoo_search_count     : compte des enregistrements (utilise pour 'combien de X ?')
- odoo_search_read      : récupère des enregistrements depuis Odoo
- odoo_read_group       : regroupe et agrège des données (prend un string JSON en entrée)
- generate_chart        : génère un graphique (uniquement si demandé explicitement)

Contraintes Odoo 16:
- is_customer et is_supplier n'existent plus → customer_rank > 0 et supplier_rank > 0
- res.partner contient clients, fournisseurs ET contacts — toujours filtrer par rank
- Le domain doit toujours être passé comme string Python entre guillemets
- La sortie de odoo_search_read est un string JSON

Réponds dans la même langue que la question.
Si les données sont vides, dis-le clairement.
"""

# ── Libellés lisibles des outils ──────────────────────────────────────────────

TOOL_LABELS: dict[str, str] = {
    "get_model_for_concept": "Identification du modèle Odoo",
    "odoo_fields_get": "Récupération des champs disponibles",
    "odoo_search_count": "Comptage des enregistrements",
    "odoo_search_read": "Lecture des données",
    "odoo_read_group": "Agrégation et regroupement",
    "generate_chart": "Génération du graphique",
}

# ── Mots-clés indiquant une exécution en erreur ────────────────────────────────

_ERROR_KEYWORDS = [
    "erreur", "error", "exception", "impossible",
    "n'existe pas", "not found", "introuvable",
    "invalid", "invalide", "failed", "échec",
]

# ── Singletons ─────────────────────────────────────────────────────────────────

TOOLS = [
    get_model_for_concept,
    odoo_fields_get,
    odoo_search_count,
    odoo_search_read,
    odoo_read_group,
    generate_chart,
]

_short_term_memory = MemorySaver()
_memory_store = MemoryStore()
_llm = ChatGroq(model="meta-llama/llama-4-scout-17b-16e-instruct", temperature=0)


# ── Construction de l'agent ────────────────────────────────────────────────────

def _build_agent(extra_context: str):
    system = BASE_SYSTEM_PROMPT + extra_context
    return create_react_agent(
        model=_llm,
        tools=TOOLS,
        prompt=system,
        checkpointer=_short_term_memory,
    )


# ── Formateurs d'étapes ────────────────────────────────────────────────────────

def _format_tool_args(tool_name: str, args: dict) -> str:
    """Résume les arguments d'un appel d'outil en une ligne lisible."""
    if tool_name == "odoo_search_count":
        return f"modèle={args.get('model', '?')}  domain={args.get('domain', '[]')}"

    if tool_name == "odoo_search_read":
        fields = args.get("fields", [])
        return (
            f"modèle={args.get('model', '?')}  "
            f"domain={args.get('domain', '[]')}  "
            f"champs={fields[:4]}{'...' if len(fields) > 4 else ''}"
        )

    if tool_name == "odoo_read_group":
        try:
            params = json.loads(args.get("params_json", "{}"))
            return (
                f"modèle={params.get('model', '?')}  "
                f"groupby={params.get('groupby', [])}  "
                f"fields={params.get('fields', [])[:3]}"
            )
        except Exception:
            return str(args)[:80]

    if tool_name == "odoo_fields_get":
        return f"modèle={args.get('model', '?')}"

    if tool_name == "get_model_for_concept":
        return f"concept='{args.get('concept', '?')}'"

    if tool_name == "generate_chart":
        return f"type={args.get('chart_type', '?')}  titre='{args.get('title', '?')}'"

    return "  ".join(f"{k}={str(v)[:40]}" for k, v in args.items())


def _format_tool_result(tool_name: str, content: str) -> str:
    """Résume le résultat d'un outil en une ligne lisible."""
    try:
        data = json.loads(content)
        if isinstance(data, int):
            return str(data)
        if isinstance(data, list):
            return f"{len(data)} enregistrement(s) retourné(s)"
        if isinstance(data, dict):
            return str(data)[:100]
    except Exception:
        pass
    result = content.strip()
    return result[:120] + ("..." if len(result) > 120 else "")


# ── Type du callback de progression ───────────────────────────────────────────
# Signature : (numéro_étape: int, message: str) -> None
StepCallback = Callable[[int, str], None]


def _default_step_callback(step: int, message: str) -> None:
    """Affichage console — remplacé par un callback SSE/WebSocket en prod."""
    print(f"  Étape {step} — {message}")


# ── Point d'entrée principal ───────────────────────────────────────────────────

def run_data_agent(state: dict) -> dict:
    """
    Exécute le data agent — appelé par LangGraph comme node.
    """
    question = state["question"]
    thread_id = state.get("session_id", "1")
    on_step = state.get("on_step", None)

    callback = on_step or _default_step_callback
    logger.info(f"[data_agent] question='{question[:80]}' thread={thread_id}")

    # ── Étape 0 : mémoire ─────────────────────────────────────────────────────
    relevant_memories = _memory_store.search(question, top_k=3)
    memory_context = _memory_store.format_for_prompt(relevant_memories)

    if relevant_memories:
        mem_msg = (
                f"Mémoire : {len(relevant_memories)} expérience(s) similaire(s) trouvée(s) — "
                + ", ".join(f"« {m.question_summary[:35]} »" for m in relevant_memories)
        )
    else:
        mem_msg = "Mémoire : aucune expérience similaire — démarrage à froid"

    callback(0, mem_msg)

    # ── Construction et streaming ──────────────────────────────────────────────
    agent = _build_agent(memory_context)
    config = {"configurable": {"thread_id": thread_id}}
    all_messages: list = []
    steps: list[str] = [mem_msg]
    step_number = 1

    for event in agent.stream(
            {"messages": [("user", question)]},
            config=config,
            stream_mode="updates",  # un événement par nœud du graph LangGraph
    ):
        for _node_name, node_output in event.items():
            for msg in node_output.get("messages", []):
                all_messages.append(msg)

                # ── LLM appelle un ou plusieurs outils ────────────────────────
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        tool_name = tc["name"]
                        label = TOOL_LABELS.get(tool_name, tool_name)
                        args_line = _format_tool_args(tool_name, tc.get("args", {}))
                        step_msg = f"{label}  ({args_line})"
                        steps.append(step_msg)
                        callback(step_number, step_msg)
                        step_number += 1

                # ── Résultat d'outil ──────────────────────────────────────────
                elif isinstance(msg, ToolMessage):
                    result_line = _format_tool_result(msg.name, str(msg.content))
                    step_msg = f"→ Résultat : {result_line}"
                    steps.append(step_msg)
                    callback(step_number, step_msg)
                    step_number += 1

                # ── Réponse finale (aucun tool_call) ──────────────────────────
                elif isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                    step_msg = "Formulation de la réponse finale"
                    steps.append(step_msg)
                    callback(step_number, step_msg)
                    step_number += 1

    answer = all_messages[-1].content if all_messages else ""

    # ── Sauvegarde mémorielle (best-effort) ────────────────────────────────────
    _try_save_memory(question, all_messages, answer)

    return {
        "answer": answer,
        "steps": steps,  # ← déjà présent, garde-le
        "metadata": {"handled_by": "data_agent"},
    }


# ── Gestion mémoire ────────────────────────────────────────────────────────────

def _is_failed_execution(messages: list, answer: str) -> bool:
    if any(kw in answer.lower() for kw in _ERROR_KEYWORDS):
        return True
    for msg in messages:
        if isinstance(msg, ToolMessage):
            if any(kw in str(msg.content).lower() for kw in ["error", "erreur", "traceback", "exception"]):
                return True
    return False


def _try_save_memory(question: str, messages: list, answer: str) -> None:
    if not answer or len(answer) < 20:
        return
    if _is_failed_execution(messages, answer):
        logger.info("[memory] Erreur détectée — souvenir non sauvegardé")
        return
    try:
        memory = extract_memory(question, messages)
        if memory:
            saved = _memory_store.save(memory)
            logger.info(f"[memory] {'Sauvegardé' if saved else 'Doublon ignoré'} : '{memory.question_summary[:60]}'")
    except Exception as e:
        logger.warning(f"[memory] Sauvegarde échouée (non bloquant) : {e}")
