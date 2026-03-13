import logging
import json
import re
from agents.state import AgentState
from tools.groq_client import call_groq
from tools.chart_generator import ChartGenerator
from config.few_shot_examples import DASHBOARD_FEW_SHOT_EXAMPLES

logger = logging.getLogger(__name__)

CHART_SYSTEM = f"""You are a data visualization expert for Odoo 16.
Given a question and available columns, return chart configuration.

{DASHBOARD_FEW_SHOT_EXAMPLES}

RULES:
- "line" for time series, trends, evolution over months
- "bar" for comparisons, rankings, top N
- "pie" for distributions, proportions
- "scatter" for correlations between 2 numeric values
- x_column and y_column MUST be exact column names from the list provided
- title in same language as question

Return ONLY valid JSON:
{{"chart_type": "bar|line|pie|scatter", "x_column": "col", "y_column": "col", "title": "..."}}
"""


def chart_node(state: AgentState) -> AgentState:
    question = state["question"]
    sql_result = state.get("sql_result")
    logger.info(f"Chart Node - Question: '{question}'")

    if not sql_result or not sql_result.get("success"):
        return {**state, "chart_html": None}

    data = sql_result.get("results", [])
    if not data:
        return {**state, "chart_html": None}

    columns = list(data[0].keys())
    logger.info(f"Colonnes: {columns}")

    try:
        raw = call_groq(
            prompt=f"Question: {question}\nAvailable columns: {columns}",
            system=CHART_SYSTEM,
            max_tokens=150,
            temperature=0,
        )
        config = _extract_json(raw)
        logger.info(f"Chart config: {config}")
    except Exception as e:
        logger.error(f"Erreur chart config: {e}")
        config = _fallback_config(question, columns)

    chart_gen = ChartGenerator()
    chart_data = chart_gen.generate_json(
        chart_type=config.get("chart_type", "bar"),
        data=data,
        title=config.get("title", question),
        x_label=config.get("x_column", columns[0] if columns else ""),
        y_label=config.get("y_column", columns[1] if len(columns) > 1 else ""),
    )

    return {
        **state,
        "chart_html": chart_data,
        "chart_type": config.get("chart_type", "bar"),
    }


def _fallback_config(question: str, columns: list) -> dict:
    q = question.lower()
    if any(w in q for w in ["courbe", "évolution", "mois", "tendance", "line"]):
        chart_type = "line"
    elif any(w in q for w in ["répartition", "proportion", "pie"]):
        chart_type = "pie"
    else:
        chart_type = "bar"
    return {
        "chart_type": chart_type,
        "x_column": columns[0] if columns else "x",
        "y_column": columns[1] if len(columns) > 1 else columns[0],
        "title": question,
    }


def _extract_json(raw: str) -> dict:
    raw = re.sub(r"```json\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(raw)
