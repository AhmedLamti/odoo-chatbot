"""
Script d'indexation Odoo -> Qdrant optimisé.
Corrections apportées :
1. Gestion bilingue (EN/FR) renforcée dans le texte du document.
2. Inclusion légère des relations o2m/m2m pour le contexte sans le bruit.
3. Priorisation des champs métier lors de la troncature (évite de perdre les champs importants).
4. Nettoyage des labels génériques (Name, ID) pour éviter la dilution sémantique.
5. Exemple de fonction de recherche avec boost 'is_core'.
"""

import argparse
import json
import logging
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Qdrant & Embedding ────────────────────────────────────────────────────────
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams, Filter, FieldCondition, MatchValue

try:
    import ollama

    _EMBED_BACKEND = "ollama"
except ImportError:
    _EMBED_BACKEND = "openai"  # Fallback vers OpenAI par défaut si ollama absent

# ── Configuration ──────────────────────────────────────────────────────────────

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "odoo_schema_v2"
EMBED_MODEL_OLLAMA = "nomic-embed-text-v2-moe"
EMBED_DIM_OLLAMA = 768
EMBED_DIM_OPENAI = 1536
BATCH_SIZE = 50

# ── Filtres et Priorités ──────────────────────────────────────────────────────

# Champs à ignorer totalement
NOISE_FIELD_PREFIXES = ("activity_", "message_", "mail_", "website_", "access_", "campaign_", "medium_", "source_",
                        "image_", "avatar_", "can_", "has_", "display_", "__")
NOISE_FIELD_EXACT = {"create_uid", "write_uid", "create_date", "write_date", "color", "active", "display_name",
                     "__last_update", "id"}

# Modèles techniques à ignorer
SKIP_MODEL_PREFIXES = ("web_editor.", "ir.qweb.", "ir.actions.", "ir.ui.", "ir.model.", "report.",
                       "publisher_warranty.", "account.edi.", "base_setup.", "base_import.", "bus.",
                       "phone_validation.", "rating.")

# Types de champs légers (on indexe juste le nom de la relation)
RELATIONAL_TYPES = {"one2many", "many2many"}

# Mots-clés de labels génériques à dé-prioriser pour éviter la dilution
GENERIC_LABELS = {"name", "type", "id", "display name", "nom", "état", "status"}

# ── AMÉLIORATION : Synonymes enrichis (EN/FR) ────────────────────────────────

MODEL_SYNONYMS = {
    "hr.leave": "congés absences vacances arrêt maladie time off leaves holiday absence management",
    "hr.employee": "employé salarié personnel collaborateur agent employee staff worker human resources",
    "sale.order": "vente commande bon de commande devis sale order quotation so deals",
    "account.move": "facture invoice comptabilité avoir credit note payment billing accounting",
    "product.template": "produit article catalogue fiche produit product item master sku",
    "res.partner": "client fournisseur contact partenaire partner customer vendor supplier",
    "stock.quant": "stock quantité inventaire entrepôt quantity on hand warehouse inventory",
}

CORE_MODELS = {
    "hr.leave", "hr.employee", "hr.contract", "sale.order", "sale.order.line",
    "account.move", "account.move.line", "purchase.order", "product.template",
    "stock.quant", "project.task", "crm.lead", "res.partner"
}


# ── Fonctions Utilitaires ─────────────────────────────────────────────────────

