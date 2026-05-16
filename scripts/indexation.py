"""
Script d'indexation one-shot du schéma Odoo dans Qdrant.

Usage :
    python schema_indexer.py --schema data/schema_odoo.json
    python schema_indexer.py --schema data/schema_odoo.json --reset   # recrée la collection

Ce script :
1. Lit schema_odoo.json
2. Filtre les modèles techniques/non-métier  ← amélioration #1
3. Filtre les champs techniques/bruits
4. Construit un texte enrichi avec synonymes métier  ← amélioration #2
5. Embedde via Ollama (nomic-embed-text) ou OpenAI selon config
6. Stocke dans Qdrant avec metadata is_core pour boost  ← amélioration #3
"""

import argparse
import json
import logging
import re
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Qdrant ─────────────────────────────────────────────────────────────────────
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# ── Embedding ─────────────────────────────────────────────────────────────────
try:
    import ollama
    _EMBED_BACKEND = "ollama"
except ImportError:
    _EMBED_BACKEND = None

try:
    from openai import OpenAI
    if _EMBED_BACKEND is None:
        _EMBED_BACKEND = "openai"
except ImportError:
    pass

# ── Configuration ──────────────────────────────────────────────────────────────

QDRANT_URL         = "http://localhost:6333"
COLLECTION_NAME    = "odoo_schema"
EMBED_MODEL_OLLAMA = "nomic-embed-text-v2-moe"        # 768 dims
EMBED_DIM_OLLAMA   = 768
EMBED_DIM_OPENAI   = 1536
BATCH_SIZE         = 50

# ── Filtres de bruit — champs ──────────────────────────────────────────────────

NOISE_FIELD_PREFIXES = (
    "activity_", "message_", "mail_", "website_", "access_",
    "campaign_", "medium_", "source_", "image_", "avatar_",
    "can_", "has_", "display_", "__",
)
NOISE_FIELD_EXACT = {
    "create_uid", "write_uid", "create_date", "write_date",
    "color", "active", "display_name", "__last_update",
}
SKIP_TYPES = {"binary", "html", "one2many", "many2many"}
NOISE_RELATION_MODELS = {
    "calendar.event", "mail.activity.type", "mail.activity",
    "res.company", "res.currency", "uom.uom", "uom.category",
    "utm.campaign", "utm.medium", "utm.source",
    "account.incoterms", "account.fiscal.position",
    "product.pricelist", "product.pricelist.item",
    "procurement.group", "stock.route", "stock.location",
    "stock.warehouse", "resource.calendar", "resource.resource",
    "ir.actions.actions",
}
MAX_FIELDS_PER_MODEL = 70

# ── AMÉLIORATION #1 — Filtre modèles techniques ───────────────────────────────

SKIP_MODEL_PREFIXES = (
    "web_editor.",
    "ir.qweb.",
    "ir.actions.",
    "ir.ui.",
    "ir.model.",
    "report.",
    "publisher_warranty.",
    "account.edi.",
    "base_setup.",
    "base_import.",
    "bus.",
    "phone_validation.",
    "rating.",
)

SKIP_MODEL_EXACT = {
    "mail.activity.mixin",
    "mail.thread",
    "portal.mixin",
    "rating.mixin",
    "web_editor.converter.test",
    "web_editor.converter.test.sub",
    "ir.rule",
    "ir.filters",
}

MIN_BUSINESS_FIELDS = 3   # modèles avec moins de N champs métier → skip


def should_index_model(model_name: str, meta: dict) -> bool:
    """
    Retourne False pour les modèles techniques, mixins, rapports générés,
    ou trop vides pour être utiles à un agent SQL.
    """
    if model_name in SKIP_MODEL_EXACT:
        return False
    if any(model_name.startswith(p) for p in SKIP_MODEL_PREFIXES):
        return False

    # Compter les champs métier réels
    fields = meta.get("fields", {})
    business_fields = [
        fname for fname, finfo in fields.items()
        if finfo.get("type") not in SKIP_TYPES
        and fname not in NOISE_FIELD_EXACT
        and not any(fname.startswith(p) for p in NOISE_FIELD_PREFIXES)
    ]
    if len(business_fields) < MIN_BUSINESS_FIELDS:
        return False

    return True


# ── AMÉLIORATION #2 — Synonymes métier ───────────────────────────────────────

