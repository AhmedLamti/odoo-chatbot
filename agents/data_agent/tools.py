import ast
import json
import logging
from typing import List

import pandas as pd
import plotly.graph_objects as go
import requests
from google.api_core.exceptions import ResourceExhausted
from langchain_core.tools import tool
from pydantic import BaseModel, Field ,validator
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.odoo_client import get_odoo_client
from shared.llm_factory import get_llm, LLMProvider

logger = logging.getLogger(__name__)

# ── Configuration RAG ──────────────────────────────────────────────────────────

_QDRANT_URL = "http://localhost:6333"
COL_MODELS = "odoo_models_v3"
COL_FIELDS = "odoo_fields_v3"
_OLLAMA_URL = "http://localhost:11434"
_EMBEDDING_MODEL = "bge-m3"
_SCHEMA_FILE = "schema_odoo_enrichi_rag_complexe_enriched.json"

_qdrant = QdrantClient(url=_QDRANT_URL)

# Chargement unique du schéma au démarrage
with open(_SCHEMA_FILE, encoding="utf-8") as _f:
    _SCHEMA: dict = json.load(_f)
logger.info("[RAG] %d modèles Odoo chargés depuis %s", len(_SCHEMA), _SCHEMA_FILE)

MASTER_BOOST = {
    "vend": ["user_id", "member_id"], "commercia": ["user_id", "member_id"],
    "respons": ["user_id", "manager_id"], "clien": ["partner_id"],
    "fournisseur": ["partner_id", "seller_ids"], "partenaire": ["partner_id"],
    "tier": ["partner_id"], "contac": ["partner_id"],
    "sociét": ["company_id"], "entrepris": ["company_id"], "filial": ["company_id"],
    "équip": ["team_id"], "département": ["department_id"],
    "employ": ["employee_id", "user_id"], "manag": ["parent_id", "manager_id"],
    "statut": ["state", "invoice_status", "delivery_status", "payment_state"],
    "état": ["state", "kanban_state"], "étap": ["stage_id", "state"],
    "phas": ["stage_id"], "valid": ["state"], "confirm": ["state"],
    "brouillon": ["state"], "annul": ["state"],
    "gagn": ["stage_id", "probability"], "perdu": ["stage_id", "lost_reason_id"],
    "factur": ["invoice_status", "invoice_ids", "move_id"],
    "pay": ["payment_state", "is_paid"], "ouvert": ["state"],
    "clôtur": ["state", "date_closed"],
    "montant": ["amount_total", "amount_untaxed", "price_unit", "expected_revenue"],
    "total": ["amount_total", "amount_untaxed"], "somme": ["amount_total"],
    "ca ": ["amount_total"], "chiffre d'affaires": ["amount_total"],
    "revenu": ["expected_revenue", "recurring_revenue"], "prix": ["price_unit", "amount_total"],
    "tax": ["tax_id", "taxes_id", "tax_ids"], "tva": ["tax_id", "taxes_id", "tax_ids"],
    "devis": ["currency_id", "company_currency_id"], "monnaie": ["currency_id"],
    "solde": ["balance", "credit", "debit"], "crédit": ["credit"], "débit": ["debit"],
    "produi": ["product_id", "product_tmpl_id"], "articl": ["product_id", "product_tmpl_id"],
    "variant": ["product_id"], "quantit": ["product_uom_qty", "qty_done", "quantity", "product_qty"],
    "qté": ["product_uom_qty", "qty_done", "quantity"],
    "stock": ["qty_available", "virtual_available", "location_id"],
    "emplac": ["location_id", "location_dest_id"], "lot": ["lot_id", "lot_name"],
    "séri": ["lot_id"], "poids": ["weight"], "unité": ["product_uom"],
    "date": ["date", "date_order", "date_deadline", "create_date"],
    "quand": ["date", "create_date"], "échéanc": ["date_deadline", "validity_date"],
    "cré": ["create_uid", "create_date"], "auteur": ["create_uid"],
    "modifi": ["write_uid", "write_date"], "derni": ["write_date"],
    "début": ["date_start"], "fin": ["date_stop", "date_end"],
    "réf": ["name", "ref", "reference", "client_order_ref"], "numéro": ["name", "number"],
    "nom": ["name", "display_name"], "desc": ["name", "description", "note"],
    "projet": ["project_id"], "tâch": ["task_id"], "command": ["order_id"],
    "étiquet": ["tag_ids", "category_id"], "catégor": ["categ_id", "category_id"],
    "motif": ["lost_reason_id", "reason"]
}


# ── Helpers internes ───────────────────────────────────────────────────────────

