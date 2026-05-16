"""
Schema Retriever — cœur du système de compréhension du schéma Odoo.

Deux responsabilités :
1. Recherche sémantique dans Qdrant pour trouver les modèles pertinents
2. Graph traversal contrôlé sur les relations many2one (depth=1, whitelist)

Utilisé par le tool get_schema_for_question dans tools.py.
"""

import logging
from functools import lru_cache

from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "odoo_schema"

TOP_K_SIMILARITY = 3  # ↓ était 5 — au-delà de 3, les matches sont marginaux
MIN_SCORE = 0.70  # ✦ nouveau — coupe les modèles faiblement liés
TRAVERSAL_DEPTH = 1  # ↓ était 2 — depth=2 cause une explosion combinatoire

# ── Domaines métier et leurs modèles "always_include" ─────────────────────────
#
# Principe : on n'inclut systématiquement un modèle QUE si la question
# appartient au même domaine. Plus de hr.leave sur une question stock.
#
_DOMAIN_ALWAYS_INCLUDE: dict[str, list[str]] = {
    "hr": ["hr.leave", "hr.employee", "hr.department"],
    "stock": ["stock.location"],
    "sale": ["sale.order", "sale.order.line"],
    "purchase": ["purchase.order", "purchase.order.line"],
    "account": ["account.move"],
}

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "hr": ["congé", "absence", "employé", "salarié", "leave", "vacance",
           "arrêt", "allocation", "rh", "paie", "contrat", "department"],
    "stock": ["stock", "quantité", "inventaire", "entrepôt", "lot", "série",
              "quant", "transfert", "livraison", "réception", "emplacement"],
    "sale": ["vente", "commande", "devis", "client", "chiffre d'affaires",
             "facture client", "sale", "commercial"],
    "purchase": ["achat", "fournisseur", "bon de commande", "purchase"],
    "account": ["facture", "comptabilité", "paiement", "règlement", "journal",
                "écriture", "invoice", "account"],
}

# ── Whitelist des relations autorisées à être suivies pendant le traversal ────
#
# Seuls les modèles de cette liste peuvent être ajoutés via graph traversal.
# Tout modèle absent est ignoré, même s'il est lié par many2one.
#
# Règle d'inclusion : modèle "feuille" ou "pont universel" dans Odoo.
# Modèles exclus : mrp.*, project.*, account.move.line, crm.*, mail.*
#
TRAVERSAL_WHITELIST: set[str] = {
    # Partenaires et utilisateurs
    "res.partner",
    "res.users",
    "res.country",
    # Produits
    "product.product",
    "product.template",
    "product.category",
    "product.packaging",
    # Stock
    "stock.location",
    "stock.lot",
    "stock.quant",
    "stock.picking",
    "stock.picking.type",
    # Ventes
    "sale.order",
    "sale.order.line",
    # Achats
    "purchase.order",
    "purchase.order.line",
    # Comptabilité (niveau haut uniquement)
    "account.move",
    "account.account",
    "account.journal",
    # RH
    "hr.employee",
    "hr.department",
    "hr.leave",
    "hr.leave.type",
    "hr.contract",
    "hr.job",
    # CRM
    "crm.team",
}

# ── Embedding (même backend que schema_indexer.py) ────────────────────────────

try:
    import ollama

    _EMBED_BACKEND = "ollama"
    EMBED_MODEL = "nomic-embed-text-v2-moe"
except ImportError:
    _EMBED_BACKEND = None

try:
    from openai import OpenAI

    if _EMBED_BACKEND is None:
        _EMBED_BACKEND = "openai"
        EMBED_MODEL = "text-embedding-3-small"
except ImportError:
    pass


def _embed(text: str) -> list[float]:
    if _EMBED_BACKEND == "ollama":
        resp = ollama.embed(model=EMBED_MODEL, input=text)
        return resp["embeddings"][0]
    elif _EMBED_BACKEND == "openai":
        client = OpenAI()
        resp = client.embeddings.create(model=EMBED_MODEL, input=text)
        return resp.data[0].embedding
    raise RuntimeError("Aucun backend d'embedding disponible.")


# ── Singletons ─────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _get_qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _detect_domain(question: str) -> str | None:
    """
    Détecte le domaine métier d'une question à partir des mots-clés.
    Retourne le nom du domaine ('hr', 'stock', 'sale'...) ou None.
    """
    q = question.lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            logger.debug("[schema_retriever] domaine détecté : '%s'", domain)
            return domain
    return None


def _get_always_include(question: str) -> list[str]:
    """
    Retourne les modèles à inclure systématiquement selon le domaine détecté.
    Retourne une liste vide si aucun domaine n'est reconnu.
    """
    domain = _detect_domain(question)
    if domain is None:
        return []
    return _DOMAIN_ALWAYS_INCLUDE.get(domain, [])


# ── Étape 1 : recherche sémantique ────────────────────────────────────────────

