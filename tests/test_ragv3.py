import time

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "bge-m3"

COL_MODELS = "odoo_models_v3"
COL_FIELDS = "odoo_fields_v3"

qdrant = QdrantClient(url=QDRANT_URL)
MASTER_BOOST = {
    # --- ACTEURS & ENTITÉS ---
    "vend": ["user_id", "member_id"],  # vendeur, vendeuse, vente
    "commercia": ["user_id", "member_id"],  # commercial, commerciaux
    "respons": ["user_id", "manager_id"],  # responsable
    "clien": ["partner_id"],  # client, clients, clientèle
    "fournisseur": ["partner_id", "seller_ids"],
    "partenaire": ["partner_id"],
    "tier": ["partner_id"],  # tiers
    "contac": ["partner_id"],  # contact
    "sociét": ["company_id"],  # société, sociétés
    "entrepris": ["company_id"],  # entreprise
    "filial": ["company_id"],  # filiale
    "équip": ["team_id"],  # équipe
    "département": ["department_id"],
    "employ": ["employee_id", "user_id"],  # employé, employés
    "manag": ["parent_id", "manager_id"],  # manager, management

    # --- ÉTATS & STATUTS ---
    "statut": ["state", "invoice_status", "delivery_status", "payment_state"],
    "état": ["state", "kanban_state"],
    "étap": ["stage_id", "state"],  # étape
    "phas": ["stage_id"],  # phase
    "valid": ["state"],  # validé, validée, validation
    "confirm": ["state"],  # confirmé, confirmation
    "brouillon": ["state"],
    "annul": ["state"],  # annulé, annulation
    "gagn": ["stage_id", "probability"],  # gagné, gagnée
    "perdu": ["stage_id", "lost_reason_id"],
    "factur": ["invoice_status", "invoice_ids"],  # facturé, facturation, facture
    "pay": ["payment_state", "is_paid"],  # payé, paiement
    "ouvert": ["state"],
    "clôtur": ["state", "date_closed"],  # clôturé, clôture

    # --- FINANCES & CHIFFRES ---
    "montant": ["amount_total", "amount_untaxed", "price_unit", "expected_revenue"],
    "total": ["amount_total", "amount_untaxed"],
    "somme": ["amount_total"],
    "ca": ["amount_total"],
    "chiffre d'affaires": ["amount_total"],
    "revenu": ["expected_revenue", "recurring_revenue"],
    "prix": ["price_unit", "amount_total"],
    "tax": ["tax_id", "taxes_id", "tax_ids"],  # taxe, taxes
    "tva": ["tax_id", "taxes_id", "tax_ids"],
    "devis": ["currency_id", "company_currency_id"],  # devise (attention, peut matcher devis)
    "monnaie": ["currency_id"],
    "solde": ["balance", "credit", "debit"],
    "crédit": ["credit"],
    "débit": ["debit"],

    # --- LOGISTIQUE & PRODUITS ---
    "produi": ["product_id", "product_tmpl_id"],  # produit
    "articl": ["product_id", "product_tmpl_id"],  # article
    "variant": ["product_id"],
    "quantit": ["product_uom_qty", "qty_done", "quantity", "product_qty"],  # quantité
    "qté": ["product_uom_qty", "qty_done", "quantity"],
    "stock": ["qty_available", "virtual_available", "location_id"],
    "emplac": ["location_id", "location_dest_id"],  # emplacement
    "lot": ["lot_id", "lot_name"],
    "séri": ["lot_id"],  # série
    "poids": ["weight"],
    "unité": ["product_uom"],

    # --- TEMPS & DATES ---
    "date": ["date", "date_order", "date_deadline", "create_date"],
    "quand": ["date", "create_date"],
    "échéanc": ["date_deadline", "validity_date"],  # échéance
    "cré": ["create_uid", "create_date"],  # créé, créée, création, créateur
    "auteur": ["create_uid"],
    "modifi": ["write_uid", "write_date"],  # modifié, modification
    "derni": ["write_date"],  # dernier, dernière
    "début": ["date_start"],
    "fin": ["date_stop", "date_end"],

    # --- RÉFÉRENCES & DOCUMENTS ---
    "réf": ["name", "ref", "reference", "client_order_ref"],  # réf, référence
    "numéro": ["name", "number"],
    "nom": ["name", "display_name"],
    "desc": ["name", "description", "note"],  # description
    "projet": ["project_id"],
    "tâch": ["task_id"],  # tâche
    "command": ["order_id"],  # commande
    "factur": ["invoice_id", "move_id"],
    "étiquet": ["tag_ids", "category_id"],  # étiquette
    "catégor": ["categ_id", "category_id"],  # catégorie
    "motif": ["lost_reason_id", "reason"],
}