def _parse_domain(domain: str | list) -> list:
    if isinstance(domain, list):
        return domain
    safe = (
        domain.replace("true", "True").replace("false", "False").replace("null", "None")
    )
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


def _apply_date_granularity(
        rows: list[dict], granularity: dict[str, str]
) -> list[dict]:
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


def expand_schema_with_relations(selected_models_dict: dict) -> dict:
    """
    Prend en entrée le dictionnaire des modèles et champs choisis par l'Agent.
    Retourne un sous-schéma complet incluant automatiquement les modèles liés nécessaires.
    """
    final_sub_schema = {}
    models_to_process = list(selected_models_dict.keys())
    processed_models = set()

    for model_name in models_to_process:
        if model_name not in _SCHEMA or model_name in processed_models:
            continue

        processed_models.add(model_name)

        # On initialise la coquille vide pour ce modèle dans notre schéma final
        final_sub_schema[model_name] = {
            "description": _SCHEMA[model_name].get("description", ""),
            "fields": {}
        }

        selected_fields = selected_models_dict[model_name]

        # On peuple les champs sélectionnés
        for field_name in selected_fields:
            if field_name in _SCHEMA[model_name].get("fields", {}):
                raw_field_data = _SCHEMA[model_name]["fields"][field_name]

                # 1. NETTOYAGE DIRECT DU CHAMP PRINCIPAL
                clean_field = {
                    "type": raw_field_data.get("type", ""),
                    "description": raw_field_data.get("description", "")
                }
                if "related_model" in raw_field_data:
                    clean_field["related_model"] = raw_field_data["related_model"]

                final_sub_schema[model_name]["fields"][field_name] = clean_field

                # 2. LA MAGIE OPÈRE ICI : Si c'est un champ relationnel
                related_model = raw_field_data.get("related_model")
                if related_model and related_model in _SCHEMA:
                    # On ajoute le modèle lié entier au schéma final
                    if related_model not in final_sub_schema:

                        clean_related_schema = {
                            "description": _SCHEMA[related_model].get("description", ""),
                            "fields": {}
                        }

                        # 3. NETTOYAGE DIRECT DES CHAMPS DU MODÈLE LIÉ
                        for rel_f_name, rel_f_data in _SCHEMA[related_model].get("fields", {}).items():
                            clean_rel_field = {
                                "type": rel_f_data.get("type", ""),
                                "description": rel_f_data.get("description", "")
                            }
                            if "related_model" in rel_f_data:
                                clean_rel_field["related_model"] = rel_f_data["related_model"]

                            clean_related_schema["fields"][rel_f_name] = clean_rel_field

                        # On l'ajoute au schéma final
                        final_sub_schema[related_model] = clean_related_schema

                        logger.info(
                            f"🔗 Auto-Expansion: Ajout de '{related_model}' (nettoyé) requis par '{model_name}.{field_name}'")

    return final_sub_schema


# ── Input schemas ──────────────────────────────────────────────────────────────


