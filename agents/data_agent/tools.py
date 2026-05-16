import ast
import json
import logging
from typing import List

import pandas as pd
import plotly.graph_objects as go
from google.api_core.exceptions import ResourceExhausted
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from agents.data_agent.model_catalogue.schema_retriever import retrieve_schema_for_question
from core.odoo_client import odoo_client
from shared.llm_factory import get_llm, LLMProvider

logger = logging.getLogger(__name__)


# ── Helpers internes ───────────────────────────────────────────────────────────


def _parse_domain(domain: str | list) -> list:
    if isinstance(domain, list):
        return domain
    safe = domain.replace("true", "True").replace("false", "False").replace("null", "None")
    try:
        return ast.literal_eval(safe)
    except Exception:
        return json.loads(domain)


def _parse_data(data: str | list) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return []
    return []


def _strip_date_granularity(groupby: list[str]) -> tuple[list[str], dict[str, str]]:
    """
    Odoo 16 XML-RPC n'accepte pas 'date_order:month' dans read_group.
    On retire la granularité et on regroupe côté Python après.

    Retourne :
        clean_groupby : groupby sans granularité, ex: ['date_order']
        granularity   : mapping champ -> granularité, ex: {'date_order': 'month'}
    """
    clean = []
    granularity = {}
    for g in groupby:
        if ":" in g:
            field, gran = g.split(":", 1)
            clean.append(field)
            granularity[field] = gran
        else:
            clean.append(g)
    return clean, granularity


def _apply_date_granularity(rows: list[dict], granularity: dict[str, str]) -> list[dict]:
    """
    Regroupe les lignes par la granularité demandée (month/year) côté Python.
    Additionne les valeurs numériques, garde la première valeur non-numérique.
    """
    if not granularity:
        return rows

    from collections import defaultdict

    def _truncate(value: str, gran: str) -> str:
        # value peut être '2026-01-15' ou '2026-01-15 00:00:00'
        s = str(value)[:10]  # garder YYYY-MM-DD
        if gran == "month":
            return s[:7]  # YYYY-MM
        if gran == "year":
            return s[:4]  # YYYY
        return s

    # Identifier les champs à tronquer et les champs numériques à sommer
    grouped: dict[tuple, dict] = defaultdict(dict)

    for row in rows:
        # Construire la clé de groupe avec les dates tronquées
        key_parts = []
        key_row = {}
        for field, gran in granularity.items():
            raw = row.get(field, "")
            truncated = _truncate(raw, gran)
            key_parts.append(truncated)
            key_row[field] = truncated

        key = tuple(key_parts)

        if key not in grouped:
            # Première occurrence : initialiser
            grouped[key] = dict(row)
            for field, truncated in key_row.items():
                grouped[key][field] = truncated
        else:
            # Occurrence suivante : additionner les numériques
            for k, v in row.items():
                if k in granularity:
                    continue  # déjà géré
                if isinstance(v, (int, float)):
                    grouped[key][k] = grouped[key].get(k, 0) + v

    return list(grouped.values())


# ── Input schemas ──────────────────────────────────────────────────────────────


class SearchCountInput(BaseModel):
    model: str = Field(description="Nom technique du modele Odoo, ex: 'res.partner'.")
    domain: str = Field(
        description=(
            "Filtres Odoo en string Python, ex: \"[['customer_rank','>',0]]\". "
            "Passe '[]' pour tout compter."
        )
    )


class SearchReadInput(BaseModel):
    model: str = Field(description="Nom technique du modele Odoo, ex: 'sale.order'.")
    domain: str = Field(
        description=(
            "Filtres Odoo en string Python, ex: \"[['state','in',['sale','done']]]\". "
            "TOUJOURS passer comme string, jamais comme liste."
        )
    )
    fields: List[str] = Field(
        description="Champs a retourner, ex: ['name', 'amount_untaxed']."
    )
    limit: int = Field(default=80, description="Nombre max d'enregistrements (defaut 80).")
    order: str = Field(default="", description="Tri, ex: 'amount_untaxed desc'.")


