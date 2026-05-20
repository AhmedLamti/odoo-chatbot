import hashlib
import json
import time

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Configuration
INPUT_FILE = "schema_odoo_enrichi_rag_complexe.json"
QDRANT_URL = "http://localhost:6333"
COL_MODELS = "odoo_models_v2"
COL_FIELDS = "odoo_fields_v2"
OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "bge-m3"
VECTOR_SIZE = 1024
SKIP_PREFIXES = ("message_", "activity_", "website_", "access_", "audit_", "create_", "write_")
SKIP_EXACT = {"__last_update", "display_name", "id", "sequence"}
qdrant = QdrantClient(url=QDRANT_URL)


def is_technical_model(model_name: str) -> bool:
    """Filtre amélioré pour ignorer les tests et les outils techniques."""
    tech_pre = ("ir.", "mail.", "bus.", "utm.", "base.", "web.", "report.", "base_import.", "test.")
    # On garde les essentiels
    whitelist = {"res.partner", "res.users", "res.company", "res.groups", "res.currency"}

    if model_name in whitelist: return False

    # Exclure les modèles de test, les mixins et les wizards
    if any(x in model_name for x in [".tests.", "test_", "mixin", "wizard"]):
        return True

    return model_name.startswith(tech_pre)


def get_embedding(text: str, retries=3):
    """Génère un embedding avec gestion de retry en cas d'erreur 500."""
    if not text or len(text.strip()) == 0:
        text = "n/a"

    payload = {"model": EMBEDDING_MODEL, "prompt": f"search_document: {text[:3000]}"}

    for i in range(retries):
        try:
            res = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload, timeout=60)
            res.raise_for_status()
            return res.json()["embedding"]
        except Exception as e:
            if i < retries - 1:
                print(f"⚠️ Erreur Ollama ({e}), tentative {i + 1}/3 dans 2s...")
                time.sleep(2)
                continue
            else:
                print(f"❌ Échec définitif pour le texte : {text[:50]}...")
                raise e


def index():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        schema = json.load(f)

    # (Ré)Initialisation des collections
    for col in [COL_MODELS, COL_FIELDS]:
        qdrant.recreate_collection(col, vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE))

    for model_name, data in schema.items():
        # 1. Premier filtre sur le nom du modèle
        if is_technical_model(model_name):
            continue

        # 2. Nettoyage et préparation des champs (Étape CRUCIALE)
        fields = data.get("fields", {})
        field_points = []

        for f_name, f_info in fields.items():
            # Application de vos filtres de champs techniques
            if any(f_name.startswith(p) for p in SKIP_PREFIXES):
                continue
            if f_name in SKIP_EXACT:
                continue

            # Si le champ survit, on prépare son point pour la collection COL_FIELDS
            f_desc = f_info.get("description", "pas de description")
            f_text = f"Champ: {f_name} (Modèle {model_name}). Type: {f_info.get('type')}. Fonction: {f_desc}"

            try:
                f_vector = get_embedding(f_text)
                field_points.append(PointStruct(
                    id=int(hashlib.md5(f"{model_name}_{f_name}".encode()).hexdigest()[:15], 16),
                    vector=f_vector,
                    payload={
                        "model_name": model_name,
                        "field_name": f_name,
                        "type": f_info.get("type"),
                        "description": f_desc
                    }
                ))
            except:
                continue

        # 3. CONDITION DE SORTIE : Si aucun champ métier n'est trouvé, on ignore le modèle
        if not field_points:
            print(f"⏩ Ignoré : {model_name} (0 champ métier après nettoyage)")
            continue

        # 4. Si on arrive ici, le modèle est valide : on indexe le MODÈLE (COL_MODELS)
        try:
            desc_text = f"Modèle: {model_name}. Description: {data.get('description_enrichie', '')}"
            model_vector = get_embedding(desc_text)

            qdrant.upsert(COL_MODELS, points=[PointStruct(
                id=int(hashlib.md5(model_name.encode()).hexdigest()[:15], 16),
                vector=model_vector,
                payload={"model_name": model_name, "desc": data.get('description_enrichie')}
            )])

            # 5. On indexe ses CHAMPS (COL_FIELDS)
            qdrant.upsert(COL_FIELDS, points=field_points)
            print(f"✅ Indexé : {model_name} ({len(field_points)} champs métiers)")

        except Exception as e:
            print(f"❌ Erreur sur {model_name} : {e}")


if __name__ == "__main__":
    index()