class SearchCountInput(BaseModel):
    model: str = Field(description="Nom technique du modele Odoo, ex: 'res.partner'.")
    domain: str = Field(
        description=(
            "Filtres Odoo en string Python, ex: \"[['customer_rank','>',0]]\". "
            "Passe '[]' pour tout compter."
        )
    )
    odoo_user_email: str | None = Field(
        default=None, description="Email/login Odoo du user connecté."
    )
    odoo_api_key: str | None = Field(
        default=None, description="API key Odoo du user connecté."
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
    limit: int = Field(
        default=80, description="Nombre max d'enregistrements (defaut 80)."
    )
    order: str = Field(default="", description="Tri, ex: 'amount_untaxed desc'.")
    odoo_user_email: str | None = Field(
        default=None, description="Email/login Odoo du user connecté."
    )
    odoo_api_key: str | None = Field(
        default=None, description="API key Odoo du user connecté."
    )


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
        ),
    )
    odoo_user_email: str | None = Field(
        default=None, description="Email/login Odoo du user connecté."
    )
    odoo_api_key: str | None = Field(
        default=None, description="API key Odoo du user connecté."
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
    y_field: str = Field(
        description="Nom EXACT de la cle JSON pour l'axe Y (valeur numerique)."
    )


# ── Tools ──────────────────────────────────────────────────────────────────────
@tool
def plan_query(question: str, subschema: str) -> str:
    """
    Génère un plan d'exécution étape par étape pour répondre à une question Odoo.

    APPELLE CET OUTIL après get_schema_for_question et avant toute requête.
    Le plan indique exactement quels modèles interroger, dans quel ordre,
    et comment relier les résultats entre eux.
    """
    planner_prompt = """Tu es un expert Odoo 16 XML-RPC.

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
        response = llm.invoke(
            [
                {"role": "system", "content": planner_prompt},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nSchéma:\n{subschema}",
                },
            ]
        )
    except ResourceExhausted:
        llm = get_llm(LLMProvider.FIREWORKS_KIMI, temperature=0)
        response = llm.invoke(
            [
                {"role": "system", "content": planner_prompt},
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nSchéma:\n{subschema}",
                },
            ]
        )
    return response.content


# ── Input schemas — RAG ────────────────────────────────────────────────────────


class VectorSearchInput(BaseModel):
    question: str = Field(description="Question métier posée par l'utilisateur.")
    top_k_models: int = Field(
        default=4, description="Nombre de modèles candidats à retourner (défaut 4)."
    )
    top_k_fields: int = Field(
        default=15, description="Nombre de champs à retourner par modèle (défaut 15)."
    )

    @validator('top_k_models', 'top_k_fields', pre=True)
    def coerce_to_int(cls, v):
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return v


class SelectModelsInput(BaseModel):
    question: str = Field(description="Question métier originale.")
    candidates: str = Field(
        description="JSON string retourné par search_similar_models."
    )


class GetSchemaInput(BaseModel):
    model_names: List[str] = Field(
        description="Liste des noms de modèles retournée par select_models."
    )


# ── Helpers RAG ────────────────────────────────────────────────────────────────


def _get_embedding(text: str) -> list[float]:
    response = requests.post(
        f"{_OLLAMA_URL}/api/embeddings",
        json={"model": _EMBEDDING_MODEL, "prompt": f"search_query: {text}"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["embedding"]


# ── Tools RAG ──────────────────────────────────────────────────────────────────


@tool(args_schema=VectorSearchInput)
def search_similar_models(question: str, top_k_models: int = 4, top_k_fields: int = 15) -> str:
    """
    Recherche les modèles Odoo et les champs potentiels liés à la question.

    Cet outil effectue une recherche vectorielle en deux étapes :
    1. Identifie les modèles (tables) les plus pertinents (ex: sale.order, res.partner).
    2. Pour chaque modèle, identifie les champs (colonnes) les plus probables en utilisant
       un dictionnaire de boost métier (ex: 'créé par' -> 'create_uid').

    Args:
        question: La question originale de l'utilisateur ou une version reformulée techniquement.
        top_k_models: Nombre de modèles à explorer (par défaut 5).
        top_k_fields: Nombre de champs à ramener par modèle (par défaut 50).

    Returns:
        Un dictionnaire JSON au format { "model_name": ["field1", "field2", ...] }.
    """
    try:
        result_schema = {}
        query_vector = _get_embedding(question)
        question_lower = question.lower()

        # --- ÉTAPE 1 : RECHERCHE DES MODÈLES ---
        model_hits = _qdrant.query_points(
            collection_name=COL_MODELS,
            query=query_vector,
            limit=8
        ).points

        scored_models = []
        for hit in model_hits:
            m_name = hit.payload.get("model_name")
            weight = hit.payload.get("weight", 1.0)
            final_score = hit.score * weight
            scored_models.append({"model_name": m_name, "score": final_score})

        # Tri par score pondéré
        scored_models.sort(key=lambda x: x["score"], reverse=True)
        top_models_names = [m["model_name"] for m in scored_models[:top_k_models]]

        if not top_models_names:
            return "Aucun modèle trouvé."

        for model_name in top_models_names:

            # On récupère les 50 meilleurs champs spécifiquement pour CE modèle
            field_hits = _qdrant.query_points(
                collection_name=COL_FIELDS,
                query=query_vector,
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="model_name",
                            match=MatchValue(value=model_name)
                        )
                    ]
                ),
                limit=150
            ).points

            refined_fields = []
            for hit in field_hits:
                f_name = hit.payload.get("field_name")
                score = hit.score

                # --- APPLICATION DU MASTER_BOOST ---
                for keyword, target_fields in MASTER_BOOST.items():
                    if keyword in question_lower and f_name in target_fields:
                        score += 2.0  # Bonus massif pour correspondance métier

                refined_fields.append({"name": f_name, "score": score})

            # Tri final des champs après boost pour CE modèle
            refined_fields.sort(key=lambda x: x["score"], reverse=True)

            # On garde les K meilleurs champs
            predicted_fields = [f["name"] for f in refined_fields[:top_k_fields]]

            # On ajoute ce modèle et ses champs au dictionnaire de résultat
            if predicted_fields:
                result_schema[model_name] = predicted_fields

        return json.dumps(result_schema, ensure_ascii=False)

    except Exception as e:
        logger.error("[search_similar_models] %s", e)
        return f"Erreur recherche vectorielle : {e}"


@tool(args_schema=SelectModelsInput)
@tool
def select_models(question: str, candidates: str) -> str:
    """
    Valide les modèles/champs finaux et récupère le schéma technique détaillé.

    L'Agent doit analyser les 'candidates' fournis par search_similar_models et ne garder
    que ce qui est strictement nécessaire pour répondre à la question.

    FONCTIONNALITÉS AVANCÉES :
    - Auto-Expansion : Si tu sélectionnes un champ relationnel (ex: 'seller_ids'), l'outil
      ajoutera automatiquement le modèle lié (ex: 'product.supplierinfo') au schéma.
    - Nettoyage : Filtre le bruit pour ne garder que les métadonnées utiles au 'plan_query'.

    Args:
        question: La question de l'utilisateur (pour le contexte de sélection).
        candidates: Le JSON string retourné par 'search_similar_models'.

    Returns:
        Un sous-schéma JSON enrichi contenant les types de champs, les descriptions
        et les modèles liés. C'est la base de données finale pour générer la requête Odoo.
    """
    # 1. Demander au LLM de faire le tri dans les candidats
    prompt = f"""
    Tu es un expert Odoo. Voici la question de l'utilisateur : "{question}"
    Voici les modèles et champs candidats trouvés par la recherche : {candidates}

    Sélectionne UNIQUEMENT les modèles et les champs strictement nécessaires pour répondre à la question.
    Réponds UNIQUEMENT au format JSON strict, où les clés sont les modèles et les valeurs sont des listes de champs.
    Exemple de format attendu : {{"product.template": ["name", "seller_ids"], "res.company": ["name"]}}
    """

    _llm = get_llm(LLMProvider.GEMINI_FLASH_LITE)
    response = _llm.invoke([{"role": "user", "content": prompt}])

    try:
        # On nettoie la réponse pour extraire le JSON (au cas où il y a des balises ```json)
        clean_json = response.content.strip().strip('```json').strip('```')
        selected_dict = json.loads(clean_json)
    except json.JSONDecodeError:
        logger.error("Le LLM n'a pas renvoyé un JSON valide pour select_models.")
        return "{}"

    # 2. On passe le choix de l'Agent dans notre moulinette d'auto-expansion
    # final_schema = expand_schema_with_relations(selected_dict)

    # 3. On renvoie le sous-schéma parfait, léger, et complet avec ses relations !
    return json.dumps(selected_dict, ensure_ascii=False)


# @tool(args_schema=GetSchemaInput)
# def get_models_schema(model_names: List[str]) -> str:
#     """
#     — Retourne le schéma exact (champs, types, relations) des modèles sélectionnés.
#
#     Prend en entrée la liste retournée par select_models.
#     Retourne un sous-schéma complet prêt à être utilisé pour construire les requêtes Odoo.
#
#     APPELLE CET OUTIL après select_models, avant plan_query.
#
#     Ce que tu obtiens :
#       - Champs disponibles avec leur type et description
#       - Relations many2one vers d'autres modèles (pour les jointures)
#       - Description fonctionnelle de chaque modèle
#     """
#     try:
#         schema_output = {}
#
#         for model_name in model_names:
#             if model_name not in _SCHEMA:
#                 logger.warning(
#                     "[get_models_schema] modèle '%s' absent du schéma", model_name
#                 )
#                 continue
#
#             model_data = _SCHEMA[model_name]
#             fields_raw = model_data.get("fields", {})
#
#             candidate = {
#                 "model_name": model_name,
#                 "score": 1.0,
#                 "source": "schema_compaction",
#                 "description_enrichie": model_data.get("description_enrichie", ""),
#                 "fields": list(fields_raw.keys()),
#                 "relations": [
#                     {
#                         "field": field_name,
#                         "type": field_data.get("type"),
#                         "related_model": field_data.get("related_model"),
#                         "description": field_data.get("description", ""),
#                     }
#                     for field_name, field_data in fields_raw.items()
#                     if field_data.get("related_model")
#                 ],
#             }
#
#             compact = compact_candidate(
#                 candidate,
#                 question="",
#                 candidate_model_names=model_names,
#             )
#
#             selected_field_names = set(compact.get("fields", []))
#
#             for rel in compact.get("relations", []):
#                 if isinstance(rel, dict) and rel.get("field"):
#                     selected_field_names.add(rel["field"])
#
#             fields_clean = {}
#
#             for field_name in selected_field_names:
#                 field_data = fields_raw.get(field_name)
#
#                 if not field_data:
#                     continue
#
#                 if field_name in _SKIP_EXACT:
#                     continue
#
#                 if any(field_name.startswith(p) for p in _SKIP_PREFIXES):
#                     continue
#
#                 fields_clean[field_name] = {
#                     "type": field_data.get("type", ""),
#                     "description": field_data.get("description", ""),
#                     **(
#                         {"related_model": field_data["related_model"]}
#                         if "related_model" in field_data
#                         else {}
#                     ),
#                 }
#
#             schema_output[model_name] = {
#                 "description": model_data.get("description", ""),
#                 "description_enrichie": model_data.get("description_enrichie", "")[
#                     :600
#                 ],
#                 "fields": fields_clean,
#             }
#
#         if not schema_output:
#             return "Aucun modèle trouvé dans le schéma."
#
#         logger.info(
#             "[get_models_schema] schéma retourné pour : %s", list(schema_output.keys())
#         )
#
#         return json.dumps(schema_output, ensure_ascii=False)
#
#     except Exception as e:
#         logger.error("[get_models_schema] %s", e)
#         return f"Erreur récupération schéma : {e}"


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
def odoo_search_count(
        model: str,
        domain: str,
        odoo_user_email: str | None = None,
        odoo_api_key: str | None = None,
) -> str:
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
        client = get_odoo_client(username=odoo_user_email, api_key=odoo_api_key)
        count = client.search_count(model, parsed)
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
        odoo_user_email: str | None = None,
        odoo_api_key: str | None = None,
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
        client = get_odoo_client(username=odoo_user_email, api_key=odoo_api_key)
        results = client.search_read(model, parsed, fields, limit or 80, order or "")
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
        odoo_user_email: str | None = None,
        odoo_api_key: str | None = None,
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
                clean_fields.append(
                    base
                    if not aggfunc or aggfunc in ("month", "year", "day")
                    else f"{base}:{aggfunc}"
                )
            else:
                clean_fields.append(f)

        # FIX 2 — orderby vide si risque AmbiguousColumn (groupby many2one sans agregat)
        safe_orderby = orderby or ""

        client = get_odoo_client(username=odoo_user_email, api_key=odoo_api_key)
        results = client.read_group(
            model,
            parsed_domain,
            clean_fields,
            clean_groupby,
            limit=limit or 80,
            orderby=safe_orderby,
        )
        logger.info(
            f"[odoo_read_group] {model} groupby={groupby}: {len(results)} groupes"
        )
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
            logger.warning(
                f"[generate_chart] x_field '{x_field}' absent, fallback sur '{cols[0]}'"
            )
            x_field = cols[0]
        if y_field not in cols:
            fallback = cols[1] if len(cols) > 1 else cols[0]
            logger.warning(
                f"[generate_chart] y_field '{y_field}' absent, fallback sur '{fallback}'"
            )
            y_field = fallback

        # Convertir y en numérique (sécurité)
        df[y_field] = pd.to_numeric(df[y_field], errors="coerce").fillna(0)

        match chart_type:
            case "bar":
                fig = go.Figure(go.Bar(x=df[x_field], y=df[y_field]))
            case "line":
                fig = go.Figure(
                    go.Scatter(x=df[x_field], y=df[y_field], mode="lines+markers")
                )
            case "pie":
                fig = go.Figure(go.Pie(labels=df[x_field], values=df[y_field]))
            case _:
                fig = go.Figure(go.Bar(x=df[x_field], y=df[y_field]))

        fig.update_layout(title=title)
        chart_json = fig.to_json()

        logger.info(
            f"[generate_chart] OK chart_type={chart_type} title='{title}' rows={len(rows)}"
        )

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
    response = _formatter_llm.invoke(
        [
            {
                "role": "system",
                "content": """Tu es un assistant qui formate les réponses de manière claire et professionnelle.

Règles :
- Utilise des emojis pertinents (📊 pour stats, 👤 pour personnes, 💰 pour finances, ✅ pour succès...)
- Structure avec des sauts de ligne si plusieurs informations
- Sois concis mais complet
- Réponds dans la même langue que la question
- Ne rajoute pas d'informations que tu n'as pas reçues
- Si c'est un chiffre simple, une ligne suffit""",
            },
            {
                "role": "user",
                "content": f"Question posée : {question}\nRéponse brute : {raw_answer}\n\nFormate cette réponse.",
            },
        ]
    )
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