class ReadGroupInput(BaseModel):
    model: str = Field(description="Nom technique du modele Odoo, ex: 'sale.order'.")
    domain: str = Field(
        description=(
            "Filtres Odoo en string Python, ex: \"[['state','in',['sale','done']]]\". "
            "TOUJOURS passer comme string."
        )
    )
    fields: List[str] = Field(
        description=(
            "Champs a agreger avec leur fonction, ex: ['amount_untaxed:sum', 'id:count']. "
            "Pour grouper seulement sans agregat: ['partner_id']."
        )
    )
    groupby: List[str] = Field(
        description=(
            "Champs de regroupement. "
            "Pour grouper par mois : ['date_order:month'], par annee : ['date_order:year']. "
            "La granularite est appliquee automatiquement cote Python."
        )
    )
    limit: int = Field(default=80, description="Nombre max de groupes (defaut 80).")
    orderby: str = Field(
        default="",
        description=(
            "Tri sur un champ du modele cible, ex: 'amount_untaxed desc'. "
            "JAMAIS un champ d'un modele lie. "
            "Pour eviter l'erreur AmbiguousColumn sur un groupby many2one, "
            "utilise le champ d'agregat plutot que 'id', ex: 'amount_untaxed desc'."
        )
    )


class ChartInput(BaseModel):
    data: str = Field(
        description=(
            "Donnees a visualiser en string JSON — "
            "passe directement la sortie de odoo_read_group ou odoo_search_read. "
            "Ne JAMAIS construire ce JSON manuellement."
        )
    )
    chart_type: str = Field(
        description=(
            "'bar' pour comparaisons/classements, "
            "'line' pour tendances temporelles, "
            "'pie' pour repartitions en pourcentage."
        )
    )
    title: str = Field(description="Titre du graphique.")
    x_field: str = Field(description="Nom EXACT de la cle JSON pour l'axe X.")
    y_field: str = Field(description="Nom EXACT de la cle JSON pour l'axe Y (valeur numerique).")


# ── Tools ──────────────────────────────────────────────────────────────────────
@tool
def plan_query(question: str, subschema: str) -> str:
    """
    Génère un plan d'exécution étape par étape pour répondre à une question Odoo.

    APPELLE CET OUTIL après get_schema_for_question et avant toute requête.
    Le plan indique exactement quels modèles interroger, dans quel ordre,
    et comment relier les résultats entre eux.
    """
    planner_prompt = planner_prompt = """Tu es un expert Odoo 16 XML-RPC.

═══════════════════════════════════════
RÈGLES UNIVERSELLES XML-RPC ODOO
═══════════════════════════════════════
La dot notation (ex: 'order_id.user_id') se comporte DIFFÉREMMENT selon le paramètre :

┌─────────────┬──────────────────┬─────────────────────────────────────┐
│ Paramètre   │ Dot notation     │ Comportement                        │
├─────────────┼──────────────────┼─────────────────────────────────────┤
│ domain      │ ✅ AUTORISÉE     │ ['order_id.state', '=', 'done']     │
│ fields      │ ❌ INTERDITE     │ retourne ValueError côté Odoo        │
│ groupby     │ ❌ INTERDITE     │ résultats incorrects ou erreur       │
└─────────────┴──────────────────┴─────────────────────────────────────┘

CONSÉQUENCES sur la planification :
1. fields_hint → champs directs du modèle cible UNIQUEMENT.
   ❌ ['product_uom_qty', 'order_id.user_id.name']
   ✅ ['product_uom_qty', 'order_id']

2. groupby_hint → champs directs du modèle cible UNIQUEMENT.
   ❌ groupby: ['order_id.user_id']
   ✅ groupby: ['order_id'], puis join Python sur le modèle lié

3. Pas de JOIN automatique → appels séquentiels + agrégation Python.

PATTERN OBLIGATOIRE pour "grouper/accéder à un champ lié" :
   Étape A : odoo_search_read sur modèle source   → ['champ_local', 'relation_id']
   Étape B : odoo_search_read sur modèle lié      → ['id', 'champ_voulu']
   Étape C : python_aggregation                   → joindre, grouper, calculer

═══════════════════════════════════════
FORMAT DE RÉPONSE
═══════════════════════════════════════
Retourne UNIQUEMENT un JSON valide, sans markdown, sans explication :
{
  "steps": [
    {
      "step": 1,
      "tool": "odoo_search_read | odoo_read_group | odoo_search_count | python_aggregation",
      "model": "nom.modele",
      "purpose": "pourquoi cet appel",
      "domain_hint": "filtre exact à appliquer",
      "fields_hint": ["champs directs uniquement"],
      "groupby_hint": ["champs directs uniquement, jamais de dot notation"],
      "use_result_for": "comment utiliser le résultat à l'étape suivante"
    }
  ]
}

Pour python_aggregation, remplace model/domain_hint/fields_hint par :
  "logic": "description de l'opération Python (join, sum, max, filter, etc.)"

Les règles métier (quels modèles, quels champs, quels filtres) sont dans le schéma fourni.
Appuie-toi dessus pour construire le plan — ne suppose rien qui n'y figure pas.
"""
    try:
        llm = get_llm(LLMProvider.FIREWORKS_DEEPSEEK, temperature=0)
        response = llm.invoke([
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": f"Question: {question}\n\nSchéma:\n{subschema}"}
        ])
    except ResourceExhausted:
        llm = get_llm(LLMProvider.FIREWORKS_KIMI, temperature=0)
        response = llm.invoke([
            {"role": "system", "content": planner_prompt},
            {"role": "user", "content": f"Question: {question}\n\nSchéma:\n{subschema}"}
        ])
    return response.content


