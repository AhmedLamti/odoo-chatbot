import logging
import requests
import re
from agents.state import AgentState
from tools.schema_selector import SchemaSelector
from tools.sql_executor import SQLExecutor
from tools.chart_generator import ChartGenerator
from config.settings import settings

logger = logging.getLogger(__name__)

DASHBOARD_SYSTEM_PROMPT = """You are an expert Odoo 16 data analyst.
You generate PostgreSQL queries AND specify chart configuration.

Respond ONLY with valid JSON in this exact format:
{
  "sql": "SELECT ...",
  "chart_type": "bar|line|pie|scatter",
  "title": "Chart title",
  "x_label": "X axis label",
  "y_label": "Y axis label"
}

CHART TYPE RULES:
- bar   → comparisons, rankings, categories
- line  → time series, evolution, trends
- pie   → proportions, distributions, percentages
- scatter → correlations between 2 numeric values

SQL RULES for Odoo 16:
- NEVER use account_invoice → use account_move
- Customers: res_partner WHERE customer_rank > 0
- Employees: hr_employee WHERE active = TRUE
- Products: product_template WHERE active = TRUE
- Revenue: sale_order WHERE state IN ('sale','done')
- Always LIMIT to 20 rows for charts

EXAMPLES:
Q: Top produits vendus
{"sql": "SELECT pt.name as produit, SUM(sol.product_uom_qty) as quantite FROM sale_order_line sol JOIN product_template pt ON sol.product_id = pt.id JOIN sale_order so ON sol.order_id = so.id WHERE so.state IN ('sale','done') GROUP BY pt.name ORDER BY quantite DESC LIMIT 10", "chart_type": "bar", "title": "Top 10 produits vendus", "x_label": "Produit", "y_label": "Quantité"}

Q: Répartition clients par pays
{"sql": "SELECT country_id, COUNT(*) as nb FROM res_partner WHERE customer_rank > 0 AND country_id IS NOT NULL GROUP BY country_id ORDER BY nb DESC LIMIT 8", "chart_type": "pie", "title": "Répartition clients par pays", "x_label": "", "y_label": ""}

Q: Ventes par mois
{"sql": "SELECT TO_CHAR(so.date_order,'Mon YYYY') as mois, SUM(so.amount_untaxed) as chiffre_affaires FROM sale_order so WHERE so.state IN ('sale','done') GROUP BY TO_CHAR(so.date_order,'Mon YYYY'), DATE_TRUNC('month',so.date_order) ORDER BY DATE_TRUNC('month',so.date_order) LIMIT 12", "chart_type": "line", "title": "Évolution des ventes par mois", "x_label": "Mois", "y_label": "CA (€)"}

"""


def dashboard_node(state: AgentState) -> AgentState:
    """
    Node Dashboard — génère SQL + graphique Plotly
    """
    question = state["question"]
    logger.info(f"Dashboard Node - Question: '{question}'")

    schema_selector = SchemaSelector()
    executor = SQLExecutor()
    chart_gen = ChartGenerator()

    schema_text = schema_selector.get_relevant_schema(question)

    prompt = f"""Database schema:
{schema_text}

Generate chart config for: {question}"""

    try:
        # Générer config graphique
        response = requests.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.ollama_sql_model,
                "messages": [
                    {"role": "system", "content": DASHBOARD_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        raw = response.json()["message"]["content"].strip()

        # Parser le JSON
        config = _extract_json(raw)
        sql = config.get("sql", "")
        chart_type = config.get("chart_type", "bar")
        title = config.get("title", question)
        x_label = config.get("x_label", "")
        y_label = config.get("y_label", "")

        logger.info(f"SQL Dashboard: {sql}")
        logger.info(f"Chart type: {chart_type}")

        # Exécuter SQL
        result = executor.execute(sql)

        if result["success"] and result["results"]:
            chart_html = chart_gen.generate_json(
                chart_type=chart_type,
                data=result["results"],
                title=title,
                x_label=x_label,
                y_label=y_label,
            )
            answer = f"Voici le graphique : **{title}**"
        else:
            chart_html = chart_gen._empty_chart(title)
            answer = "Aucune donnée disponible pour générer ce graphique."

    except Exception as e:
        logger.error(f"Erreur Dashboard Node: {e}")
        chart_html = chart_gen._error_chart(str(e))
        answer = f"Erreur lors de la génération du graphique."

    return {
        **state,
        "answer": answer,
        "chart_html": chart_html,
        "chart_type": chart_type if 'chart_type' in locals() else "bar",
        "sql_query": sql if 'sql' in locals() else None,
    }


def _extract_json(raw: str) -> dict:
    """Extrait le JSON depuis la réponse du LLM"""
    import json
    # Nettoyer markdown
    raw = re.sub(r'```json\s*', '', raw)
    raw = re.sub(r'```\s*', '', raw)
    raw = raw.strip()

    # Extraire le JSON
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group())

    return json.loads(raw)
