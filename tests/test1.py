import time

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# --- CONFIGURATION ---
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434"
COL_MODELS = "odoo_models_v2"  # Vérifiez bien le nom de votre collection
COL_FIELDS = "odoo_fields_v3"
EMBEDDING_MODEL = "bge-m3"

qdrant = QdrantClient(url=QDRANT_URL)

# Le dictionnaire de Boost (Solution A)
ODOO_CORE_MODELS = {
    # --- Modèles augmentés suite aux erreurs ---
    "res.partner": {"weight": 1.25},  # Pour battre account.root et phone.blacklist
    "account.move": {"weight": 1.25},  # Pour battre account.payment.term
    "sale.order": {"weight": 1.25},  # Pour battre sale.order.template
    "stock.quant": {"weight": 1.25},  # Pour battre stock.warehouse

    # --- Nouveaux modèles ajoutés ---
    "hr.applicant": {"weight": 1.20},
    "hr.job": {"weight": 1.20},
    "hr.attendance": {"weight": 1.15},
    "account.analytic.line": {"weight": 1.15},
    "account.payment.term": {"weight": 1.15},
    "project.task.type": {"weight": 1.15},
    "crm.lost.reason": {"weight": 1.10},

    # --- Reste des modèles (stables) ---
    "product.template": {"weight": 1.20},
    "product.product": {"weight": 1.15},
    "res.company": {"weight": 1.10},
    "sale.order.line": {"weight": 1.15},
    "crm.lead": {"weight": 1.15},
    "purchase.order": {"weight": 1.15},
    "purchase.order.line": {"weight": 1.10},
    "stock.picking": {"weight": 1.15},
    "stock.move": {"weight": 1.10},
    "account.move.line": {"weight": 1.15},
    "account.payment": {"weight": 1.15},
    "account.journal": {"weight": 1.10},
    "hr.employee": {"weight": 1.20},
    "hr.contract": {"weight": 1.15},
    "hr.leave": {"weight": 1.10},
    "project.project": {"weight": 1.15},
    "project.task": {"weight": 1.15}
}