# FR + EN pour maximiser la similarité quelle que soit la langue de la question
MODEL_SYNONYMS: dict[str, str] = {
    "hr.leave":              "congés absences vacances arrêt maladie time off leaves holiday",
    "hr.leave.allocation":   "allocation congés quota solde droits leave allocation",
    "hr.employee":           "employé salarié personnel collaborateur agent employee staff",
    "hr.contract":           "contrat salaire rémunération paie wage salary contract",
    "hr.department":         "département service équipe team department",
    "hr.payslip":            "fiche de paie bulletin salaire payslip",
    "sale.order":            "vente commande bon de commande devis sale order quotation",
    "sale.order.line":       "ligne commande produit vendu sale order line item",
    "account.move":          "facture invoice comptabilité avoir credit note payment",
    "account.move.line":     "ligne facture écriture comptable journal entry",
    "account.payment":       "paiement règlement virement payment",
    "purchase.order":        "achat commande fournisseur purchase order",
    "purchase.order.line":   "ligne achat fournisseur purchase order line",
    "product.template":      "produit article catalogue fiche produit product",
    "product.product":       "variante produit SKU product variant",
    "stock.quant":           "stock quantité inventaire entrepôt quantity on hand",
    "stock.picking":         "transfert livraison réception mouvement stock picking",
    "stock.move":            "mouvement stock entrée sortie stock move",
    "project.project":       "projet project",
    "project.task":          "tâche ticket todo task issue",
    "project.milestone":     "jalon milestone livrable",
    "crm.lead":              "opportunité prospect pipeline lead CRM affaire",
    "res.partner":           "client fournisseur contact partenaire partner customer",
    "res.users":             "utilisateur user connexion login",
    "mrp.production":        "ordre fabrication production manufacturing order",
    "mrp.bom":               "nomenclature liste composants bill of materials BOM",
}


# ── AMÉLIORATION #3 — Core models (metadata pour boost retrieval) ─────────────

CORE_MODELS: set[str] = {
    # RH
    "hr.leave", "hr.leave.allocation", "hr.employee", "hr.contract",
    "hr.department", "hr.payslip", "hr.job",
    # Ventes
    "sale.order", "sale.order.line",
    # Comptabilité
    "account.move", "account.move.line", "account.payment",
    # Achats
    "purchase.order", "purchase.order.line",
    # Produits / Stock
    "product.template", "product.product",
    "stock.quant", "stock.picking", "stock.move",
    # Projets
    "project.project", "project.task",
    # CRM
    "crm.lead",
    # Partenaires
    "res.partner", "res.users",
    # Fabrication
    "mrp.production", "mrp.bom",
}


# ── Chargement du schéma ──────────────────────────────────────────────────────

def load_schema(path: str) -> dict:
    logger.info("Chargement du schéma : %s", path)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    fixed = re.sub(r",\s*([}\]])", r"\1", content)
    schema = json.loads(fixed)
    logger.info("%d modèles chargés", len(schema))
    return schema


# ── Construction du texte de document ────────────────────────────────────────

def build_document_text(model_name: str, meta: dict) -> str:
    """
    Construit le texte enrichi d'un modèle Odoo à indexer dans Qdrant.

    Format :
        model: hr.leave
        label: Time Off
        synonyms: congés absences vacances ...     ← nouveau
        fields:
          state (selection) : Status
          ...
        relations (many2one):
          employee_id -> hr.employee : Employee
          ...
    """
    fields = meta.get("fields", {})
    lines = [
        f"model: {model_name}",
        f"label: {meta.get('description', model_name)}",
    ]

    # ── Synonymes métier (amélioration #2)
    if model_name in MODEL_SYNONYMS:
        lines.append(f"synonyms: {MODEL_SYNONYMS[model_name]}")

    field_lines = []
    rel_lines   = []

    for fname, finfo in fields.items():
        ftype = finfo.get("type", "")
        if ftype in SKIP_TYPES:
            continue
        if fname in NOISE_FIELD_EXACT:
            continue
        if any(fname.startswith(p) for p in NOISE_FIELD_PREFIXES):
            continue

        label = finfo.get("description", fname)

        if ftype == "many2one":
            rel = finfo.get("related_model", "")
            if rel and rel not in NOISE_RELATION_MODELS:
                rel_lines.append(f"  {fname} -> {rel} : {label}")
        else:
            field_lines.append(f"  {fname} ({ftype}) : {label}")

    lines.append("fields:")
    lines.extend(field_lines[:MAX_FIELDS_PER_MODEL])

    if rel_lines:
        lines.append("relations (many2one):")
        lines.extend(rel_lines)

    return "\n".join(lines)