def load_schema(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    fixed = re.sub(r",\s*([}\]])", r"\1", content)
    return json.loads(fixed)


def embed_text(text: str) -> list[float]:
    if _EMBED_BACKEND == "ollama":
        return ollama.embed(model=EMBED_MODEL_OLLAMA, input=text)["embeddings"][0]
    # Implémentation OpenAI si nécessaire...
    return []


# ── AMÉLIORATION : Construction du document texte ───────────────────────────

def build_enhanced_document(model_name: str, meta: dict) -> str:
    """
    Construit un document texte optimisé :
    - Incorpore les noms techniques (langue universelle).
    - Priorise les champs métier.
    - Ajoute les relations o2m/m2m sans détails excessifs.
    """
    fields = meta.get("fields", {})
    description = meta.get("description", model_name)

    lines = [
        f"Technical Model: {model_name}",
        f"Business Label: {description}",
    ]

    if model_name in MODEL_SYNONYMS:
        lines.append(f"Keywords: {MODEL_SYNONYMS[model_name]}")

    biz_fields = []
    rel_fields = []

    for fname, finfo in fields.items():
        ftype = finfo.get("type", "")
        flabel = finfo.get("description", "").lower()

        # Filtrage du bruit
        if fname in NOISE_FIELD_EXACT or any(fname.startswith(p) for p in NOISE_FIELD_PREFIXES):
            continue

        # Gestion des relations (o2m/m2m) pour le contexte
        if ftype in RELATIONAL_TYPES:
            rel_model = finfo.get("related_model", "unknown")
            rel_fields.append(f"  - Linked to {rel_model} ({fname})")
            continue

        # Filtrage des types binaires/HTML lourds
        if ftype in ["binary", "html"]:
            continue

        # Formatage : Nom technique + Label pour le bilinguisme
        # Si le label est trop générique, on lui donne moins d'importance visuelle
        if flabel in GENERIC_LABELS:
            biz_fields.append((1, f"  - {fname} ({ftype})"))  # Priorité basse
        else:
            biz_fields.append((0, f"  - {fname}: {finfo.get('description')} ({ftype})"))  # Priorité haute

    # Tri par priorité (champs spécifiques en premier) et limitation à 80 champs
    biz_fields.sort(key=lambda x: x[0])
    lines.append("Business Fields:")
    lines.extend([f[1] for f in biz_fields[:80]])

    if rel_fields:
        lines.append("Relationships:")
        lines.extend(rel_fields[:20])

    return "\n".join(lines)


# ── Indexation Principale ─────────────────────────────────────────────────────

def index_schema(schema: dict, client: QdrantClient):
    points = []
    point_id = 0

    for model_name, meta in schema.items():
        # Filtrage des modèles techniques
        if any(model_name.startswith(p) for p in SKIP_MODEL_PREFIXES):
            continue

        # On vérifie si le modèle contient assez de substance
        if len(meta.get("fields", {})) < 3:
            continue

        doc_text = build_enhanced_document(model_name, meta)
        is_core = model_name in CORE_MODELS

        try:
            vector = embed_text(doc_text)
            points.append(PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "model_name": model_name,
                    "description": meta.get("description", ""),
                    "is_core": is_core,
                    "text": doc_text
                }
            ))
            point_id += 1
        except Exception as e:
            logger.error(f"Erreur embedding {model_name}: {e}")

        if len(points) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            points = []
            logger.info(f"Indexé {point_id} modèles...")

    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)


# ── AMÉLIORATION : Recherche avec Boost 'is_core' ───────────────────────────

def search_models(client: QdrantClient, query: str, limit: int = 5):
    """
    Exemple de recherche utilisant le score de similarité
    tout en favorisant les modèles 'core'.
    """
    query_vector = embed_text(query)

    # On récupère plus de résultats pour appliquer un reranking manuel sur le boost
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=limit * 2
    )

    final_results = []
    for res in results:
        score = res.score
        # Application d'un boost de 15% pour les modèles structurants (CORE)
        if res.payload.get("is_core"):
            score *= 1.15

        final_results.append({
            "model": res.payload["model_name"],
            "score": score,
            "original_score": res.score
        })

    # Tri par nouveau score boosté
    final_results.sort(key=lambda x: x["score"], reverse=True)
    return final_results[:limit]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", default="schema_odoo.json")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    client = QdrantClient(url=QDRANT_URL)

    if args.reset:
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBED_DIM_OLLAMA, distance=Distance.COSINE),
        )

    schema = load_schema(args.schema)
    index_schema(schema, client)
    logger.info("Indexation terminée avec succès.")


if __name__ == "__main__":
    main()