@tool
def get_schema_for_question(question: str) -> str:
    """
    Trouve les modèles Odoo pertinents pour une question et retourne leur
    schéma complet : noms techniques, champs disponibles, types, et relations
    entre modèles (jointures).

    APPELLE CET OUTIL EN PREMIER avant toute requête Odoo.
    Il remplace get_model_for_concept et odoo_fields_get.

    Ce que tu obtiens en retour :
      - Les modèles Odoo à utiliser (ex: hr.leave, hr.employee)
      - Les champs disponibles et leurs types
      - Les relations many2one pour naviguer entre modèles (jointures)

    Exemples d'utilisation :
      'congés des employés'
          → hr.leave (employee_id, state, number_of_days...)
          → hr.employee (user_id, department_id...)

      'commercial ayant vendu le plus de produit E-COM11'
          → product.template (default_code...)
          → sale.order.line (product_id, product_uom_qty...)
          → sale.order (user_id → res.users...)
          → hr.employee (user_id → res.users...)

      'factures impayées des clients'
          → account.move (move_type, state, payment_state, amount_total...)
          → res.partner (customer_rank...)
    """
    try:
        result = retrieve_schema_for_question(question)
        logger.info("[get_schema_for_question] sous-schéma assemblé pour : '%s'", question[:60])
        return result
    except Exception as e:
        logger.error("[get_schema_for_question] %s", e)
        return f"Erreur lors de la récupération du schéma : {e}"


# @tool
# def get_model_for_concept(concept: str) -> str:
#     """
#     Trouve le nom technique du modele Odoo correspondant a un concept metier.
#
#     Utilise cet outil quand tu ne connais pas le nom exact du modele.
#
#     Exemples:
#       'commandes clients'  -> 'sale.order'
#       'factures'           -> 'account.move'
#       'employes'           -> 'hr.employee'
#       'fournisseurs'       -> 'res.partner'
#     """
#     try:
#         model = resolve_model(concept)
#         logger.info(f"[get_model_for_concept] '{concept}' -> '{model}'")
#         return model
#     except Exception as e:
#         logger.error(f"[get_model_for_concept] {e}")
#         return f"Erreur: {e}"
#
#
# @tool
# def odoo_fields_get(model: str) -> str:
#     """
#     Liste les champs disponibles d'un modele Odoo (nom, type, label).
#
#     Utilise cet outil avant odoo_search_read ou odoo_read_group pour
#     connaitre les champs disponibles et leurs types.
#
#     Types importants:
#       many2one   -> retourne [id, "Nom"] dans search_read
#       selection  -> valeurs fixes ('sale', 'done', 'posted'...)
#       date/datetime -> groupable par ':month', ':year' via odoo_read_group
#     """
#     try:
#         fields = odoo_client.fields_get(model)
#         lines = [f"Champs de '{model}':"]
#         for fname, finfo in list(fields.items())[:50]:
#             lines.append(f"  - {fname} ({finfo.get('type')}) : {finfo.get('string')}")
#         return "\n".join(lines)
#     except Exception as e:
#         logger.error(f"[odoo_fields_get] {model}: {e}")
#         return f"Erreur: {e}"


