"""
Schema Retriever — cœur du système de compréhension du schéma Odoo.
Adapté pour fonctionner avec l'indexation enrichie (v2).
"""

import logging
from functools import lru_cache

from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "odoo_schema_v2"  # Nom de la nouvelle collection

TOP_K_SIMILARITY = 3
MIN_SCORE = 0.70
TRAVERSAL_DEPTH = 1

# ── Domaines métier et modèles "always_include" (Bilingue) ────────────────────

_DOMAIN_ALWAYS_INCLUDE: dict[str, list[str]] = {
    "hr": ["hr.leave", "hr.employee", "hr.department"],
    "stock": ["stock.location", "stock.quant"],
    "sale": ["sale.order", "sale.order.line"],
    "purchase": ["purchase.order", "purchase.order.line"],
    "account": ["account.move"],
}

_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "hr": ["congé", "absence", "employé", "salarié", "leave", "vacance", "holiday",
           "arrêt", "allocation", "rh", "paie", "contrat", "department", "staff"],
    "stock": ["stock", "quantité", "inventaire", "entrepôt", "lot", "série", "warehouse",
              "quant", "transfert", "livraison", "réception", "emplacement", "inventory"],
    "sale": ["vente", "commande", "devis", "client", "chiffre d'affaires", "deal",
             "facture client", "sale", "commercial", "quotation", "so"],
    "purchase": ["achat", "fournisseur", "bon de commande", "purchase", "vendor", "supplier"],
    "account": ["facture", "comptabilité", "paiement", "règlement", "journal", "billing",
                "écriture", "invoice", "account", "accounting", "payment"],
}

# ── Whitelist des relations autorisées ────────────────────────────────────────

TRAVERSAL_WHITELIST: set[str] = {
    "res.partner", "res.users", "res.country", "res.currency",
    "product.product", "product.template", "product.category",
    "stock.location", "stock.lot", "stock.quant", "stock.picking",
    "sale.order", "sale.order.line",
    "purchase.order", "purchase.order.line",
    "account.move", "account.account", "account.journal",
    "hr.employee", "hr.department", "hr.leave", "hr.leave.type", "hr.contract",
}

# ── Embedding ─────────────────────────────────────────────────────────────────

try:
    import ollama

    _EMBED_BACKEND = "ollama"
    EMBED_MODEL = "nomic-embed-text-v2-moe"
except ImportError:
    _EMBED_BACKEND = "openai"
    EMBED_MODEL = "text-embedding-3-small"


def _embed(text: str) -> list[float]:
    if _EMBED_BACKEND == "ollama":
        resp = ollama.embed(model=EMBED_MODEL, input=text)
        return resp["embeddings"][0]


@lru_cache(maxsize=1)
def _get_qdrant() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


# ── Helpers de détection ──────────────────────────────────────────────────────

def _detect_domain(question: str) -> str | None:
    q = question.lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return domain
    return None


def _get_always_include(question: str) -> list[str]:
    domain = _detect_domain(question)
    return _DOMAIN_ALWAYS_INCLUDE.get(domain, []) if domain else []


# ── Étape 1 : Recherche Sémantique ───────────────────────────────────────────

def _similarity_search(question: str, top_k: int = TOP_K_SIMILARITY) -> list[dict]:
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
        p = r.payload
        raw_score = round(r.score if hasattr(r, "score") else 0.0, 4)

        # Application du Boost is_core défini lors de l'indexation
        is_core = p.get("is_core", False)
        effective_score = round(min(raw_score * 1.15, 1.0), 4) if is_core else raw_score

        if effective_score < MIN_SCORE:
            continue

        found.append({
            "model_name": p["model_name"],
            "description": p.get("description", ""),
            "text": p.get("text", ""),  # Nouveau champ textuel enrichi
            "score": effective_score,
            "is_core": is_core
        })
    return found


# ── Étape 2 : Graph Traversal ────────────────────────────────────────────────

