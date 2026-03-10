import logging
import requests
from agents.state import AgentState
from config.settings import settings

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """Tu es un expert analyste business Odoo.
Tu reçois des données chiffrées et tu fournis UNIQUEMENT une analyse textuelle.

INTERDIT :
- Générer du code Python, matplotlib, pandas ou tout autre code
- Donner des exemples de code
- Mentionner des bibliothèques

OBLIGATOIRE :
- Analyse en français ou en anglais
- 4 sections : Tendance, Point fort, Point faible, Recommandation
- Utilise des emojis
- Maximum 8 lignes
- Sois direct et actionnable
"""


def analysis_node(state: AgentState) -> AgentState:
    """
    Node Analyse — génère des insights depuis les données du graphique
    """
    question = state["question"]
    sql_result = state.get("sql_result")
    chart_type = state.get("chart_type", "bar")

    logger.info(f"Analysis Node - Question: '{question}'")

    if not sql_result or not sql_result.get("success"):
        return {**state, "answer": state.get("answer", "")}

    data = sql_result.get("results", [])
    if not data:
        return {**state, "answer": state.get("answer", "")}

    # Préparer un résumé des données pour le LLM
    data_summary = _summarize_data(data)

    prompt = f"""Question utilisateur: {question}
Type de graphique: {chart_type}
Données:
{data_summary}

Fournis une analyse business de ces données."""

    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "messages": [
                    {"role": "system", "content": ANALYSIS_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        analysis = response.json()["message"]["content"].strip()

        # Combiner titre graphique + analyse
        chart_title = state.get("answer", "Voici le graphique")
        full_answer = f"{chart_title}\n\n---\n\n### 📊 Analyse\n\n{analysis}"

    except Exception as e:
        logger.error(f"Erreur Analysis Node: {e}")
        full_answer = state.get("answer", "Voici le graphique")

    return {**state, "answer": full_answer}


def _summarize_data(data: list) -> str:
    """Résume les données pour le LLM — max 20 lignes"""
    lines = []
    for row in data[:20]:
        line = " | ".join([
            f"{k}: {v}" for k, v in row.items()
        ])
        lines.append(line)
    return "\n".join(lines)
