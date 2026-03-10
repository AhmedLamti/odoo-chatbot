from agents.state import AgentState
from tools.chart_generator import ChartGenerator
import logging
import requests
from config.settings import settings

logger = logging.getLogger(__name__)

CHART_CONFIG_PROMPT = """You are a data visualization expert.
Given a question and SQL results, determine the best chart configuration.

Respond ONLY with valid JSON:
{
  "chart_type": "bar|line|pie|scatter",
  "title": "Chart title",
  "x_label": "X axis label",
  "y_label": "Y axis label"
}

RULES:
- bar   → comparisons, rankings, categories
- line  → time series, trends, evolution
- pie   → proportions, distributions
- scatter → correlations

EXAMPLES:
Q: Top produits vendus
{"title": "Top 10 produits vendus", "x_label": "Produit", "y_label": "Quantité"}

Q: Répartition clients par pays
{"chart_type": "pie", "title": "Répartition clients par pays", "x_label": "", "y_label": ""}

Q: Ventes par mois
{"chart_type": "line", "title": "Évolution des ventes par mois", "x_label": "Mois", "y_label": "CA (€)"}

Q: Top produits vendus
{  "chart_type": "bar",
  "title": "Top 10 produits vendus",
  "x_label": "Produit",
  "y_label": "Quantité"
}
"""


def chart_node(state: AgentState) -> AgentState:
    """
    Node Chart — reçoit les données SQL et génère le graphique
    """
    question = state["question"]
    sql_result = state.get("sql_result")

    logger.info(f"Chart Node - Question: '{question}'")

    # Pas de données SQL → pas de graphique
    if not sql_result or not sql_result.get("success"):
        return {**state, "chart_html": None}

    data = sql_result.get("results", [])
    if not data:
        return {**state, "chart_html": None}

    # Demander au LLM juste la config du graphique
    try:
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_llm_model,
                "messages": [
                    {"role": "system", "content": CHART_CONFIG_PROMPT},
                    {
                        "role": "user",
                        "content": f"Question: {question}\nColumns: {list(data[0].keys())}",
                    },
                ],
                "stream": False,
            },
            timeout=60,
        )
        response.raise_for_status()
        raw = response.json()["message"]["content"].strip()
        config = _extract_json(raw)

    except Exception as e:
        logger.error(f"Erreur config graphique: {e}")
        # Fallback config
        config = {
            "chart_type": "bar",
            "title": question,
            "x_label": "",
            "y_label": "",
        }

    # Générer le graphique
    chart_gen = ChartGenerator()
    chart_data = chart_gen.generate_json(
        chart_type=config.get("chart_type", "bar"),
        data=data,
        title=config.get("title", question),
        x_label=config.get("x_label", ""),
        y_label=config.get("y_label", ""),
    )

    return {
        **state,
        "chart_html": chart_data,
        "chart_type": config.get("chart_type", "bar"),
    }


def _extract_json(raw: str) -> dict:
    import json, re

    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(raw)