def _fetch_model_payload(model_name: str) -> dict | None:
    client = _get_qdrant()
    results = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter={"must": [{"key": "model_name", "match": {"value": model_name}}]},
        limit=1,
        with_payload=True,
    )
    points = results[0]
    if not points: return None
    p = points[0].payload
    return {
        "model_name": p["model_name"],
        "description": p.get("description", ""),
        "text": p.get("text", ""),
        "score": 0.0,
    }


def _graph_traversal(seed_models: list[dict], depth: int = TRAVERSAL_DEPTH) -> dict[str, dict]:
    all_models: dict[str, dict] = {m["model_name"]: m for m in seed_models}
    frontier = list(all_models.keys())

    for _ in range(depth):
        next_frontier = []
        for model_name in frontier:
            # Extraction des relations depuis le texte indexé (v2 stocke les relations dans le texte)
            # ou via une clé 'relations' si vous l'avez gardée en metadata.
            # Ici on se base sur la whitelist pour chercher les liens mentionnés.
            doc_text = all_models[model_name].get("text", "")

            for target_model in TRAVERSAL_WHITELIST:
                if target_model in all_models: continue
                # On cherche si le modèle cible est mentionné comme relation dans le texte
                if f"Linked to {target_model}" in doc_text:
                    payload = _fetch_model_payload(target_model)
                    if payload:
                        payload["added_by_traversal"] = True
                        payload["traversal_from"] = model_name
                        all_models[target_model] = payload
                        next_frontier.append(target_model)
        frontier = next_frontier
    return all_models


# ── Étape 3 : Assemblage du Prompt LLM ────────────────────────────────────────

_FIELD_ANNOTATIONS = {
    "sale.order.line": {"product_id": "⚠ Utilisez product_id.product_tmpl_id pour filtrer par article général."},
    "hr.leave": {"state": "⚠ Filtrez state=['validate'] pour les congés approuvés."},
    "account.move": {"move_type": "⚠ out_invoice=Client, in_invoice=Fournisseur."},
}


def _build_subschema_text(models: dict[str, dict]) -> str:
    lines = ["=== SOUS-SCHÉMA ODOO OPTIMISÉ (RAG v2) ===\n"]

    # Tri : Core models en premier, puis par score
    sorted_models = sorted(
        models.values(),
        key=lambda m: (m.get("is_core", False), m.get("score", 0.0)),
        reverse=True
    )

    for m in sorted_models:
        m_name = m["model_name"]
        origin = f"(Score: {m['score']})" if m.get("score", 0) > 0 else "(Relation contextuelle)"

        lines.append(f"MODEL: {m_name} | {m['description']} {origin}")

        # On injecte le doc_text (qui contient déjà les champs et relations formatés)
        doc_lines = m["text"].split("\n")
        for dl in doc_lines:
            if dl.startswith("Technical Model:") or dl.startswith("Business Label:"):
                continue  # Évite les doublons

            lines.append(dl)

            # Injection des annotations de sécurité/métier
            for field, note in _FIELD_ANNOTATIONS.get(m_name, {}).items():
                if f" {field} " in dl or f" {field}:" in dl:
                    lines.append(f"    {note}")

        lines.append("-" * 40)

    return "\n".join(lines)


# ── API Publique ──────────────────────────────────────────────────────────────

def retrieve_schema_for_question(question: str, top_k: int = TOP_K_SIMILARITY) -> str:
    logger.info("[Retriever] Recherche pour: %s", question)

    # 1. Similarité sémantique
    seed_models = _similarity_search(question, top_k=top_k)

    # 2. Ajout des incontournables (Always Include)
    always_models = _get_always_include(question)
    for m_name in always_models:
        if not any(sm["model_name"] == m_name for sm in seed_models):
            p = _fetch_model_payload(m_name)
            if p: seed_models.append(p)

    # 3. Expansion des relations (Graph Traversal)
    all_models = _graph_traversal(seed_models)

    # 4. Génération du texte final
    return _build_subschema_text(all_models)