@tool(args_schema=SearchCountInput)
def odoo_search_count(model: str, domain: str) -> str:
    """
    Compte le nombre d'enregistrements correspondant a un filtre.

    Utilise cet outil UNIQUEMENT pour les questions 'combien de X ?'.
    N'utilise JAMAIS odoo_search_read juste pour compter.

    Exemples de domains:
      Clients actifs      : "[['customer_rank','>',0],['active','=',True]]"
      Fournisseurs actifs : "[['supplier_rank','>',0],['active','=',True]]"
      Employes actifs     : "[['active','=',True]]"
      Ventes confirmees   : "[['state','in',['sale','done']]]"

    ATTENTION — res.partner contient clients, fournisseurs ET contacts melanges:
      - Clients      -> OBLIGATOIRE d'avoir customer_rank > 0
      - Fournisseurs -> OBLIGATOIRE d'avoir supplier_rank > 0
      - Sans ce filtre, le resultat est FAUX
    """
    try:
        parsed = _parse_domain(domain)
        count = odoo_client.search_count(model, parsed)
        logger.info(f"[odoo_search_count] {model} -> {count}")
        return str(count)
    except Exception as e:
        logger.error(f"[odoo_search_count] {model}: {e}")
        return f"Erreur: {e}"


@tool(args_schema=SearchReadInput)
def odoo_search_read(
        model: str,
        domain: str,
        fields: List[str],
        limit: int = 80,
        order: str = "",
) -> str:
    """
    Recupere des enregistrements depuis Odoo et retourne un JSON string.

    Utilise cet outil pour des listes d'enregistrements individuels.
    Pour des totaux, moyennes ou regroupements, utilise PLUTOT odoo_read_group.

    Le domain doit TOUJOURS etre passe comme string Python, ex:
      "[['state','in',['sale','done']]]"

    Regles Odoo 16:
      - Clients      : customer_rank > 0  (is_customer N'EXISTE PLUS)
      - Fournisseurs : supplier_rank > 0  (is_supplier N'EXISTE PLUS)
      - Ventes confirmees : state in ['sale','done']
      - Factures clients  : move_type='out_invoice' AND state='posted'
      - Factures impayees : ajouter payment_state in ['not_paid','partial']

    Le champ 'order' doit etre un champ du modele cible — JAMAIS un champ
    d'un modele lie (ex: ne pas trier res.partner par 'amount_untaxed').
    """
    try:
        parsed = _parse_domain(domain)
        results = odoo_client.search_read(model, parsed, fields, limit or 80, order or "")
        logger.info(f"[odoo_search_read] {model}: {len(results)} enregistrements")
        if not results:
            return "Aucun resultat."
        return json.dumps(results, ensure_ascii=False, default=str)
    except Exception as e:
        logger.error(f"[odoo_search_read] {model}: {e}")
        return f"Erreur: {e}"


