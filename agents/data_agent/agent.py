import json
import logging
from typing import Callable

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from agents.data_agent.memory_extractor import extract_memory
from agents.data_agent.memory_store import MemoryStore
from agents.data_agent.tools import (
    format_response,
    generate_chart,
    # get_schema_for_question,
    plan_query,
    # get_model_for_concept,
    # odoo_fields_get,
    odoo_read_group,
    odoo_search_count,
    odoo_search_read,
    search_similar_models,
    select_models,
    #get_models_schema,
)
from shared.llm_factory import get_llm, LLMProvider

logger = logging.getLogger(__name__)

# ── Prompt ─────────────────────────────────────────────────────────────────────

BASE_SYSTEM_PROMPT = """Tu es un agent expert Odoo 16 qui répond aux questions
sur les données de l'entreprise en utilisant les outils disponibles.

Outils disponibles :
- search_similar_models : utilise cet outil quand tu as besoin d'identifier 
  les modèles et les champs Odoo sont concernés par la question.
- select_models : utilise cet outil pour affiner les candidats retournés par 
  search_similar_models et ne garder que les modèles vraiment utiles.
- plan_query : utilise cet outil quand la question nécessite plusieurs appels 
  Odoo enchaînés ou des jointures entre modèles
- odoo_search_count : utilise cet outil quand tu dois compter des enregistrements
- odoo_search_read : utilise cet outil quand tu dois récupérer des enregistrements
- odoo_read_group : utilise cet outil quand tu dois agréger ou regrouper des données
- generate_chart : utilise cet outil uniquement si l'utilisateur demande explicitement 
  une visualisation
- format_response : utilise cet outil comme DERNIÈRE étape obligatoire avant de répondre.
  Passe raw_answer=<ta réponse brute> et question=<la question originale de l'utilisateur>.
  Ne génère JAMAIS de réponse finale sans passer par cet outil.

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
    "search_similar_models": "Recherche des modèles et champs similaires",
    "select_models": "Rerourne le schema des modèles pertinents",
    "plan_query": "Planification de l'ordre d'execution des requetes",
    "odoo_search_count": "Comptage des enregistrements",
    "odoo_search_read": "Lecture des données",
    "odoo_read_group": "Agrégation et regroupement",
    "generate_chart": "Génération du graphique",
    "format_response": "Formulation de la réponse finale",
}

# ── Mots-clés indiquant une exécution en erreur ────────────────────────────────

_ERROR_KEYWORDS = [
    "erreur",
    "error",
    "exception",
    "impossible",
    "n'existe pas",
    "not found",
    "introuvable",
    "invalid",
    "invalide",
    "failed",
    "échec",
]

# ── Singletons ─────────────────────────────────────────────────────────────────

TOOLS = [
    search_similar_models,
    select_models,
    #get_models_schema,
    plan_query,
    odoo_search_count,
    odoo_search_read,
    odoo_read_group,
    generate_chart,
    format_response,
]

_short_term_memory = MemorySaver()
_memory_store = MemoryStore()
_llm = get_llm(LLMProvider.GEMINI_FLASH)


# ── Construction de l'agent ────────────────────────────────────────────────────


def _build_agent(extra_context: str, llm):
    system = BASE_SYSTEM_PROMPT + extra_context
    return create_react_agent(
        model=llm,
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
    provider = state.get("llm_provider", None)
    llm = get_llm(provider) if provider else _llm
    odoo_user_email = state.get("odoo_user_email")
    odoo_api_key = state.get("odoo_api_key")

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
    credentials_context = f"""

    Credentials Odoo du user connecté :
    - odoo_user_email = {json.dumps(odoo_user_email)}
    - odoo_api_key = {json.dumps(odoo_api_key)}

    RÈGLE OBLIGATOIRE :
    Pour chaque appel aux outils suivants :
    - odoo_search_count
    - odoo_search_read
    - odoo_read_group

    tu dois TOUJOURS inclure :
    - odoo_user_email
    - odoo_api_key

    Exemple :
    odoo_search_read(
      model="sale.order",
      domain="[]",
      fields=["id", "name"],
      limit=10,
      odoo_user_email={json.dumps(odoo_user_email)},
      odoo_api_key={json.dumps(odoo_api_key)}
    )
    """

    agent = _build_agent(memory_context + credentials_context, llm=llm)
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
    if not isinstance(answer, str):
        answer = json.dumps(answer, ensure_ascii=False, default=str)

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
            if any(
                kw in str(msg.content).lower()
                for kw in ["error", "erreur", "traceback", "exception"]
            ):
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
            logger.info(
                f"[memory] {'Sauvegardé' if saved else 'Doublon ignoré'} : '{memory.question_summary[:60]}'"
            )
    except Exception as e:
        logger.warning(f"[memory] Sauvegarde échouée (non bloquant) : {e}")
