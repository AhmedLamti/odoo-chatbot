import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Configuration
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434"
COL_MODELS = "odoo_models_v2"  # Assurez-vous que c'est la bonne collection
COL_FIELDS = "odoo_fields_v3"
EMBEDDING_MODEL = "bge-m3"

qdrant = QdrantClient(url=QDRANT_URL)

ODOO_CORE_MODELS = {
    # === CATALOGUE & CONTACTS ===
    "product.template": {"weight": 1.20,
                         "keywords": "CATALOGUE, PRODUIT PRINCIPAL, ARTICLE RÉFÉRENCE, GESTION DES PRODUITS"},
    "product.product": {"weight": 1.15, "keywords": "VARIANTE, STOCK, INVENTAIRE, SKU, CODE BARRE"},
    "res.partner": {"weight": 1.20, "keywords": "CLIENT, FOURNISSEUR, CONTACT, ADRESSE, ENTREPRISE"},
    "res.company": {"weight": 1.10, "keywords": "SOCIÉTÉ, MULTI-SOCIÉTÉ, ENTREPRISE PRINCIPALE"},

    # === VENTES & CRM ===
    "sale.order": {"weight": 1.20, "keywords": "VENTE, COMMANDE CLIENT, DEVIS, CHIFFRE D'AFFAIRES"},
    "sale.order.line": {"weight": 1.15, "keywords": "LIGNE DE VENTE, ARTICLE VENDU, QUANTITÉ VENDUE"},
    "crm.lead": {"weight": 1.15, "keywords": "OPPORTUNITÉ, PISTE, PROSPECT, PIPELINE, CRM"},

    # === ACHATS ===
    "purchase.order": {"weight": 1.15, "keywords": "ACHAT, COMMANDE FOURNISSEUR, APPROVISIONNEMENT"},
    "purchase.order.line": {"weight": 1.10, "keywords": "LIGNE D'ACHAT, ARTICLE ACHETÉ"},

    # === STOCK & LOGISTIQUE ===
    "stock.picking": {"weight": 1.15, "keywords": "TRANSFERT, LIVRAISON, RÉCEPTION, BON DE LIVRAISON, EXPÉDITION"},
    "stock.move": {"weight": 1.10, "keywords": "MOUVEMENT DE STOCK, HISTORIQUE STOCK"},
    "stock.quant": {"weight": 1.20, "keywords": "QUANTITÉ EN STOCK, INVENTAIRE RÉEL, DISPONIBILITÉ"},

    # === COMPTABILITÉ ===
    "account.move": {"weight": 1.20, "keywords": "FACTURE, PIÈCE COMPTABLE, ÉCRITURE, AVOIR, FACTURATION"},
    "account.move.line": {"weight": 1.15, "keywords": "LIGNE COMPTABLE, LIGNE DE FACTURE, COMPTE"},
    "account.payment": {"weight": 1.15, "keywords": "PAIEMENT, RÈGLEMENT, ENCAISSEMENT, DÉCAISSEMENT"},
    "account.journal": {"weight": 1.10, "keywords": "JOURNAL COMPTABLE, BANQUE, CAISSE"},

    # === RESSOURCES HUMAINES ===
    "hr.employee": {"weight": 1.20, "keywords": "EMPLOYÉ, SALARIÉ, PERSONNEL, RESSOURCES HUMAINES"},
    "hr.contract": {"weight": 1.10, "keywords": "CONTRAT DE TRAVAIL, SALAIRE, RÉMUNÉRATION"},
    "hr.leave": {"weight": 1.10, "keywords": "CONGÉ, ABSENCE, VACANCES"},

    # === PROJETS ===
    "project.project": {"weight": 1.15, "keywords": "PROJET, CHANTIER, GESTION DE PROJET"},
    "project.task": {"weight": 1.15, "keywords": "TÂCHE, FEUILLE DE TEMPS, TIMESHEET"}
}


def get_query_embedding(text: str):
    """Génère l'embedding de la question avec le préfixe search_query."""
    payload = {"model": EMBEDDING_MODEL, "prompt": f"search_query: {text}"}
    res = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
    res.raise_for_status()
    return res.json()["embedding"]


def perform_rag_search(user_query: str):
    print(f"\n🔍 QUESTION : '{user_query}'")
    print("=" * 50)

    # 1. Embedding de la requête
    query_vector = get_query_embedding(user_query)

    # 2. ÉTAPE 1 : Trouver les modèles (On cherche large, ex: 15 résultats)
    print("\n[Étape 1] Recherche et Re-ranking des modèles...")
    raw_model_results = qdrant.query_points(
        collection_name=COL_MODELS,
        query=query_vector,
        limit=15  # Plus grand pour attraper le bon modèle même s'il est bas
    ).points

    # --- APPLICATION DU BOOST (RE-RANKING) ---
    reranked_models = []
    for m_res in raw_model_results:
        model_name = m_res.payload['model_name']
        base_score = m_res.score

        # Vérifie si le modèle est dans notre liste prioritaire
        if model_name in ODOO_CORE_MODELS:
            boost = ODOO_CORE_MODELS[model_name]["weight"]
            is_core = True
        else:
            boost = 1.0
            is_core = False

        final_score = base_score * boost

        reranked_models.append({
            "model_name": model_name,
            "original_score": base_score,
            "final_score": final_score,
            "is_core": is_core,
            "payload": m_res.payload
        })

    # Tri de la liste en fonction du nouveau score final décroissant
    reranked_models.sort(key=lambda x: x["final_score"], reverse=True)

    # On ne garde que le TOP 3 après le tri
    top_3_models = reranked_models[:3]

    for m_res in top_3_models:
        model_name = m_res["model_name"]
        score_f = m_res["final_score"]
        score_o = m_res["original_score"]
        boost_indicator = "🚀 BOOSTÉ" if m_res["is_core"] else ""

        print(f"\n⭐ MODÈLE : {model_name} (Score final: {score_f:.4f} | Base: {score_o:.4f}) {boost_indicator}")

        # 3. ÉTAPE 2 : Trouver les champs pertinents UNIQUEMENT pour ce modèle
        print(f"   ∟ Recherche des champs pertinents dans {model_name}...")

        field_results = qdrant.query_points(
            collection_name=COL_FIELDS,
            query=query_vector,
            query_filter=Filter(
                must=[FieldCondition(key="model_name", match=MatchValue(value=model_name))]
            ),
            limit=5  # Je l'ai remis à 5 pour ne pas noyer le futur LLM, ajustez si besoin
        ).points

        for f_res in field_results:
            f_name = f_res.payload['field_name']
            f_type = f_res.payload['type']
            print(f"      - {f_name} ({f_type}) | Score: {f_res.score:.4f}")


if __name__ == "__main__":
    # Testez ici votre question
    test_query = "combien de produit nous avons dans le catalogue"
    perform_rag_search(test_query)