@tool(args_schema=ReadGroupInput)
def odoo_read_group(
        model: str,
        domain: str,
        fields: List[str],
        groupby: List[str],
        limit: int = 80,
        orderby: str = "",
) -> str:
    """
    Effectue un GROUP BY et retourne les agregats.

    Utilise cet outil pour TOUTE question impliquant:
      - un total, une somme, une moyenne par categorie
      - un classement (meilleurs clients, top produits...)
      - une evolution dans le temps (par mois, par annee)
      - un comptage par groupe (employes par departement...)

    Format du champ 'fields' — TOUJOURS specifier la fonction d'agregation:
      'amount_untaxed:sum'   -> somme des montants HT
      'id:count'             -> nombre d'enregistrements
      'amount_total:avg'     -> moyenne des montants
      'partner_id'           -> champ de regroupement (pas de fonction)

    Format du champ 'groupby' — la granularite date est geree automatiquement:
      ['partner_id']              -> par partenaire
      ['date_order:month']        -> par mois (Python post-processing)
      ['date_order:year']         -> par annee (Python post-processing)
      ['department_id']           -> par departement

    REGLES orderby pour eviter les erreurs:
      - Toujours utiliser le champ d'agregat, pas 'id', ex: 'amount_untaxed desc'
      - Pour un simple comptage, laisser orderby vide et trier en Python si besoin
      - JAMAIS un champ d'un modele lie

    Exemples:

      CA par client (sale.order):
        fields=['partner_id', 'amount_untaxed:sum']
        groupby=['partner_id']
        orderby='amount_untaxed desc'

      Employes par departement (hr.employee):
        fields=['department_id', 'id:count']
        groupby=['department_id']
        orderby=''   <- laisser vide pour eviter AmbiguousColumn

      Ventes par mois (sale.order):
        fields=['date_order', 'amount_untaxed:sum']
        groupby=['date_order:month']
        orderby=''

    Retourne un JSON array avec les champs demandes.
    Les champs many2one retournent le label directement (ex: "Azure Interior").
    """
    try:
        parsed_domain = _parse_domain(domain)

        # FIX 1 — Retirer la granularite date (':month', ':year') du groupby
        # car Odoo 16 XML-RPC ne la supporte pas. On regroupe en Python apres.
        clean_groupby, granularity = _strip_date_granularity(groupby)

        # Mettre a jour fields pour utiliser le champ sans granularite
        clean_fields = []
        for f in fields:
            base = f.split(":")[0]
            if base in granularity:
                # Remplacer 'date_order:month' -> 'date_order' dans fields aussi
                aggfunc = f.split(":")[1] if ":" in f else None
                clean_fields.append(base if not aggfunc or aggfunc in ("month", "year", "day") else f"{base}:{aggfunc}")
            else:
                clean_fields.append(f)

        # FIX 2 — orderby vide si risque AmbiguousColumn (groupby many2one sans agregat)
        safe_orderby = orderby or ""

        results = odoo_client.read_group(
            model, parsed_domain, clean_fields, clean_groupby,
            limit=limit or 80, orderby=safe_orderby
        )
        logger.info(f"[odoo_read_group] {model} groupby={groupby}: {len(results)} groupes")
        if not results:
            return "Aucun resultat."

        # Nettoyage : supprimer les cles internes Odoo (__domain, __fold)
        # et simplifier les many2one [id, "Nom"] -> "Nom"
        cleaned = []
        for row in results:
            clean = {}
            for k, v in row.items():
                if k.startswith("__"):
                    continue
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    clean[k] = v[1]  # many2one -> garder le label
                else:
                    clean[k] = v
            cleaned.append(clean)

        # FIX 1 (suite) — Appliquer le regroupement par granularite date en Python
        if granularity:
            cleaned = _apply_date_granularity(cleaned, granularity)
            # Renommer la cle pour qu'elle reflète la granularité
            # ex: 'date_order' -> 'date_order:month' dans les données retournées
            for row in cleaned:
                for field, gran in granularity.items():
                    if field in row:
                        row[f"{field}:{gran}"] = row.pop(field)

        return json.dumps(cleaned, ensure_ascii=False, default=str)

    except Exception as e:
        logger.error(f"[odoo_read_group] {model}: {e}")
        return f"Erreur: {e}"


