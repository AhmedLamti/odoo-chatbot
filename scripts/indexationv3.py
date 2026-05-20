import json
import time
import uuid

import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434"
EMBEDDING_MODEL = "bge-m3"
VECTOR_SIZE = 1024  # Modifiez si votre modèle d'embedding a une taille différente

# Nouvelles collections pour éviter d'écraser vos tests précédents
COL_MODELS = "odoo_models_v3"
COL_FIELDS = "odoo_fields_v3"

# ==========================================
# 🛑 LISTE NOIRE (Modèles à exclure)
# ==========================================
BLACKLIST_MODELS = [
    # Modèles Web & Techniques
    "web_editor.converter.test", "web_editor.converter.test.sub", "web_tour.tour",
    "privacy.log", "chatbot.message", "chatbot.script", "chatbot.script.answer",
    "chatbot.script.step", "ai.agent.message", "ai.agent.thread", "auth_totp.device",

    # Modèles d'utilisateurs techniques & logs
    "res.users.settings", "res.users.settings.volumes", "res.users.apikeys",
    "res.users.apikeys.show", "res.users.deletion", "res.users.log",

    # Modèles de Templates & Configuration (Le plus gros du "bruit")
    "sale.order.template", "sale.order.template.line", "sale.order.template.option",
    "sale.order.option", "account.account.template", "account.chart.template",
    "account.fiscal.position.account.template", "account.fiscal.position.template",
    "account.tax.template", "account.tax.repartition.line.template",
    "account.reconcile.model", "account.reconcile.model.line", "account.reconcile.model.template",
    "account.reconcile.model.line.template", "account.reconcile.model.partner.mapping",
    "account.group.template", "account.fiscal.position.tax.template",

    # Modèles de Rapports & Statistiques pures (L'IA doit requêter les vraies tables, pas les rapports)
    "account.report", "account.report.column", "account.report.expression",
    "account.report.external.value", "account.report.line", "account.invoice.report",
    "purchase.report", "sale.report", "hr.leave.report", "hr.leave.report.calendar",
    "hr.leave.employee.type.report", "hr.attendance.report", "fleet.vehicle.cost.report",
    "im_livechat.report.channel", "im_livechat.report.operator", "crm.activity.report",
    "project.task.burndown.chart.report", "vendor.delay.report", "digest.digest", "digest.tip",

    # Modèles inutiles pour la recherche (API, Mailing, etc.)
    "phone.blacklist", "snailmail.confirm", "snailmail.letter", "sms.sms", "sms.template",
    "iap.account", "crm.iap.lead.mining.request", "crm.iap.lead.industry", "crm.iap.lead.role",
    "crm.iap.lead.seniority", "fetchmail.server", "res.partner.autocomplete.sync",
    "purchase.bill.union", "account.root", "barcode.nomenclature", "barcode.rule",
    "spreadsheet.dashboard", "spreadsheet.dashboard.group", "decimal.precision"
]

# Liste des champs techniques Odoo à ne JAMAIS indexer
BLACKLIST_FIELDS = [
    'write_uid', 'write_date', 'create_uid', 'create_date', '__last_update',
    'display_name', 'id', 'message_main_attachment_id', 'message_follower_ids',
    'message_ids', 'message_has_error', 'message_has_error_counter',
    'message_needaction', 'message_needaction_counter', 'message_has_sms_error',
    'activity_ids', 'activity_state', 'activity_user_id', 'activity_type_id',
    'activity_date_deadline', 'my_activity_date_deadline', 'activity_summary',
    'message_is_follower', 'message_attachment_count', 'website_message_ids'
]

# ==========================================
# 🎯 DICTIONNAIRE DES POIDS & MOTS CLÉS (CORE MODELS)
# ==========================================
ODOO_CORE_MODELS = {
    "res.partner": {"weight": 1.25,
                    "keywords": "client, fournisseur, contact, société, adresse, facturation, téléphone, email"},
    "account.move": {"weight": 1.25, "keywords": "facture, avoir, paiement, comptabilité, impayé, dû"},
    "sale.order": {"weight": 1.25, "keywords": "devis, commande, vente, chiffre d'affaires, commercial"},
    "stock.quant": {"weight": 1.25, "keywords": "stock, quantité, inventaire, disponible, emplacement, entrepôt"},
    "hr.employee": {"weight": 1.20, "keywords": "employé, salarié, travailleur, personnel, rh"},
    "product.template": {"weight": 1.20, "keywords": "produit, article, catalogue, prix, référence"},
    "hr.applicant": {"weight": 1.20, "keywords": "candidat, candidature, recrutement, embauche"},
    "hr.job": {"weight": 1.20, "keywords": "poste, offre d'emploi, recrutement"},
    "project.task": {"weight": 1.15, "keywords": "tâche, projet, avancement, heures, planifié"},
    "project.project": {"weight": 1.15, "keywords": "projet, gestion de projet, équipe"},
    "crm.lead": {"weight": 1.15, "keywords": "opportunité, piste, prospect, pipeline, gagné, perdu"},
    "purchase.order": {"weight": 1.15, "keywords": "achat, commande fournisseur, rfq, demande de prix"},
    "stock.picking": {"weight": 1.15, "keywords": "livraison, réception, transfert, bon de livraison"},
    "account.payment": {"weight": 1.15, "keywords": "paiement, règlement, encaissement, décaissement"},
    "account.move.line": {"weight": 1.15, "keywords": "écriture comptable, ligne de facture, débit, crédit"},
    "hr.contract": {"weight": 1.15, "keywords": "contrat, salaire, rémunération, date de fin"},
    "hr.attendance": {"weight": 1.15, "keywords": "présence, pointage, check-in, check-out"},
    "account.analytic.line": {"weight": 1.15,
                              "keywords": "feuille de temps, timesheet, heures travaillées, analytique"},
    "account.payment.term": {"weight": 1.15, "keywords": "condition de paiement, échéance, 30 jours"},
    "project.task.type": {"weight": 1.15, "keywords": "étape, statut kanban, colonne projet"},
    "product.product": {"weight": 1.15, "keywords": "variante de produit, code barre, sku"},
    "sale.order.line": {"weight": 1.15, "keywords": "ligne de vente, article vendu, remise, quantité commandée"},
    "res.company": {"weight": 1.10, "keywords": "société, filiale, entreprise principale"},
    "purchase.order.line": {"weight": 1.10, "keywords": "ligne d'achat, article acheté, prix unitaire d'achat"},
    "stock.move": {"weight": 1.10, "keywords": "mouvement de stock, historique d'inventaire"},
    "account.journal": {"weight": 1.10, "keywords": "journal comptable, banque, espèces, ventes, achats"},
    "hr.leave": {"weight": 1.10, "keywords": "congé, absence, time off, vacances"},
    "crm.lost.reason": {"weight": 1.10, "keywords": "motif de perte, raison de refus, opportunité perdue"}
}