def extract_business_relations(meta: dict) -> dict[str, str]:
    """Retourne {field_name: related_model} pour les relations métier uniquement."""
    fields = meta.get("fields", {})
    result = {}
    for fname, finfo in fields.items():
        if finfo.get("type") != "many2one":
            continue
        rel = finfo.get("related_model", "")
        if not rel or rel in NOISE_RELATION_MODELS:
            continue
        if any(fname.startswith(p) for p in NOISE_FIELD_PREFIXES):
            continue
        if fname in NOISE_FIELD_EXACT:
            continue
        result[fname] = rel
    return result


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_text(text: str) -> list[float]:
    if _EMBED_BACKEND == "ollama":
        resp = ollama.embed(model=EMBED_MODEL_OLLAMA, input=text)
        return resp["embeddings"][0]


    raise RuntimeError(
        "Aucun backend d'embedding disponible. "
        "Installez ollama ou openai : pip install ollama / pip install openai"
    )


def get_embed_dim() -> int:
    return EMBED_DIM_OLLAMA if _EMBED_BACKEND == "ollama" else EMBED_DIM_OPENAI


# ── Qdrant helpers ────────────────────────────────────────────────────────────

def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: QdrantClient, reset: bool = False) -> None:
    exists = any(c.name == COLLECTION_NAME for c in client.get_collections().collections)

    if exists and reset:
        logger.info("Suppression de la collection existante '%s'", COLLECTION_NAME)
        client.delete_collection(COLLECTION_NAME)
        exists = False

    if not exists:
        dim = get_embed_dim()
        logger.info("Création de la collection '%s' (dim=%d)", COLLECTION_NAME, dim)
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
    else:
        logger.info("Collection '%s' déjà existante — skip création", COLLECTION_NAME)


# ── Indexation ────────────────────────────────────────────────────────────────

def index_schema(schema: dict, client: QdrantClient) -> None:
    """Embedde et indexe tous les modèles métier dans Qdrant par batch."""
    models   = list(schema.items())
    total    = len(models)
    points   = []
    inserted = 0
    skipped  = 0
    point_id = 0   # ID séquentiel sur les modèles retenus uniquement

    logger.info("Début de l'indexation de %d modèles (batch=%d)…", total, BATCH_SIZE)

    for model_name, meta in models:

        # ── Amélioration #1 — filtre modèles non-métier
        if not should_index_model(model_name, meta):
            logger.debug("Skip modèle technique : %s", model_name)
            skipped += 1
            continue

        doc_text  = build_document_text(model_name, meta)   # synonymes inclus (#2)
        relations = extract_business_relations(meta)
        is_core   = model_name in CORE_MODELS               # metadata pour boost (#3)

        try:
            vector = embed_text(doc_text)
        except Exception as exc:
            logger.warning("Embedding échoué pour '%s' : %s — skip", model_name, exc)
            skipped += 1
            continue

        points.append(PointStruct(
            id=point_id,
            vector=vector,
            payload={
                "model_name": model_name,
                "label":      meta.get("description", model_name),
                "doc_text":   doc_text,
                "relations":  relations,
                "is_core":    is_core,   # ← utilisé par schema_retriever pour le boost
            },
        ))
        point_id += 1

        # Flush par batch
        if len(points) >= BATCH_SIZE:
            client.upsert(collection_name=COLLECTION_NAME, points=points)
            inserted += len(points)
            logger.info("  %d modèles indexés (skip: %d)…", inserted, skipped)
            points = []
            time.sleep(0.1)

    # Dernier batch
    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)
        inserted += len(points)

    logger.info(
        "Indexation terminée : %d insérés, %d skippés (sur %d total).",
        inserted, skipped, total,
    )


# ── Entrée ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Indexation du schéma Odoo dans Qdrant")
    parser.add_argument("--schema", default="schema_odoo.json", help="Chemin vers schema_odoo.json")
    parser.add_argument("--reset", action="store_true", help="Supprime et recrée la collection avant d'indexer")
    args = parser.parse_args()

    schema = load_schema(args.schema)
    client = get_qdrant_client()
    ensure_collection(client, reset=args.reset)
    index_schema(schema, client)


if __name__ == "__main__":
    main()