def get_embedding(text):
    """Génère l'embedding via Ollama."""
    try:
        payload = {"model": EMBEDDING_MODEL, "prompt": text}
        res = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
        res.raise_for_status()
        return res.json()["embedding"]
    except Exception as e:
        print(f"❌ Erreur Ollama : {e}")
        return None


def search_rag_v3(question, top_k_models=5, top_k_fields=150):
    """
    1. Cherche le modèle (en appliquant le poids natif)
    2. Cherche les champs (en filtrant uniquement sur le meilleur modèle)
    """
    query_vector = get_embedding(question)
    if not query_vector:
        return [], []

    # --- ÉTAPE 1 : RECHERCHE DES MODÈLES ---
    # On ramène un peu plus de résultats (ex: 10) pour laisser la place au tri avec les poids
    model_hits = qdrant.query_points(
        collection_name=COL_MODELS,
        query=query_vector,
        limit=10
    ).points

    # Application du multiplicateur de poids (Core Models)
    scored_models = []
    for hit in model_hits:
        weight = hit.payload.get("weight", 1.0)
        # Score final = Score cosinus brut * Poids métier
        final_score = hit.score * weight
        scored_models.append({
            "model_name": hit.payload.get("model_name"),
            "score": final_score
        })

    # Tri des modèles par le nouveau score et sélection du Top K
    scored_models.sort(key=lambda x: x["score"], reverse=True)
    top_models = [m["model_name"] for m in scored_models[:top_k_models]]

    # Le grand gagnant est le numéro 1
    best_model = top_models[0] if top_models else None

    # --- ÉTAPE 2 : RECHERCHE DES CHAMPS (AVEC FILTRE) ---
    predicted_fields = []
    if best_model:
        # La magie de Qdrant : On limite la recherche vectorielle au best_model
        field_hits = qdrant.query_points(
            collection_name=COL_FIELDS,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key="model_name",
                        match=MatchValue(value=best_model)
                    )
                ]
            ),
            limit=top_k_fields
        ).points
        refined_fields = []
        question_lower = question.lower()

        for hit in field_hits:
            payload = hit.payload
            f_name = payload.get("field_name")
            score = hit.score
            for keyword, target_fields in MASTER_BOOST.items():
                # Si le mot-clé est dans la question ET que le champ actuel est un des champs cibles
                if keyword in question_lower and f_name in target_fields:
                    # On ajoute un bonus proportionnel à la confiance
                    score += 2

            refined_fields.append({"name": f_name, "score": score})

            # Tri final
        refined_fields.sort(key=lambda x: x["score"], reverse=True)
        print(refined_fields)
        predicted_fields = [f["name"] for f in refined_fields[:top_k_fields]]

    return top_models, predicted_fields