qdrant = QdrantClient(url=QDRANT_URL)


def setup_qdrant():
    for col in [COL_MODELS, COL_FIELDS]:
        try:
            qdrant.get_collection(col)
            print(f"🔄 Collection {col} existe déjà.")
        except Exception:
            qdrant.create_collection(
                collection_name=col,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
            )
            print(f"✅ Collection {col} créée.")


def get_embedding(text: str, retries=3):
    payload = {"model": EMBEDDING_MODEL, "prompt": text}
    for attempt in range(retries):
        try:
            res = requests.post(f"{OLLAMA_URL}/api/embeddings", json=payload)
            res.raise_for_status()
            return res.json()["embedding"]
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Erreur Ollama ({e}), tentative {attempt + 1}/{retries} dans 2s...")
            time.sleep(2)
    print(f"❌ Échec définitif pour le texte : {text[:50]}...")
    return None


def run_indexing():
    setup_qdrant()

    # ⚠️ Modifiez le chemin vers votre fichier JSON contenant la structure d'Odoo
    with open('schema_odoo_enrichi_rag_complexe_enriched.json', 'r', encoding='utf-8') as f:
        schema = json.load(f)

    for model_name, data in schema.items():
        # --- 1. FILTRAGE (Action 1) ---
        if model_name in BLACKLIST_MODELS or model_name.startswith("ir") or model_name.startswith("base"):
            continue

        is_core = model_name in ODOO_CORE_MODELS
        magic_words = ODOO_CORE_MODELS[model_name]["keywords"] if is_core else ""
        model_weight = ODOO_CORE_MODELS[model_name]["weight"] if is_core else 1.0
        base_desc = data.get('description_enrichie', data.get('name', ''))

        # --- 2. CONTEXTUALISATION DU MODÈLE (Action 2) ---
        if is_core:
            model_text = f"Modèle Odoo {model_name} ({base_desc}). MOTS CLÉS : {magic_words}."
        else:
            model_text = f"Modèle Odoo {model_name} ({base_desc})."

        print(f"⚙️ Indexation du modèle : {model_name}")
        model_vector = get_embedding(model_text)

        if model_vector:
            qdrant.upsert(
                collection_name=COL_MODELS,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector=model_vector,
                    payload={"model_name": model_name, "description": base_desc, "weight": model_weight}
                    # Poids stocké en base !
                )]
            )

        # --- 3. CONTEXTUALISATION DES CHAMPS (Action 3) ---
        fields_points = []
        for field_name, field_data in data.get('fields', {}).items():
            # FILTRE : On ignore les champs techniques
            if field_name in BLACKLIST_FIELDS or field_name.startswith('activity_'):
                continue

            field_desc = field_data.get('description', '')
            field_type = field_data.get('type', '')
            field_description = field_data.get('description_enrichie', '')
            # Enrichissement sémantique pour forcer la détection
            # On ajoute des synonymes pour les champs critiques
            field_text = (
                f"Dans le modèle Odoo '{model_name}', le champ technique se nomme '{field_name}'. "
                f"Définition et contexte : {field_description}"
            )

            field_vector = get_embedding(field_text)
            if field_vector:
                fields_points.append(PointStruct(
                    id=str(uuid.uuid4()),
                    vector=field_vector,
                    payload={
                        "model_name": model_name,
                        "field_name": field_name,
                        "type": field_type,
                        "description": field_desc,
                        "description_enrichie": field_description
                    }
                ))

        if fields_points:
            # Upsert par lot pour aller plus vite
            qdrant.upsert(collection_name=COL_FIELDS, points=fields_points)

    print("\n✅ Indexation V3 terminée avec succès !")


if __name__ == "__main__":
    start_time = time.time()
    run_indexing()
    print(f"⏱️ Temps total d'indexation : {time.time() - start_time:.1f} sec")
