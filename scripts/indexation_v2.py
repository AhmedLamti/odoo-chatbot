import json
import hashlib
import time
import requests

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct


INPUT_FILE = "schema_odoo_enrichi_rag_complexe.json"

QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "odoo_schema_v3"

OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "bge-m3"
VECTOR_SIZE = 1024

BATCH_SIZE = 50
MAX_TEXT_CHARS = 5000

SKIP_PREFIXES = ("message_", "activity_", "website_")
SKIP_EXACT = {
    "__last_update",
    "create_uid",
    "create_date",
    "write_uid",
    "write_date",
    "display_name",
}


MODEL_BOOSTS = {
    "sale.order.line": "Requêtes produits vendus, lignes de vente, quantité vendue, chiffre d'affaires par produit, vendeur du produit, commercial ayant vendu un article, product_id, order_id, sales line.",
    "sale.order": "Requêtes vendeurs, commerciaux, commandes clients, ventes confirmées, chiffre d'affaires par commercial, user_id, salesperson, seller, sales order.",
    "product.template": "Requêtes produit par default_code, référence interne, fiche article, catalogue produit, template produit, product reference, SKU.",
    "product.product": "Requêtes variante produit, SKU, default_code, article vendu, produit stockable, product variant.",
    "res.users": "Requêtes vendeurs, commerciaux, utilisateurs internes, salesperson, seller, user_id, responsable de vente.",
    "hr.employee": "Requêtes employé, lien utilisateur-employé, vendeur employé, congés de l'employé, employee, staff member.",
    "hr.leave": "Requêtes congés pris, jours d'absence, demandes de congé, time off, leave request.",
    "hr.leave.allocation": "Requêtes solde de congés, jours alloués, droits de congé, leave balance, allocation.",
    "account.move": "Requêtes factures clients, factures fournisseurs, impayés, avoirs, invoice, vendor bill, unpaid invoice.",
    "account.move.line": "Requêtes lignes de facture, produits facturés, montants comptables, taxes, invoice line, journal item.",
    "res.partner": "Requêtes client, fournisseur, contact, tiers, partenaire commercial, customer, vendor, partner.",
}


IMPORTANT_KEYWORDS = [
    "product", "default_code", "sale", "order", "line", "user", "seller",
    "salesperson", "employee", "partner", "customer", "vendor", "client",
    "date", "state", "amount", "qty", "quantity", "price", "subtotal",
    "leave", "holiday", "department", "manager", "company",
    "invoice", "payment", "stock", "move", "picking",
    "name", "code", "reference", "template", "variant",
]


qdrant = QdrantClient(url=QDRANT_URL)


def model_name_to_id(model_name: str) -> int:
    return int(hashlib.md5(model_name.encode()).hexdigest()[:15], 16)


def get_embedding(text: str, mode: str = "document", retries: int = 3) -> list[float]:
    text = text[:MAX_TEXT_CHARS]

    prefix = "search_document" if mode == "document" else "search_query"

    payload = {
        "model": EMBEDDING_MODEL,
        "prompt": f"{prefix}: {text}",
    }

    for attempt in range(retries):
        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json=payload,
                timeout=90,
            )
            response.raise_for_status()
            return response.json()["embedding"]

        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            print(f"⚠️ Embedding tentative {attempt + 1}/{retries} — {e} — retry dans {wait}s")
            time.sleep(wait)

    raise RuntimeError("Impossible d'obtenir l'embedding.")