# ==========================================
# 🧪 VOS CAS DE TESTS
# ==========================================
TEST_CASES = [
    # ================= 1. VENTES (sale.order) =================
    {
        "question": "Montre moi le chiffre d'affaires total des devis validés pour l'équipe commerciale Europe.",
        "expected_model": "sale.order",
        "expected_fields": ["team_id", "amount_total", "state"]
    },
    {
        "question": "Quelles sont les commandes clients facturées qui utilisent la devise USD ?",
        "expected_model": "sale.order",
        "expected_fields": ["currency_id", "invoice_status"]
    },
    {
        "question": "Liste les lignes de vente associées au produit 'Bureau' avec leur taxe applicable.",
        "expected_model": "sale.order.line",
        "expected_fields": ["product_id", "tax_id"]
    },
    {
        "question": "Quelles commandes de vente ont été créées par l'utilisateur Marc pour le client Decathlon ?",
        "expected_model": "sale.order",
        "expected_fields": ["create_uid", "partner_id"]
    },
    {
        "question": "Combien de bons de commande ont une adresse de facturation différente de l'adresse de livraison ?",
        "expected_model": "sale.order",
        "expected_fields": ["partner_invoice_id", "partner_shipping_id"]
    },
    {
        "question": "Quel est le délai de validité moyen des devis liés au compte analytique 'Projet Alpha' ?",
        "expected_model": "sale.order",
        "expected_fields": ["validity_date", "analytic_account_id"]
    },
    {
        "question": "Quelles sont les campagnes marketing (UTM) qui ont généré le plus de revenus sur les devis gagnés ?",
        "expected_model": "sale.order",
        "expected_fields": ["campaign_id", "amount_total", "state"]
    },

    # ================= 2. CRM (crm.lead) =================
    {
        "question": "Quelles opportunités liées à la campagne marketing 'Promo Hiver' ont été gagnées par le vendeur Jean ?",
        "expected_model": "crm.lead",
        "expected_fields": ["campaign_id", "user_id", "stage_id"]
    },
    {
        "question": "Liste des pistes perdues avec le motif 'Trop cher' appartenant à l'équipe de vente Ventes Directes.",
        "expected_model": "crm.lead",
        "expected_fields": ["lost_reason_id", "team_id"]
    },
    {
        "question": "Quel est le revenu espéré des opportunités rattachées au client Microsoft et créées le mois dernier ?",
        "expected_model": "crm.lead",
        "expected_fields": ["partner_id", "expected_revenue", "create_date"]
    },
    {
        "question": "Quels prospects ont une réunion planifiée avec le manager de l'équipe commerciale ?",
        "expected_model": "crm.lead",
        "expected_fields": ["activity_calendar_event_id", "team_id"]
    },

    # ================= 3. ACHATS (purchase.order) =================
    {
        "question": "Quelles commandes d'achat ont été envoyées au fournisseur 'Dell' pour la filiale 'Tech Belgique' ?",
        "expected_model": "purchase.order",
        "expected_fields": ["partner_id", "company_id", "state"]
    },
    {
        "question": "Liste les lignes d'achat associées à la demande de prix 'RFQ123' incluant la taxe 'TVA 20%'.",
        "expected_model": "purchase.order.line",
        "expected_fields": ["order_id", "taxes_id"]
    },
    {
        "question": "Combien de factures fournisseurs sont générées à partir des bons de commande du vendeur Marc ?",
        "expected_model": "purchase.order",
        "expected_fields": ["invoice_ids", "user_id"]
    },
    {
        "question": "Quel est le délai moyen de livraison configuré pour le produit 'Souris' chez le partenaire 'Logitech' ?",
        "expected_model": "product.supplierinfo",
        "expected_fields": ["product_tmpl_id", "partner_id", "delay"]
    },

    # ================= 4. COMPTABILITÉ (account.move, account.analytic) =================
    {
        "question": "Quels sont les comptes analytiques appartenant au client 'Amazon' avec un solde créditeur ?",
        "expected_model": "account.analytic.account",
        "expected_fields": ["partner_id", "credit"]
    },
    {
        "question": "Quelles factures fournisseurs ont été payées via le journal bancaire BRED ?",
        "expected_model": "account.move",
        "expected_fields": ["journal_id", "payment_state", "move_type"]
    },
    {
        "question": "Liste des lignes d'écritures comptables rattachées au compte général '411 Clients' pour la devise EUR.",
        "expected_model": "account.move.line",
        "expected_fields": ["account_id", "currency_id", "debit", "credit"]
    },
    {
        "question": "Quels sont les comptes comptables de type 'Banque et Caisse' liés à la société 'MaBoite' ?",
        "expected_model": "account.account",
        "expected_fields": ["account_type", "company_id"]
    },
    {
        "question": "Montre moi les conditions de paiement appliquées sur les avoirs clients créés par le vendeur Alice.",
        "expected_model": "account.move",
        "expected_fields": ["invoice_payment_term_id", "invoice_user_id", "move_type"]
    },
    {
        "question": "Quel est le montant des taxes liées aux factures associées au compte analytique 'Projet Web' ?",
        "expected_model": "account.move.line",
        "expected_fields": ["tax_ids", "analytic_account_id"]
    },
    {
        "question": "Quels sont les comptes bancaires (avec la banque associée) enregistrés pour le partenaire Google ?",
        "expected_model": "res.partner.bank",
        "expected_fields": ["partner_id", "bank_id"]
    },

    # ================= 5. INVENTAIRE (stock.picking, stock.quant) =================
    {
        "question": "Quels bons de livraison (pickings) sont en attente pour l'emplacement 'Paris Central' et le client 'Tesla' ?",
        "expected_model": "stock.picking",
        "expected_fields": ["picking_type_id", "location_id", "partner_id"]
    },
    {
        "question": "Quels mouvements de stock ont été réalisés pour le produit 'Clavier' depuis l'emplacement 'Stock de base' vers la destination 'Client' ?",
        "expected_model": "stock.move",
        "expected_fields": ["product_id", "location_id", "location_dest_id"]
    },
    {
        "question": "Combien de quantités réelles du produit 'Ecran 24' sont disponibles dans le lot 'L-2023' sur l'emplacement A1 ?",
        "expected_model": "stock.quant",
        "expected_fields": ["product_id", "lot_id", "location_id", "quantity"]
    },
    {
        "question": "Quelles règles de réapprovisionnement sont configurées pour le produit 'Papier' dans la société filiale 'Z' ?",
        "expected_model": "stock.warehouse.orderpoint",
        "expected_fields": ["product_id", "company_id"]
    },
    {
        "question": "Quels transferts internes ont été validés et terminés par l'utilisateur 'Admin' aujourd'hui ?",
        "expected_model": "stock.picking",
        "expected_fields": ["picking_type_id", "write_uid", "date_done"]
    },

    # ================= 6. RESSOURCES HUMAINES (hr.applicant, hr.employee) =================
    {
        "question": "Combien de candidatures ont été affectées au poste de 'Développeur Python' dans le département IT ?",
        "expected_model": "hr.applicant",
        "expected_fields": ["job_id", "department_id"]
    },
    {
        "question": "Quels candidats recrutés par le recruteur 'Marc' ont une réunion planifiée dans leur calendrier ?",
        "expected_model": "hr.applicant",
        "expected_fields": ["user_id", "activity_calendar_event_id"]
    },
    {
        "question": "Quels employés sont sous la responsabilité du manager 'Sophie' et travaillent sur le lieu de travail de Paris ?",
        "expected_model": "hr.employee",
        "expected_fields": ["parent_id", "work_location_id"]
    },
    {
        "question": "Liste les contrats de travail en cours pour les employés de la société 'TechCorp' avec leur salaire de base.",
        "expected_model": "hr.contract",
        "expected_fields": ["employee_id", "company_id", "wage", "state"]
    },
    {
        "question": "Combien de jours de congés de type 'Maladie' ont été validés par le manager RH 'Paul' ?",
        "expected_model": "hr.leave",
        "expected_fields": ["holiday_status_id", "state", "employee_id"]
    },
    {
        "question": "Quelles notes de frais ont été soumises par l'employé 'Alice' et approuvées par le journal 'Espèces' ?",
        "expected_model": "hr.expense",
        "expected_fields": ["employee_id", "journal_id", "state"]
    },
    {
        "question": "Quelles sont les feuilles de temps (timesheets) encodées par l'employé 'Jean' sur la tâche 'Développement' du projet X ?",
        "expected_model": "account.analytic.line",
        "expected_fields": ["employee_id", "task_id", "project_id"]
    },

    # ================= 7. PRODUCTION / MRP (mrp.bom, mrp.production) =================
    {
        "question": "Quelles nomenclatures (BoM) de type 'Kit' sont utilisées par la société 'Meubles SA' ?",
        "expected_model": "mrp.bom",
        "expected_fields": ["type", "company_id"]
    },
    {
        "question": "Quels composants sont nécessaires pour fabriquer le produit 'Table Rouge' selon sa nomenclature ?",
        "expected_model": "mrp.bom.line",
        "expected_fields": ["bom_id", "product_id"]
    },
    {
        "question": "Montre moi les ordres de fabrication clôturés affectés au compte analytique 'Production 2024'.",
        "expected_model": "mrp.production",
        "expected_fields": ["state", "analytic_account_id"]
    },
    {
        "question": "Quels sont les ordres de travail en cours sur le poste de charge 'Assemblage' ?",
        "expected_model": "mrp.workorder",
        "expected_fields": ["workcenter_id", "state"]
    },

    # ================= 8. PROJETS (project.project, project.task) =================
    {
        "question": "Quels projets appartenant au client 'Tesla' sont supervisés par le chef de projet 'Elon' ?",
        "expected_model": "project.project",
        "expected_fields": ["partner_id", "user_id"]
    },
    {
        "question": "Liste des tâches assignées à l'utilisateur 'Bob' qui sont dans l'étape Kanban 'En test'.",
        "expected_model": "project.task",
        "expected_fields": ["user_ids", "stage_id"]
    },
    {
        "question": "Combien d'heures effectives ont été pointées sur les tâches du projet 'Refonte ERP' facturables au client ?",
        "expected_model": "project.task",
        "expected_fields": ["project_id", "effective_hours", "partner_id"]
    },

    # ================= 9. CONTACTS & PARTENAIRES (res.partner) =================
    {
        "question": "Quelles sont les sociétés clientes qui appartiennent au pays 'France' et à la catégorie 'VIP' ?",
        "expected_model": "res.partner",
        "expected_fields": ["is_company", "country_id", "category_id"]
    },
    {
        "question": "Trouve tous les contacts individuels rattachés à la société parente 'Agrolait' avec l'étiquette 'Fournisseur'.",
        "expected_model": "res.partner",
        "expected_fields": ["parent_id", "category_id"]
    },
    {
        "question": "Quels sont les utilisateurs Odoo (employés) liés à la société 'Startup' ?",
        "expected_model": "res.users",
        "expected_fields": ["employee_id", "company_id"]
    },

    # ================= 10. CALENDRIER, FLOTTE & DIVERS =================
    {
        "question": "Quels événements du calendrier (réunions) sont organisés par 'Alice' avec les participants du client 'Decathlon' ?",
        "expected_model": "calendar.event",
        "expected_fields": ["user_id", "partner_ids"]
    },
    {
        "question": "Quelles activités (rappels) sont assignées à l'utilisateur 'Marc' sur des opportunités CRM pour cette semaine ?",
        "expected_model": "crm.lead",
        "expected_fields": ["activity_user_id", "activity_type_id"]
    },
    {
        "question": "Montre moi les véhicules de la flotte conduits par l'employé 'Jean' avec le modèle 'Peugeot 208'.",
        "expected_model": "fleet.vehicle",
        "expected_fields": ["driver_id", "model_id"]
    },
    {
        "question": "Quels contrats de location de véhicules sont actifs pour la société 'Transports SA' ?",
        "expected_model": "fleet.vehicle.log.contract",
        "expected_fields": ["state", "company_id"]
    },
    {
        "question": "Quelles variantes de produits ont un code barre défini et appartiennent à la catégorie 'Bureautique' ?",
        "expected_model": "product.product",
        "expected_fields": ["barcode", "categ_id"]
    },
    {
        "question": "Quelles sont les catégories de produits parentes associées à la stratégie de retrait 'FIFO' ?",
        "expected_model": "product.category",
        "expected_fields": ["parent_id", "removal_strategy_id"]
    }
]


