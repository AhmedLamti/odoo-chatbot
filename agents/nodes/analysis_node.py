import logging
from agents.state import AgentState
from tools.groq_client import call_groq

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM = """Tu es un expert analyste business Odoo.
Fournis UNIQUEMENT une analyse textuelle des données.

INTERDIT: code Python, matplotlib, pandas, SQL, bibliothèques
OBLIGATOIRE:
- Même langue que la question (français ou anglais)
- 4 sections: Tendance, Point fort, Point faible, Recommandation
- Emojis pour chaque section
- Maximum 8 lignes
- Chiffres réels des données
- Direct et actionnable
"""


def analysis_node(state: AgentState) -> AgentState:
    question = state["question"]
    sql_result = state.get("sql_result")
    chart_type = state.get("chart_type", "bar")
    logger.info(f"Analysis Node - Question: '{question}'")

    if not sql_result or not sql_result.get("success"):
        return {**state, "answer": state.get("answer", "")}

    data = sql_result.get("results", [])
    if not data:
        return {**state, "answer": state.get("answer", "")}

    data_summary = _summarize(data)

    try:
        analysis = call_groq(
            prompt=f"Question: {question}\nChart: {chart_type}\nData:\n{data_summary}",
            system=ANALYSIS_SYSTEM,
            max_tokens=400,
            temperature=0.1,
        )
        chart_title = state.get("answer", "Voici le graphique")
        full_answer = f"{chart_title}\n\n---\n\n### 📊 Analyse\n\n{analysis}"
    except Exception as e:
        logger.error(f"Erreur Analysis: {e}")
        full_answer = state.get("answer", "Voici le graphique")

    return {**state, "answer": full_answer}


def _summarize(data: list) -> str:
    return "\n".join([
        " | ".join([f"{k}: {v}" for k, v in row.items()])
        for row in data[:20]
    ])