def clean_fields(fields: dict) -> dict:
    cleaned = {}

    for field_name, field_data in fields.items():
        if field_name in SKIP_EXACT:
            continue

        if any(field_name.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue

        cleaned[field_name] = field_data

    return cleaned


def extract_relations(fields: dict) -> list[str]:
    relations = []

    for field_name, field_data in fields.items():
        related_model = field_data.get("related_model")
        field_type = field_data.get("type", "")

        if related_model:
            relations.append(f"{field_name} ({field_type}) -> {related_model}")

    return relations


def extract_field_text(fields: dict) -> list[str]:
    field_texts = []

    for field_name, field_data in fields.items():
        field_type = field_data.get("type", "")
        field_desc = field_data.get("description", "")
        related_model = field_data.get("related_model", "")

        if related_model:
            text = f"{field_name} : {field_desc} | type={field_type} | relation={related_model}"
        else:
            text = f"{field_name} : {field_desc} | type={field_type}"

        field_texts.append(text)

    return field_texts


def select_important_fields(field_texts: list[str], limit: int = 35) -> list[str]:
    scored = []

    for text in field_texts:
        lower = text.lower()
        score = 0

        for keyword in IMPORTANT_KEYWORDS:
            if keyword in lower:
                score += 1

        if "relation=" in lower:
            score += 2

        scored.append((score, text))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [text for score, text in scored[:limit]]


def is_technical_model(model_name: str) -> bool:
    technical_prefixes = (
        "ir.",
        "mail.",
        "bus.",
        "utm.",
        "portal.",
        "rating.",
        "resource.",
    )

    if model_name in {"res.partner", "res.company", "res.currency", "res.users"}:
        return False

    if model_name.startswith(technical_prefixes):
        return True

    if "mixin" in model_name or "qweb" in model_name or "_unknown" in model_name:
        return True

    return False


def build_index_text(model_name: str, model_data: dict) -> str:
    description_originale = model_data.get("description", "")
    description_enrichie = model_data.get("description_enrichie", "").strip()
    fields = clean_fields(model_data.get("fields", {}))

    field_texts = extract_field_text(fields)
    relations = extract_relations(fields)

    if is_technical_model(model_name):
        field_limit = 15
        relation_limit = 15
    else:
        field_limit = 35
        relation_limit = 35

    important_fields = select_important_fields(field_texts, limit=field_limit)
    important_relations = relations[:relation_limit]

    boost_text = MODEL_BOOSTS.get(model_name, "")

    index_text = "\n".join([
        f"Nom technique du modèle Odoo : {model_name}",
        f"Libellé fonctionnel : {description_originale}",
        f"Description métier enrichie : {description_enrichie}",
        f"Signaux de recherche prioritaires : {boost_text}",
        "Champs métier importants : " + " ; ".join(important_fields),
        "Relations fonctionnelles importantes : " + " ; ".join(important_relations),
    ])

    return index_text[:MAX_TEXT_CHARS]


def recreate_collection():
    if qdrant.collection_exists(COLLECTION_NAME):
        print(f"⚠️ Collection '{COLLECTION_NAME}' existante — suppression.")
        qdrant.delete_collection(COLLECTION_NAME)

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )

    print(f"✅ Collection '{COLLECTION_NAME}' créée.")


def upsert_batch(points: list[PointStruct]):
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
    )


def index(input_file: str = INPUT_FILE):
    print(f"📂 Lecture du fichier : {input_file}")

    with open(input_file, "r", encoding="utf-8") as f:
        schema = json.load(f)

    total = len(schema)
    print(f"📊 {total} modèles à indexer.")

    recreate_collection()

    points_batch = []
    errors = []

    for count, (model_name, model_data) in enumerate(schema.items(), start=1):
        description_originale = model_data.get("description", "")
        description_enrichie = model_data.get("description_enrichie", "").strip()
        fields_clean = clean_fields(model_data.get("fields", {}))

        if not description_enrichie:
            print(f"⚠️ [{count}/{total}] {model_name} ignoré : description_enrichie vide.")
            errors.append(model_name)
            continue

        index_text = build_index_text(model_name, model_data)

        print(f"⏳ [{count}/{total}] {model_name}")

        try:
            vector = get_embedding(index_text, mode="document")
        except Exception as e:
            print(f"❌ Erreur embedding pour {model_name} : {e}")
            errors.append(model_name)
            continue

        payload = {
            "model_name": model_name,
            "description_originale": description_originale,
            "description_enrichie": description_enrichie,
            "index_text": index_text,
            "fields": list(fields_clean.keys()),
            "relations": extract_relations(fields_clean),
            "nb_fields": len(fields_clean),
            "is_technical": is_technical_model(model_name),
        }

        points_batch.append(
            PointStruct(
                id=model_name_to_id(model_name),
                vector=vector,
                payload=payload,
            )
        )

        if len(points_batch) >= BATCH_SIZE:
            print(f"💾 Upsert batch : {len(points_batch)} points")
            upsert_batch(points_batch)
            points_batch = []

    if points_batch:
        print(f"💾 Upsert final : {len(points_batch)} points")
        upsert_batch(points_batch)

    print("=" * 60)
    print("✅ Indexation terminée")
    print(f"📌 Collection : {COLLECTION_NAME}")
    print(f"📊 Modèles indexés : {total - len(errors)}/{total}")

    if errors:
        print(f"⚠️ Modèles en erreur : {errors}")

    print("=" * 60)


def search(query: str, top_k: int = 20):
    print(f"\n🔍 Recherche : {query}")

    vector = get_embedding(query, mode="query")

    results = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=top_k,
    ).points

    for i, r in enumerate(results, start=1):
        print(f"{i}. [{r.score:.3f}] {r.payload['model_name']}")
        print(f"   {r.payload['description_enrichie'][:180]}...")


if __name__ == "__main__":
    index()

    search("vendeurs du produit E-COM11", top_k=20)
    search("combien de jours de congé de l'employé qui a vendu le plus le produit ayant default_code X", top_k=20)
    search("factures clients impayées par commercial", top_k=20)