def run_tests():
    print("🚀 Lancement de la suite de tests V3 (Indexation Contextuelle)...\n")
    start_time = time.time()

    success_models = 0
    success_fields = 0

    for i, test in enumerate(TEST_CASES, 1):
        question = test["question"]
        expected_model = test["expected_model"]
        expected_fields = test.get("expected_fields", [])

        # Interrogation du RAG
        predicted_models, predicted_fields = search_rag_v3(question)

        print(f"[{i}/{len(TEST_CASES)}] Q: '{question}'")

        # Vérification du Modèle
        model_ok = expected_model in predicted_models
        if model_ok:
            rank = predicted_models.index(expected_model) + 1
            print(f"  ✅ MODÈLE TROUVÉ : {expected_model} (Rang {rank})")
            success_models += 1

            # Vérification des Champs (Uniquement si le modèle a été trouvé en rang 1)
            if rank == 1 and expected_fields:
                fields_ok = all(f in predicted_fields for f in expected_fields)
                if fields_ok:
                    print(f"  ✅ CHAMPS TROUVÉS : {expected_fields} (parmi {predicted_fields[:4]}...)")
                    success_fields += 1
                else:
                    print(f"  ❌ CHAMPS MANQUANTS : On attendait {expected_fields}, on a eu {predicted_fields}")
        else:
            print(f"  ❌ MODÈLE ÉCHOUÉ : Attendu {expected_model}, Obtenus {predicted_models}")

        print("-" * 50)

    # Calcul des scores finaux
    total_tests = len(TEST_CASES)
    tests_with_fields = sum(1 for t in TEST_CASES if t.get("expected_fields"))
    exec_time = time.time() - start_time

    print("\n==================================================")
    print("📊 RAPPORT FINAL (SOLUTION B - V3)")
    print("==================================================")
    print(f"🎯 Modèles trouvés (Top 3) : {success_models}/{total_tests}")
    print(f"🎯 Champs trouvés (Top 10) : {success_fields}/{tests_with_fields} (parmi les modèles exacts)")
    print(f"\n⏱️ Temps d'exécution total: {exec_time:.1f} sec")


if __name__ == "__main__":
    run_tests()