def _similarity_search(question: str, top_k: int = TOP_K_SIMILARITY) -> list[dict]:
    """
    Retourne les modèles les plus proches sémantiquement de la question,
    filtrés par MIN_SCORE pour couper les matches marginaux.

    Le score effectif applique un boost de 15% aux modèles is_core,
    ce qui compense les variations sémantiques sur les modèles centraux
    (ex: sale.order.line peut scorer 0.68 brut mais 0.78 après boost).

    Chaque résultat : {model_name, label, doc_text, relations, score}
    """
    vector = _embed(question)
    client = _get_qdrant()

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k,
        with_payload=True,
    )

    found = []
    for r in results.points:
        raw_score = round(r.score if hasattr(r, "score") else 0.0, 4)
        payload = r.payload if hasattr(r, "payload") else r[2]

        # ✦ Boost is_core — les modèles centraux bénéficient d'un bonus
        # pour compenser les variations de formulation de la question.
        # Le boost ne dépasse jamais 1.0 et n'est appliqué qu'aux core models.
        is_core = payload.get("is_core", False)
        effective_score = round(min(raw_score * 1.15, 1.0), 4) if is_core else raw_score

        # ✦ Filtrer les modèles sous le seuil de pertinence (score effectif)
        if effective_score < MIN_SCORE:
            logger.debug(
                "[schema_retriever] modèle ignoré (raw=%.4f effective=%.4f < %.2f) : %s",
                raw_score, effective_score, MIN_SCORE, payload["model_name"],
            )
            continue

        found.append({
            "model_name": payload["model_name"],
            "label": payload["label"],
            "doc_text": payload["doc_text"],
            "relations": payload.get("relations", {}),
            "score": effective_score,
        })

    return found


# ── Étape 2 : graph traversal ─────────────────────────────────────────────────

def _fetch_model_payload(model_name: str) -> dict | None:
    """
    Récupère le payload d'un modèle depuis Qdrant par son nom exact.
    Retourne None si le modèle n'existe pas dans la collection.
    """
    client = _get_qdrant()
    results = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter={
            "must": [{"key": "model_name", "match": {"value": model_name}}]
        },
        limit=1,
        with_payload=True,
    )
    points = results[0]
    if not points:
        return None
    p = points[0].payload
    return {
        "model_name": p["model_name"],
        "label": p["label"],
        "doc_text": p["doc_text"],
        "relations": p.get("relations", {}),
        "score": 0.0,
    }


def _graph_traversal(seed_models: list[dict], depth: int = TRAVERSAL_DEPTH) -> dict[str, dict]:
    """
    À partir des modèles seed, remonte leurs voisins directs via many2one,
    en respectant deux contraintes :

    1. TRAVERSAL_WHITELIST — seuls les modèles listés peuvent être ajoutés.
       Cela empêche l'expansion vers mrp.*, project.task, account.move.line...

    2. depth=1 recommandé — depth=2 multiplie les modèles inutiles.
       On ne suit pas les relations des modèles ajoutés par traversal.

    Retourne un dict {model_name: payload} contenant seed + voisins filtrés.
    """
    all_models: dict[str, dict] = {}

    for m in seed_models:
        all_models[m["model_name"]] = m

    frontier = list(all_models.keys())

    for current_depth in range(depth):
        next_frontier = []

        for model_name in frontier:
            model_data = all_models[model_name]
            relations = model_data.get("relations", {})

            for field, related_model in relations.items():

                # Déjà présent → skip
                if related_model in all_models:
                    continue

                # ✦ Whitelist — ignore les modèles hors périmètre
                if related_model not in TRAVERSAL_WHITELIST:
                    logger.debug(
                        "[schema_retriever] relation ignorée (hors whitelist) : %s.%s → %s",
                        model_name, field, related_model,
                    )
                    continue

                payload = _fetch_model_payload(related_model)
                if payload:
                    payload["added_by_traversal"] = True
                    payload["traversal_from"] = f"{model_name}.{field}"
                    all_models[related_model] = payload
                    next_frontier.append(related_model)

        frontier = next_frontier

    return all_models


# ── Étape 3 : assemblage du sous-schéma textuel ───────────────────────────────

_FIELD_ANNOTATIONS: dict[str, dict[str, str]] = {
    "sale.order.line": {
        # product_id pointe vers product.product (variante), pas product.template.
        # Pour filtrer par default_code (porté par product.template), il faut
        # traverser product_id.product_tmpl_id dans le domain — jamais dans fields.
        "product_id": (
            "⚠ product_id → product.product (variante), PAS product.template. "
            "Pour filtrer par default_code : domain=[['product_id.product_tmpl_id','=',<id_template>]]"
        ),
    },
    "hr.leave": {
        # Sans filtre sur state, on récupère brouillons, refusés, annulés.
        # validate1 = approuvé niveau 1 (double validation activée).
        "state": (
            "⚠ Congés validés uniquement : state in ['validate', 'validate1']. "
            "Sans ce filtre, les brouillons et refus sont inclus."
        ),
    },
    "sale.order": {
        # Sans filtre, les devis (draft/sent) sont inclus.
        "state": (
            "⚠ Ventes confirmées uniquement : state in ['sale', 'done']. "
            "Sans ce filtre, les devis sont inclus."
        ),
    },
    "account.move": {
        "move_type": (
            "⚠ Factures clients : move_type='out_invoice'. "
            "Factures fournisseurs : move_type='in_invoice'. "
            "Avoirs clients : move_type='out_refund'."
        ),
        "payment_state": (
            "⚠ Factures impayées : payment_state in ['not_paid', 'partial']. "
            "Factures payées : payment_state='paid'."
        ),
    },
    "res.partner": {
        "customer_rank": (
            "⚠ res.partner contient clients + fournisseurs + contacts mélangés. "
            "Clients uniquement : customer_rank > 0. "
            "Fournisseurs uniquement : supplier_rank > 0."
        ),
    },
}


