import ast
import json
import logging
from typing import List

import pandas as pd
import plotly.graph_objects as go
import requests
from google.api_core.exceptions import ResourceExhausted
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from core.odoo_client import get_odoo_client
from shared.llm_factory import get_llm, LLMProvider

logger = logging.getLogger(__name__)

# ── Configuration RAG ──────────────────────────────────────────────────────────

_QDRANT_URL = "http://localhost:6333"
_COLLECTION_NAME = "odoo_schema_v3"
_OLLAMA_URL = "http://localhost:11434"
_EMBEDDING_MODEL = "bge-m3"
_SCHEMA_FILE = "schema_odoo_enrichi_rag_complexe.json"

_qdrant = QdrantClient(url=_QDRANT_URL)

# Chargement unique du schéma au démarrage
with open(_SCHEMA_FILE, encoding="utf-8") as _f:
    _SCHEMA: dict = json.load(_f)
logger.info("[RAG] %d modèles Odoo chargés depuis %s", len(_SCHEMA), _SCHEMA_FILE)

# Champs techniques à exclure du schéma retourné
_SKIP_PREFIXES = ("message_", "activity_", "website_")
_SKIP_EXACT = {
    "__last_update",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "display_name",
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


INTENT_MODEL_RULES = [
    (
        ["vendu", "vente", "vendeur", "commercial", "salesperson", "seller"],
        ["sale.order", "sale.order.line", "res.users"],
    ),
    (
        ["produit", "article", "default_code", "sku", "référence", "reference"],
        ["product.template", "product.product", "sale.order.line"],
    ),
    (
        ["congé", "conges", "absence", "jours de congé", "leave", "time off"],
        ["hr.employee", "hr.leave", "hr.leave.allocation", "hr.leave.type"],
    ),
    (
        ["facture", "factures", "impayé", "impayée", "impayées", "invoice", "unpaid"],
        ["account.move", "account.move.line", "res.partner"],
    ),
    (["client", "clients", "customer"], ["res.partner"]),
    (
        ["paiement", "règlement", "payment", "paid"],
        ["account.payment", "account.move", "account.move.line"],
    ),
]


def detect_required_models(question: str) -> list[str]:
    q = question.lower()
    models = []

    for keywords, required_models in INTENT_MODEL_RULES:
        if any(keyword in q for keyword in keywords):
            models.extend(required_models)

    return list(dict.fromkeys(models))


def _model_name_to_id(model_name: str) -> int:
    import hashlib

    return int(hashlib.md5(model_name.encode()).hexdigest()[:15], 16)


def get_rule_candidates(model_names: list[str]) -> list[dict]:
    candidates = []

    for model_name in model_names:
        try:
            records = _qdrant.retrieve(
                collection_name=_COLLECTION_NAME,
                ids=[_model_name_to_id(model_name)],
                with_payload=True,
                with_vectors=False,
            )

            for record in records:
                payload = record.payload or {}
                candidates.append(
                    {
                        "model_name": payload.get("model_name", model_name),
                        "score": 1.0,
                        "source": "rule",
                        "description_enrichie": payload.get("description_enrichie", ""),
                        "fields": payload.get("fields", []),
                        "relations": payload.get("relations", []),
                    }
                )

        except Exception as e:
            logger.warning("[get_rule_candidates] %s: %s", model_name, e)

    return candidates


def expand_candidates_with_relations(
        candidates: list[dict], depth: int = 1
) -> list[dict]:
    """
    Ajoute les modèles liés aux candidats via les champs related_model.
    Exemple: sale.order.line -> sale.order, product.product, product.template, res.users
    """
    model_names = {c.get("model_name") for c in candidates if c.get("model_name")}

    expanded = set(model_names)

    current_level = set(model_names)

    for _ in range(depth):
        next_level = set()

        for model_name in current_level:
            model_data = _SCHEMA.get(model_name, {})
            fields = model_data.get("fields", {})

            for field_name, field_data in fields.items():
                related_model = field_data.get("related_model")

                if related_model and related_model in _SCHEMA:
                    if related_model not in expanded:
                        expanded.add(related_model)
                        next_level.add(related_model)

        current_level = next_level

    final_candidates = {}

    for candidate in candidates:
        model_name = candidate.get("model_name")
        if model_name:
            final_candidates[model_name] = candidate

    for model_name in expanded:
        if model_name not in final_candidates:
            model_data = _SCHEMA.get(model_name, {})

            relations = []
            for field_name, field_data in model_data.get("fields", {}).items():
                related_model = field_data.get("related_model")
                if related_model:
                    relations.append(
                        {
                            "field": field_name,
                            "type": field_data.get("type"),
                            "related_model": related_model,
                            "description": field_data.get("description", ""),
                        }
                    )

            final_candidates[model_name] = {
                "model_name": model_name,
                "score": 0.0,
                "source": "relation_expansion",
                "description_enrichie": model_data.get("description_enrichie", ""),
                "fields": list(model_data.get("fields", {}).keys()),
                "relations": relations,
            }

    return list(final_candidates.values())


IMPORTANT_FIELDS = {
    "identity": {
        "id",
        "name",
        "display_name",
        "code",
        "ref",
        "barcode",
        "default_code",
    },
    "status": {"state", "active", "payment_state", "invoice_status", "delivery_status"},
    "dates": {
        "date",
        "date_order",
        "create_date",
        "write_date",
        "invoice_date",
        "date_done",
        "scheduled_date",
        "effective_date",
        "commitment_date",
        "validity_date",
    },
    "amounts": {
        "amount_total",
        "amount_untaxed",
        "amount_tax",
        "price_total",
        "price_subtotal",
        "price_unit",
        "balance",
        "debit",
        "credit",
        "residual",
        "quantity",
        "product_uom_qty",
        "qty_done",
        "qty_delivered",
        "qty_invoiced",
        "qty_available",
    },
    "people": {
        "user_id",
        "salesman_id",
        "partner_id",
        "commercial_partner_id",
        "employee_id",
        "responsible_id",
        "manager_id",
        "create_uid",
        "write_uid",
    },
    "product": {
        "product_id",
        "product_tmpl_id",
        "product_template_id",
        "product_variant_id",
        "product_variant_ids",
        "categ_id",
        "category_id",
        "uom_id",
        "product_uom",
        "product_uom_id",
        "product_uom_qty",
    },
    "sales": {
        "order_id",
        "order_line",
        "sale_id",
        "sale_order_id",
        "sale_line_id",
        "invoice_lines",
        "invoice_ids",
        "team_id",
        "warehouse_id",
    },
    "accounting": {
        "move_id",
        "move_line_ids",
        "line_ids",
        "journal_id",
        "account_id",
        "payment_id",
        "move_type",
        "payment_state",
        "partner_bank_id",
        "currency_id",
        "company_currency_id",
    },
    "stock": {
        "picking_id",
        "picking_ids",
        "picking_type_id",
        "move_ids",
        "move_line_ids",
        "location_id",
        "location_dest_id",
        "warehouse_id",
        "lot_id",
        "quant_id",
    },
    "purchase": {
        "purchase_id",
        "purchase_order_id",
        "purchase_line_id",
        "purchase_line_ids",
        "partner_id",
        "vendor_id",
        "supplier_id",
    },
    "hr": {
        "employee_id",
        "department_id",
        "job_id",
        "holiday_status_id",
        "request_date_from",
        "request_date_to",
        "number_of_days",
        "parent_id",
        "user_id",
    },
    "crm": {
        "lead_id",
        "opportunity_id",
        "stage_id",
        "probability",
        "expected_revenue",
        "campaign_id",
        "source_id",
        "medium_id",
        "team_id",
        "user_id",
        "partner_id",
    },
    "company_context": {"company_id", "company_ids", "currency_id"},
}
SKIP_FIELD_PREFIXES = (
    "message_",
    "activity_",
    "website_",
    "access_",
    "avatar_",
    "image_",
)

SKIP_FIELD_EXACT = {
    "__last_update",
    "write_uid",
    "write_date",
    "create_uid",
    "create_date",
    "display_name",
    "has_message",
    "message_ids",
    "message_follower_ids",
    "message_partner_ids",
    "website_message_ids",
}


def compact_candidate(candidate, question="", candidate_model_names=None):
    candidate_model_names = set(candidate_model_names or [])
    q = question.lower()
    q_tokens = set(q.replace("'", " ").replace("-", " ").split())

    all_important_fields = set()
    for fields in IMPORTANT_FIELDS.values():
        all_important_fields.update(fields)

    def should_skip_field(field_name):
        if field_name in SKIP_FIELD_EXACT:
            return True
        return any(field_name.startswith(prefix) for prefix in SKIP_FIELD_PREFIXES)

    selected_fields = []
    selected_relations = []

    fields = candidate.get("fields", [])
    relations = candidate.get("relations", [])

    for field in fields:
        field_name = field if isinstance(field, str) else field.get("name", "")
        if not field_name or should_skip_field(field_name):
            continue

        score = 0

        if field_name in all_important_fields:
            score += 5

        if field_name.lower() in q:
            score += 6

        field_parts = set(field_name.lower().replace("_", " ").split())
        if field_parts & q_tokens:
            score += 2

        if score > 0:
            selected_fields.append((score, field_name))

    for rel in relations:
        rel_text = str(rel).lower()

        score = 0

        if any(skip in rel_text for skip in ["mail.", "ir.", "bus.", "web.", "base."]):
            continue

        if any(model in rel_text for model in candidate_model_names):
            score += 5

        if any(
                word in rel_text
                for word in [
                    "user",
                    "partner",
                    "product",
                    "order",
                    "invoice",
                    "move",
                    "line",
                    "company",
                    "employee",
                    "payment",
                    "picking",
                    "stock",
                    "purchase",
                    "sale",
                ]
        ):
            score += 3

        if any(token in rel_text for token in q_tokens):
            score += 2

        if score > 0:
            selected_relations.append((score, rel))

    selected_fields = [
        field
        for score, field in sorted(selected_fields, key=lambda x: x[0], reverse=True)
    ][:25]

    selected_relations = [
        rel
        for score, rel in sorted(selected_relations, key=lambda x: x[0], reverse=True)
    ][:15]

    return {
        "model_name": candidate.get("model_name"),
        "score": candidate.get("score"),
        "source": candidate.get("source"),
        "description_enrichie": candidate.get("description_enrichie", "")[:600],
        "fields": selected_fields,
        "relations": selected_relations,
    }


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
    top_k: int = Field(
        default=8, description="Nombre de modèles candidats à retourner (défaut 8)."
    )


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
def search_similar_models(question: str, top_k: int = 25) -> str:
    """
    — Recherche par similarité vectorielle dans Qdrant.

    Retourne les modèles Odoo les plus proches sémantiquement de la question,
    avec leur score de similarité et leur description fonctionnelle.

    APPELLE CET OUTIL EN PREMIER, avant select_models et get_models_schema.

    Exemple :
      'factures clients impayées'
        → account.move (0.85), account.payment (0.71), res.partner (0.65)...
    """
    try:
        vector = _get_embedding(question)

        results = _qdrant.query_points(
            collection_name=_COLLECTION_NAME,
            query=vector,
            limit=top_k,
        ).points

        vector_candidates = []

        for r in results:
            payload = r.payload or {}
            vector_candidates.append(
                {
                    "model_name": payload.get("model_name"),
                    "score": round(float(r.score), 3),
                    "source": "vector",
                    "description_enrichie": payload.get("description_enrichie", ""),
                    "fields": payload.get("fields", []),
                    "relations": payload.get("relations", []),
                }
            )

        required_models = detect_required_models(question)
        rule_candidates = get_rule_candidates(required_models)

        merged = {}

        for c in vector_candidates + rule_candidates:
            model_name = c.get("model_name")
            if not model_name:
                continue

            if model_name not in merged:
                merged[model_name] = c
            else:
                if c.get("source") == "rule":
                    merged[model_name]["source"] = "vector+rule"
                    merged[model_name]["score"] = max(
                        merged[model_name]["score"], c["score"]
                    )

        final_candidates = list(merged.values())

        # Ajouter les modèles liés aux candidats trouvés
        final_candidates = expand_candidates_with_relations(final_candidates, depth=1)

        candidate_model_names = [
            c.get("model_name") for c in final_candidates if c.get("model_name")
        ]

        final_candidates = [
            compact_candidate(c, question, candidate_model_names)
            for c in final_candidates
        ]

        return json.dumps(final_candidates[:20], ensure_ascii=False)

    except Exception as e:
        logger.error("[search_similar_models] %s", e)
        return f"Erreur recherche vectorielle : {e}"


@tool(args_schema=SelectModelsInput)
def select_models(question: str, candidates: str) -> str:
    """
    — Demande au LLM de choisir les modèles pertinents parmi les candidats.

    Prend en entrée la question et les candidats retournés par search_similar_models.
    Retourne uniquement les noms de modèles strictement nécessaires pour répondre.

    APPELLE CET OUTIL après search_similar_models, avant get_models_schema.

    Exemple :
      Candidats : [account.move, account.payment, res.partner, ...]
      Question  : 'factures clients impayées'
        → Sélection : ['account.move', 'res.partner']
    """
    try:
        try:
            if isinstance(candidates, list):
                raw_list = candidates
            else:
                raw_list = json.loads(candidates)

            #  Fix : normaliser peu importe ce que l'agent a passé
            candidates_list = []
            for item in raw_list:
                if isinstance(item, dict):
                    # Format complet : {"model_name": ..., "score": ..., "description_enrichie": ...}
                    candidates_list.append(item)
                elif isinstance(item, str):
                    # Format dégradé : l'agent a passé juste les noms → reconstruire depuis le schéma
                    candidates_list.append(
                        {
                            "model_name": item,
                            "score": 0.0,
                            "description_enrichie": _SCHEMA.get(item, {}).get(
                                "description_enrichie", ""
                            ),
                        }
                    )
        except Exception as e:
            logger.error("[select_models] %s", e)

        system_prompt = (
            system_prompt
        ) = """Tu es un expert Odoo ERP et modélisation de données.

On te donne :
1. une question métier posée par un utilisateur
2. une liste de modèles candidats issus d'une recherche RAG/vectorielle, de règles métier et/ou d'une expansion relationnelle

Chaque candidat peut contenir :
- model_name
- score
- source : vector, rule, vector+rule, relation_expansion
- description_enrichie
- fields
- relations

Ta mission :
sélectionner les modèles Odoo nécessaires pour répondre correctement à la question.

═══════════════════════════════════════
PRINCIPE IMPORTANT
═══════════════════════════════════════

Ne sélectionne pas seulement les modèles qui ressemblent sémantiquement à la question.

Tu dois sélectionner les modèles nécessaires pour relier :

1. le FILTRE demandé
   Exemple : default_code, date, état, client, produit, employé, société

2. l'ÉVÉNEMENT ou DOCUMENT métier
   Exemple : vente, facture, paiement, livraison, achat, congé, stock

3. la SORTIE attendue
   Exemple : vendeur, client, produit, montant, quantité, personne, utilisateur

4. les MODÈLES-PONTS nécessaires
   Exemple : sale.order.line relie produit vendu et commande
             sale.order relie commande et vendeur
             account.move.line relie facture et produit/comptes

Un modèle peut être nécessaire même s'il n'est pas mentionné explicitement dans la question.

═══════════════════════════════════════
RÈGLES DE SÉLECTION
═══════════════════════════════════════

- Inclure le modèle qui contient le champ de filtre demandé.
- Inclure le modèle qui représente l'objet métier principal de la question.
- Inclure le modèle qui contient la sortie attendue.
- Inclure les modèles nécessaires pour connecter ces éléments par relations.
- Tu peux sélectionner des modèles avec source="relation_expansion" s'ils servent de pont relationnel.
- Ne supprime jamais un modèle relationnel important uniquement parce que son score vectoriel est faible.
- Si deux modèles produit sont possibles, garder product.product ET product.template.
- Si la question parle de vendeur, commercial, salesperson, personne qui a vendu, inclure res.users.
- Si la question parle de client, acheteur, contact, inclure res.partner.
- Si la question parle de produit vendu, quantité vendue ou référence produit dans une vente, inclure sale.order.line.
- Si la question parle de commande, vente, devis confirmé, montant de vente ou vendeur de commande, inclure sale.order.
- Si la question parle de facture, impayé, paiement client ou facture fournisseur, inclure account.move.
- Si la question parle de lignes de facture, produits facturés, comptes comptables ou montants détaillés, inclure account.move.line.
- Si la question parle de paiement ou règlement, inclure account.payment.
- Si la question parle de stock, disponibilité, mouvement ou livraison, inclure stock.quant, stock.move ou stock.picking selon les candidats disponibles.
- Si la question parle d'employé, RH, congé ou absence, inclure les modèles hr.* pertinents disponibles.
- Écarter les modèles techniques comme ir.*, mail.*, bus.*, base.*, web.* sauf s'ils sont indispensables pour répondre.
- Écarter les modèles de chatter, followers, messages, activités et pièces jointes sauf si la question les demande explicitement.
- En cas de doute entre un modèle métier principal et un modèle technique, privilégier le modèle métier.
- En cas de doute entre plusieurs modèles métier connectés, garde ceux qui sont nécessaires pour construire un chemin relationnel complet.

═══════════════════════════════════════
EXEMPLES DE RAISONNEMENT
═══════════════════════════════════════

Question :
"quelles sont les personnes qui ont vendu le produit ayant le default_code E-COM11"

Analyse :
- default_code est un filtre produit → product.product et/ou product.template
- vendu indique une vente réelle → sale.order.line
- la commande de vente peut porter le vendeur → sale.order
- personnes/vendeurs correspond aux utilisateurs commerciaux → res.users
- chemin relationnel possible :
  product.product/product.template ← sale.order.line → sale.order → res.users

Réponse :
{
  "selected_models": [
    "sale.order.line",
    "sale.order",
    "product.product",
    "product.template",
    "res.users"
  ],
  "reasoning": "Question sur les vendeurs d'un produit filtré par default_code : il faut les produits, les lignes de vente, les commandes et les utilisateurs vendeurs."
}

Question :
"quels sont les clients qui ont des factures impayées"

Analyse :
- factures impayées → account.move
- clients → res.partner
- filtre facture client : move_type/state/payment_state
- account.move contient généralement partner_id vers res.partner

Réponse :
{
  "selected_models": [
    "account.move",
    "res.partner"
  ],
  "reasoning": "Les factures client impayées sont dans account.move et les clients sont reliés via partner_id vers res.partner."
}

Question :
"quels produits ont été les plus vendus ce mois-ci"

Analyse :
- produits vendus et quantités → sale.order.line
- produit → product.product/product.template
- période/date et état de vente peuvent venir de sale.order via order_id
- agrégation par produit

Réponse :
{
  "selected_models": [
    "sale.order.line",
    "sale.order",
    "product.product",
    "product.template"
  ],
  "reasoning": "Le classement des produits vendus nécessite les lignes de vente, les produits et les commandes pour filtrer la période et l'état."
}

═══════════════════════════════════════
FORMAT DE SORTIE OBLIGATOIRE
═══════════════════════════════════════

Retourne UNIQUEMENT un JSON valide.
Pas de markdown.
Pas de texte avant ou après.
Pas de commentaires.

Format exact :
{
  "selected_models": ["model.a", "model.b"],
  "reasoning": "explication courte"
}
"""

        user_prompt = (
            f'Question : "{question}"\n\n'
            f"Candidats :\n{candidates_list}"
            f"Retourne uniquement le JSON de sélection."
        )

        try:
            llm = get_llm(LLMProvider.FIREWORKS_DEEPSEEK, temperature=0)
            response = llm.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except ResourceExhausted:
            llm = get_llm(LLMProvider.GROQ_QWEN3, temperature=0)
            response = llm.invoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )

        raw = response.content.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        selected = result.get("selected_models", [])
        reasoning = result.get("reasoning", "")

        logger.info(
            "[select_models] sélection: %s | raison: %s", selected, reasoning[:80]
        )
        return json.dumps(
            {"selected_models": selected, "reasoning": reasoning}, ensure_ascii=False
        )

    except Exception as e:
        logger.error("[select_models] %s", e)
        return f"Erreur sélection modèles : {e}"