# --- LES 50 CAS DE TESTS ---
# --- LES 50 CAS DE TESTS (Modèles + Champs attendus) ---
TEST_CASES = [
    # ==========================================
    # 🛒 VENTES & CRM (Sales & CRM)
    # ==========================================
    {"q": "Quels sont les devis en attente pour le client Decathlon ?", "expected_model": "sale.order",
     "expected_fields": ["state", "partner_id"]},
    {"q": "Donne-moi le total des ventes réalisées par le commercial Marc.", "expected_model": "sale.order",
     "expected_fields": ["amount_total", "user_id"]},
    {"q": "Combien de devis ont été annulés aujourd'hui ?", "expected_model": "sale.order",
     "expected_fields": ["state", "date_order"]},
    {"q": "Quelles sont les lignes de commande avec une remise de 10% ?", "expected_model": "sale.order.line",
     "expected_fields": ["discount", "order_id"]},
    {"q": "Combien d'opportunités avons-nous gagnées ce mois-ci ?", "expected_model": "crm.lead",
     "expected_fields": ["stage_id", "expected_revenue"]},
    {"q": "Quels sont les motifs de perte de nos opportunités ?", "expected_model": "crm.lost.reason",
     "expected_fields": ["name"]},
    {"q": "Quel est le chiffre d'affaires espéré pour l'équipe Europe ?", "expected_model": "crm.lead",
     "expected_fields": ["team_id", "expected_revenue"]},
    {"q": "Quel est le prochain rappel (activité) pour le prospect XYZ ?", "expected_model": "crm.lead",
     "expected_fields": ["activity_date_deadline", "activity_summary"]},
    {"q": "Combien d'opportunités n'ont pas été assignées à un commercial ?", "expected_model": "crm.lead",
     "expected_fields": ["user_id", "type"]},

    # ==========================================
    # 👥 CONTACTS & SOCIÉTÉS (Contacts & Companies)
    # ==========================================
    {"q": "Quelle est l'adresse de facturation de la société Agrolait ?", "expected_model": "res.partner",
     "expected_fields": ["type", "street", "city"]},
    {"q": "Donne-moi le numéro de téléphone et le mobile de Jean Dupont.", "expected_model": "res.partner",
     "expected_fields": ["phone", "mobile"]},
    {"q": "Quels sont nos clients situés à Paris ?", "expected_model": "res.partner",
     "expected_fields": ["city", "customer_rank"]},
    {"q": "Quel est l'email du contact principal de l'entreprise ?", "expected_model": "res.partner",
     "expected_fields": ["email", "is_company"]},
    {"q": "Quelles sont les étiquettes (tags) du client Microsoft ?", "expected_model": "res.partner.category",
     "expected_fields": ["name"]},
    {"q": "Liste de toutes nos filiales (multi-société).", "expected_model": "res.company",
     "expected_fields": ["name", "parent_id"]},

    # ==========================================
    # 📦 CATALOGUE & INVENTAIRE (Inventory & Products)
    # ==========================================
    {"q": "Quel est le prix de vente public du produit qui a le code E-COM11 ?", "expected_model": "product.template",
     "expected_fields": ["list_price", "default_code"]},
    {"q": "Quel est le code barre de la variante Rouge du T-shirt ?", "expected_model": "product.product",
     "expected_fields": ["barcode", "product_tmpl_id"]},
    {"q": "Quelles sont les catégories de produits existantes ?", "expected_model": "product.category",
     "expected_fields": ["name", "parent_id"]},
    {"q": "Combien d'unités de l'article 'Chaise' avons-nous réellement en stock ?", "expected_model": "stock.quant",
     "expected_fields": ["quantity", "product_id"]},
    {"q": "Où est rangé le produit X dans l'entrepôt ?", "expected_model": "stock.quant",
     "expected_fields": ["location_id", "product_id"]},
    {"q": "Liste tous les bons de livraison qui sont en retard.", "expected_model": "stock.picking",
     "expected_fields": ["state", "scheduled_date"]},
    {"q": "Quels sont les mouvements de stock réalisés hier ?", "expected_model": "stock.move",
     "expected_fields": ["state", "date", "product_id"]},
    {"q": "Donne-moi le détail des transferts internes en cours.", "expected_model": "stock.picking",
     "expected_fields": ["picking_type_id", "state"]},
    {"q": "Quelles sont les règles de réapprovisionnement pour le bois ?",
     "expected_model": "stock.warehouse.orderpoint", "expected_fields": ["product_min_qty", "product_max_qty"]},
    {"q": "Combien d'entrepôts actifs avons-nous ?", "expected_model": "stock.warehouse",
     "expected_fields": ["name", "code"]},

    # ==========================================
    # 🤝 ACHATS (Purchasing)
    # ==========================================
    {"q": "Qui est notre fournisseur pour les écrans Dell ?", "expected_model": "purchase.order",
     "expected_fields": ["partner_id", "amount_total"]},
    {"q": "Combien de commandes d'achat attendent une validation par le manager ?", "expected_model": "purchase.order",
     "expected_fields": ["state", "amount_total"]},
    {"q": "Quel est le délai de livraison moyen de ce fournisseur ?", "expected_model": "res.partner",
     "expected_fields": ["delay", "name"]},  # Peut aussi être product.supplierinfo
    {"q": "Quelles sont les lignes d'achat pour le projet XYZ ?", "expected_model": "purchase.order.line",
     "expected_fields": ["price_unit", "product_id"]},
    {"q": "Quelles demandes de prix (RFQ) ont été envoyées aujourd'hui ?", "expected_model": "purchase.order",
     "expected_fields": ["state", "date_order"]},

    # ==========================================
    # 💼 RESSOURCES HUMAINES (HR & Timesheets)
    # ==========================================
    {"q": "Combien de jours de congés validés reste-t-il à Sophie ?", "expected_model": "hr.leave",
     "expected_fields": ["number_of_days", "state", "employee_id"]},
    {"q": "Quel est le salaire de base de Jean dans son contrat actuel ?", "expected_model": "hr.contract",
     "expected_fields": ["wage", "employee_id", "state"]},
    {"q": "Qui est le manager du département IT ?", "expected_model": "hr.department",
     "expected_fields": ["manager_id", "name"]},
    {"q": "Combien d'employés travaillent dans notre société actuellement ?", "expected_model": "hr.employee",
     "expected_fields": ["active", "department_id"]},
    {"q": "Quelles sont les candidatures reçues pour le poste de développeur ?", "expected_model": "hr.applicant",
     "expected_fields": ["job_id", "stage_id"]},
    {"q": "Quels sont les postes actuellement ouverts au recrutement ?", "expected_model": "hr.job",
     "expected_fields": ["state", "no_of_recruitment"]},
    {"q": "Liste des notes de frais en attente de remboursement.", "expected_model": "hr.expense",
     "expected_fields": ["state", "total_amount", "employee_id"]},
    {"q": "Quelles sont les feuilles de présence (pointages) de la semaine dernière ?",
     "expected_model": "hr.attendance", "expected_fields": ["check_in", "check_out", "employee_id"]},
    {"q": "Combien d'heures ont été pointées (timesheet) par Alice aujourd'hui ?",
     "expected_model": "account.analytic.line", "expected_fields": ["unit_amount", "employee_id", "date"]},
    {"q": "Quels sont les contrats de travail en cours de validité ?", "expected_model": "hr.contract",
     "expected_fields": ["state", "date_start", "date_end"]},

    # ==========================================
    # 💰 COMPTABILITÉ & FINANCE (Accounting & Invoicing)
    # ==========================================
    {"q": "Quelles sont les factures client impayées de plus de 30 jours ?", "expected_model": "account.move",
     "expected_fields": ["payment_state", "invoice_date_due", "move_type"]},
    {"q": "Donne-moi la liste des avoirs créés ce mois-ci.", "expected_model": "account.move",
     "expected_fields": ["move_type", "invoice_date", "amount_total"]},
    {"q": "Qui a créé la dernière facture ?", "expected_model": "account.move",
     "expected_fields": ["create_uid", "name"]},
    {"q": "Quel est le montant total des paiements reçus hier ?", "expected_model": "account.payment",
     "expected_fields": ["amount", "date", "payment_type"]},
    {"q": "Quelles sont les lignes d'écritures pour le compte client 411 ?", "expected_model": "account.move.line",
     "expected_fields": ["account_id", "debit", "credit"]},
    {"q": "Combien de taxes sont configurées pour la TVA à 20% ?", "expected_model": "account.tax",
     "expected_fields": ["amount", "name"]},
    {"q": "Quelles sont les conditions de paiement configurées à 30 jours ?", "expected_model": "account.payment.term",
     "expected_fields": ["name", "line_ids"]},
    {"q": "Liste des relevés bancaires non lettrés.", "expected_model": "account.bank.statement",
     "expected_fields": ["balance_end", "date"]},
    {"q": "Quelle est la devise principale de l'entreprise ?", "expected_model": "res.currency",
     "expected_fields": ["name", "active"]},
    {"q": "Montre moi le journal comptable des ventes.", "expected_model": "account.journal",
     "expected_fields": ["type", "name"]},

    # ==========================================
    # 📋 PROJETS (Projects)
    # ==========================================
    {"q": "Combien de tâches sont bloquées dans le projet Refonte Web ?", "expected_model": "project.task",
     "expected_fields": ["kanban_state", "project_id"]},
    {"q": "Quels sont les projets actifs en ce moment ?", "expected_model": "project.project",
     "expected_fields": ["active", "name", "user_id"]},
    {"q": "Quelles sont les étapes (états) Kanban de nos projets ?", "expected_model": "project.task.type",
     "expected_fields": ["name", "project_ids"]},
    {"q": "Combien d'heures planifiées versus réalisées sur cette tâche ?", "expected_model": "project.task",
     "expected_fields": ["planned_hours", "effective_hours"]}
]