def _build_subschema_text(models: dict[str, dict]) -> str:
    """
    Assemble le texte final injecté dans le prompt de l'agent.

    Format de sortie :
        === Sous-schéma Odoo pertinent ===

        [sale.order.line] Sales Order Line  (similarité: 0.87)
        fields:
          product_id (many2one → product.product) : Product
            ⚠ product_id → product.product (variante), PAS product.template...
          order_id (many2one → sale.order) : Order
          ...

    Les annotations de _FIELD_ANNOTATIONS sont injectées sous le champ concerné
    uniquement si ce modèle et ce champ sont présents dans le sous-schéma courant.
    """
    lines = ["=== Sous-schéma Odoo pertinent ===\n"]

    sorted_models = sorted(
        models.values(),
        key=lambda m: (m.get("added_by_traversal", False), -m.get("score", 0.0)),
    )

    for m in sorted_models:
        model_name = m["model_name"]
        model_annotations = _FIELD_ANNOTATIONS.get(model_name, {})

        origin = (
            f"(similarité: {m['score']})"
            if not m.get("added_by_traversal")
            else f"(ajouté via {m.get('traversal_from', 'traversal')})"
        )
        lines.append(f"[{model_name}] {m['label']}  {origin}")

        doc_lines = m["doc_text"].split("\n")
        for dl in doc_lines[2:]:  # skip "model:" et "label:"
            lines.append(dl)

            # Injecter l'annotation sous le champ concerné.
            # On détecte le nom du champ depuis la ligne de doc
            # (format attendu dans doc_text : "  field_name (type) : label")
            stripped = dl.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith(
                    "fields") and not stripped.startswith("relations"):
                field_name = stripped.split(" ")[0].split("(")[0].rstrip()
                if field_name in model_annotations:
                    lines.append(f"    {model_annotations[field_name]}")

        lines.append("")

    return "\n".join(lines)


# ── API publique ───────────────────────────────────────────────────────────────

def retrieve_schema_for_question(
        question: str,
        top_k: int = TOP_K_SIMILARITY,
        depth: int = TRAVERSAL_DEPTH,
) -> str:
    """
    Point d'entrée principal.

    Prend une question en langage naturel (FR/AR/EN) et retourne
    un sous-schéma Odoo textuel prêt à être injecté dans le prompt du LLM.

    Optimisations appliquées :
    - MIN_SCORE = 0.70 → filtre les modèles faiblement liés
    - TOP_K = 3        → limite les seeds à 3 modèles directs
    - depth = 1        → depth=2 était la cause de l'explosion combinatoire
    - TRAVERSAL_WHITELIST → bloque l'expansion vers mrp.*, project.task...
    - always_include conditionnel → hr.leave n'est plus inclus sur une question stock

    Args:
        question : Question de l'utilisateur
        top_k    : Nombre de modèles retournés par la similarité (défaut : 3)
        depth    : Profondeur du graph traversal (défaut : 1)

    Returns:
        Texte du sous-schéma (modèles + champs + relations)
    """
    logger.info("[schema_retriever] question='%s'", question[:80])

    # Étape 1 — similarité sémantique avec seuil MIN_SCORE
    seed_models = _similarity_search(question, top_k=top_k)
    logger.info(
        "[schema_retriever] similarité → %s",
        [f"{m['model_name']}({m['score']})" for m in seed_models],
    )

    if not seed_models:
        logger.warning("[schema_retriever] aucun modèle au-dessus du seuil %.2f", MIN_SCORE)

    # Étape 1b — always_include conditionnel par domaine détecté
    always_models = _get_always_include(question)
    for model_name in always_models:
        if not any(m["model_name"] == model_name for m in seed_models):
            payload = _fetch_model_payload(model_name)
            if payload:
                payload["added_by_traversal"] = True
                payload["traversal_from"] = "always_include"
                seed_models.append(payload)
                logger.debug("[schema_retriever] always_include ajouté : %s", model_name)

    # Étape 2 — graph traversal contrôlé (whitelist + depth=1)
    all_models = _graph_traversal(seed_models, depth=depth)
    logger.info(
        "[schema_retriever] après traversal → %d modèles : %s",
        len(all_models),
        list(all_models.keys()),
    )

    # Étape 3 — assemblage texte
    return _build_subschema_text(all_models)