@tool(args_schema=GetSchemaInput)
def get_models_schema(model_names: List[str]) -> str:
    """
    — Retourne le schéma exact (champs, types, relations) des modèles sélectionnés.

    Prend en entrée la liste retournée par select_models.
    Retourne un sous-schéma complet prêt à être utilisé pour construire les requêtes Odoo.

    APPELLE CET OUTIL après select_models, avant plan_query.

    Ce que tu obtiens :
      - Champs disponibles avec leur type et description
      - Relations many2one vers d'autres modèles (pour les jointures)
      - Description fonctionnelle de chaque modèle
    """
    try:
        schema_output = {}

        for model_name in model_names:
            if model_name not in _SCHEMA:
                logger.warning(
                    "[get_models_schema] modèle '%s' absent du schéma", model_name
                )
                continue

            model_data = _SCHEMA[model_name]
            fields_raw = model_data.get("fields", {})

            fields_clean = {}
            for field_name, field_data in fields_raw.items():
                if field_name in _SKIP_EXACT:
                    continue
                if any(field_name.startswith(p) for p in _SKIP_PREFIXES):
                    continue
                fields_clean[field_name] = {
                    "type": field_data.get("type", ""),
                    "description": field_data.get("description", ""),
                    **(
                        {"related_model": field_data["related_model"]}
                        if "related_model" in field_data
                        else {}
                    ),
                }

            schema_output[model_name] = {
                "description": model_data.get("description", ""),
                "description_enrichie": model_data.get("description_enrichie", ""),
                "fields": fields_clean,
            }

        if not schema_output:
            return "Aucun modèle trouvé dans le schéma."

        logger.info(
            "[get_models_schema] schéma retourné pour : %s", list(schema_output.keys())
        )
        return json.dumps(schema_output, ensure_ascii=False)

    except Exception as e:
        logger.error("[get_models_schema] %s", e)
        return f"Erreur récupération schéma : {e}"


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
        results = client.search_read(
            model, parsed, fields, limit or 80, order or ""
        )
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