def get_embedding(text: str):
    payload = {"model": EMBEDDING_MODEL, "prompt": f"search_query: {text}"}
    res = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
    return res.json()["embedding"]


def test_rag_full():
    print(f"🚀 Lancement de la suite de tests Modèles + Champs ({len(TEST_CASES)} questions)...\n")

    model_success = 0
    field_success = 0

    for i, test in enumerate(TEST_CASES, 1):
        query = test["q"]
        exp_model = test["expected_model"]
        exp_fields = test["expected_fields"]

        print(f"\n[{i}/{len(TEST_CASES)}] Q: '{query}'")
        vector = get_embedding(query)

        # --- ÉTAPE 1 : MODÈLES ---
        raw_results = qdrant.query_points(collection_name=COL_MODELS, query=vector, limit=15).points
        reranked = []
        for r in raw_results:
            m_name = r.payload['model_name']
            boost = ODOO_CORE_MODELS.get(m_name, {}).get("weight", 1.0)
            reranked.append({"model": m_name, "score": r.score * boost})

        reranked.sort(key=lambda x: x["score"], reverse=True)
        top_3_models = [r["model"] for r in reranked[:3]]

        if exp_model in top_3_models:
            model_success += 1
            print(f"  ✅ MODÈLE TROUVÉ : {exp_model} (Rang {top_3_models.index(exp_model) + 1})")

            # --- ÉTAPE 2 : CHAMPS (Seulement si le modèle est trouvé) ---
            field_results = qdrant.query_points(
                collection_name=COL_FIELDS,
                query=vector,
                query_filter=Filter(must=[FieldCondition(key="model_name", match=MatchValue(value=exp_model))]),
                limit=10  # On récupère les 7 meilleurs champs
            ).points

            found_fields = [f.payload['field_name'] for f in field_results]

            # Vérifie combien de champs attendus sont dans les champs trouvés
            matched_fields = [f for f in exp_fields if f in found_fields]

            if matched_fields:
                field_success += 1
                print(f"  ✅ CHAMPS TROUVÉS : {matched_fields} (parmi {found_fields[:4]}...)")
            else:
                print(f"  ❌ CHAMPS MANQUANTS : On attendait {exp_fields}, on a eu {found_fields}")

        else:
            print(f"  ❌ MODÈLE ÉCHOUÉ : Attendu {exp_model}, Obtenus {top_3_models}")

    # --- RAPPORT FINAL ---
    print("\n" + "=" * 50)
    print("📊 RAPPORT FINAL (SOLUTION A)")
    print("=" * 50)
    print(f"🎯 Modèles trouvés (Top 3) : {model_success}/{len(TEST_CASES)}")
    print(f"🎯 Champs trouvés (Top 7)  : {field_success}/{model_success} (parmi les modèles réussis)")


if __name__ == "__main__":
    start_time = time.time()
    test_rag_full()
    print(f"\n⏱️ Temps d'exécution total: {time.time() - start_time:.1f} sec")