@tool(args_schema=ChartInput)
def generate_chart(
        data: str,
        chart_type: str,
        title: str,
        x_field: str,
        y_field: str,
) -> str:
    """
    Genere un graphique Plotly depuis des donnees Odoo et retourne une confirmation.

    Utilise cet outil UNIQUEMENT si l'utilisateur demande explicitement
    un graphique, une visualisation, une courbe ou un diagramme.
    NE JAMAIS generer un graphique sans demande explicite.

    WORKFLOW OBLIGATOIRE avant d'appeler cet outil:
      1. Appelle odoo_read_group ou odoo_search_read pour obtenir les donnees
      2. Identifie les cles exactes retournees (x_field et y_field)
      3. Passe la sortie brute dans 'data' sans la modifier

    `data` : string JSON brut sorti de odoo_read_group ou odoo_search_read.
             Ne JAMAIS construire ce JSON manuellement.
    `x_field` : cle EXACTE presente dans les dicts de data pour l'axe X.
    `y_field` : cle EXACTE presente dans les dicts de data pour la valeur numerique.

    chart_type:
      'bar'  -> comparaisons et classements
      'line' -> evolution dans le temps
      'pie'  -> repartitions en pourcentage

    Retourne "Graphique genere: <titre>" quand c'est reussi.
    """
    try:
        rows = _parse_data(data)
        if not rows:
            return "Erreur: donnees vides ou invalides."

        df = pd.DataFrame(rows)
        cols = df.columns.tolist()

        # Fallback si les champs exacts ne correspondent pas
        if x_field not in cols:
            logger.warning(f"[generate_chart] x_field '{x_field}' absent, fallback sur '{cols[0]}'")
            x_field = cols[0]
        if y_field not in cols:
            fallback = cols[1] if len(cols) > 1 else cols[0]
            logger.warning(f"[generate_chart] y_field '{y_field}' absent, fallback sur '{fallback}'")
            y_field = fallback

        # Convertir y en numérique (sécurité)
        df[y_field] = pd.to_numeric(df[y_field], errors="coerce").fillna(0)

        match chart_type:
            case "bar":
                fig = go.Figure(go.Bar(x=df[x_field], y=df[y_field]))
            case "line":
                fig = go.Figure(go.Scatter(
                    x=df[x_field], y=df[y_field], mode="lines+markers"
                ))
            case "pie":
                fig = go.Figure(go.Pie(labels=df[x_field], values=df[y_field]))
            case _:
                fig = go.Figure(go.Bar(x=df[x_field], y=df[y_field]))

        fig.update_layout(title=title)
        chart_json = fig.to_json()

        logger.info(f"[generate_chart] OK chart_type={chart_type} title='{title}' rows={len(rows)}")

        # FIX 3 — Retourner une confirmation courte, pas le JSON Plotly brut.
        # Le JSON brut (plusieurs Ko) pousse le LLM à continuer de générer
        # du contenu hors du tool call -> tool_use_failed.
        # Le JSON est stocké en interne et accessible via get_last_chart().
        _last_chart_store["json"] = chart_json
        _last_chart_store["title"] = title

        return f"Graphique genere avec succes: '{title}' ({chart_type}, {len(rows)} points)."

    except Exception as e:
        logger.error(f"[generate_chart] {e}")
        return f"Erreur generation graphique: {e}"


# Stockage interne du dernier graphique généré (accessible par l'API)
_last_chart_store: dict = {"json": None, "title": None}


@tool
def format_response(raw_answer: str, question: str) -> str:
    """
    Formate la réponse finale en un message clair, structuré et agréable.
    Utilise cet outil comme DERNIÈRE étape, juste avant de répondre à l'utilisateur.
    """
    _formatter_llm = get_llm(LLMProvider.GEMINI_FLASH_LITE)
    response = _formatter_llm.invoke([
        {
            "role": "system",
            "content": """Tu es un assistant qui formate les réponses de manière claire et professionnelle.

Règles :
- Utilise des emojis pertinents (📊 pour stats, 👤 pour personnes, 💰 pour finances, ✅ pour succès...)
- Structure avec des sauts de ligne si plusieurs informations
- Sois concis mais complet
- Réponds dans la même langue que la question
- Ne rajoute pas d'informations que tu n'as pas reçues
- Si c'est un chiffre simple, une ligne suffit"""
        },
        {
            "role": "user",
            "content": f"Question posée : {question}\nRéponse brute : {raw_answer}\n\nFormate cette réponse."
        }
    ])
    return response.content


def get_last_chart() -> dict | None:
    """
    Retourne le JSON Plotly du dernier graphique genere, ou None.
    A appeler depuis l'API apres run_data_agent().

    Exemple dans api/main.py:
        result = run_data_agent(question)
        chart = get_last_chart()
        if chart:
            response.chart_data = chart["json"]
    """
    if _last_chart_store["json"] is None:
        return None
    return dict(_last_chart_store)
