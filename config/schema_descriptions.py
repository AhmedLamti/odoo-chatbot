"""
Descriptions sémantiques des colonnes importantes par table.
Permet au LLM de comprendre la signification métier de chaque champ.
"""

SCHEMA_DESCRIPTIONS = {
    "sale_order": {
        "_description": "Commandes de vente clients confirmées",
        "id": "identifiant unique de la commande",
        "name": "numéro de commande (ex: S00001)",
        "state": "statut: 'draft'=devis, 'sale'=confirmée, 'done'=terminée, 'cancel'=annulée",
        "partner_id": "CLIENT → JOIN res_partner rp ON so.partner_id = rp.id",
        "user_id": "VENDEUR/COMMERCIAL → JOIN res_users ru ON so.user_id = ru.id → JOIN res_partner rp ON ru.partner_id = rp.id",
        "team_id": "équipe commerciale → JOIN crm_team",
        "date_order": "date de la commande",
        "amount_untaxed": "montant HT de la commande",
        "amount_tax": "montant TVA",
        "amount_total": "montant TTC total",
        "invoice_status": "statut facturation: 'invoiced', 'to invoice', 'nothing'",
        "currency_id": "devise → JOIN res_currency",
        "warehouse_id": "entrepôt → JOIN stock_warehouse",
    },
    "sale_order_line": {
        "_description": "Lignes de commande (produits dans une commande)",
        "order_id": "commande parent → JOIN sale_order so ON sol.order_id = so.id",
        "product_id": "variante produit → JOIN product_product pp ON sol.product_id = pp.id",
        "name": "description/libellé de la ligne (PAS le nom du vendeur)",
        "product_uom_qty": "quantité commandée",
        "price_unit": "prix unitaire",
        "price_subtotal": "sous-total HT de la ligne",
        "price_total": "sous-total TTC de la ligne",
        "qty_delivered": "quantité livrée",
        "qty_invoiced": "quantité facturée",
        "state": "statut hérité de la commande",
    },
    "res_partner": {
        "_description": "Contacts: clients, fournisseurs, employés",
        "id": "identifiant unique",
        "name": "nom du contact/client/fournisseur",
        "customer_rank": "rang client: > 0 = c'est un client",
        "supplier_rank": "rang fournisseur: > 0 = c'est un fournisseur",
        "active": "TRUE = actif, FALSE = archivé",
        "email": "email",
        "phone": "téléphone",
        "city": "ville",
        "country_id": "pays → JOIN res_country rc ON rp.country_id = rc.id",
        "is_company": "TRUE = société, FALSE = personne",
    },
    "res_users": {
        "_description": "Utilisateurs Odoo (vendeurs, comptables...)",
        "id": "identifiant utilisateur",
        "partner_id": "NOM du vendeur → JOIN res_partner rp ON ru.partner_id = rp.id → rp.name",
        "login": "email de connexion",
        "active": "TRUE = actif",
    },
    "account_move": {
        "_description": "Écritures comptables: factures clients/fournisseurs, avoirs",
        "id": "identifiant",
        "name": "numéro de facture (ex: INV/2024/0001)",
        "move_type": "'out_invoice'=facture client, 'in_invoice'=facture fournisseur, 'out_refund'=avoir client",
        "state": "'draft'=brouillon, 'posted'=validée, 'cancel'=annulée",
        "partner_id": "client/fournisseur → JOIN res_partner",
        "invoice_date": "date de la facture",
        "invoice_date_due": "date d'échéance",
        "amount_untaxed": "montant HT",
        "amount_total": "montant TTC",
        "amount_residual": "montant RESTANT à payer (0 si payée)",
        "payment_state": "'not_paid'=impayée, 'partial'=partiellement payée, 'paid'=payée",
    },
    "product_template": {
        "_description": "Modèles de produits (version principale)",
        "id": "identifiant",
        "name": "JSONB → COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text)",
        "list_price": "prix de vente public",
        "standard_price": "coût du produit",
        "categ_id": "catégorie → JOIN product_category pc ON pt.categ_id = pc.id",
        "type": "'product'=stockable, 'consu'=consommable, 'service'=service",
        "active": "TRUE = actif",
        "sale_ok": "TRUE = peut être vendu",
        "purchase_ok": "TRUE = peut être acheté",
    },
    "product_product": {
        "_description": "Variantes de produits (taille, couleur...)",
        "id": "identifiant variante",
        "product_tmpl_id": "modèle parent → JOIN product_template pt ON pp.product_tmpl_id = pt.id",
        "default_code": "référence interne (SKU)",
        "active": "TRUE = actif",
    },
    "hr_employee": {
        "_description": "Employés de l'entreprise",
        "id": "identifiant",
        "name": "nom complet de l'employé",
        "department_id": "département → JOIN hr_department hd ON he.department_id = hd.id",
        "job_title": "titre du poste",
        "job_id": "fiche de poste → JOIN hr_job",
        "work_email": "email professionnel",
        "active": "TRUE = actif (FALSE = archivé)",
        "parent_id": "manager direct → JOIN hr_employee",
    },
    "hr_department": {
        "_description": "Départements RH",
        "id": "identifiant",
        "name": "nom du département",
        "manager_id": "responsable du département → JOIN hr_employee",
    },
    "purchase_order": {
        "_description": "Commandes d'achat fournisseurs",
        "id": "identifiant",
        "name": "numéro de commande achat (ex: PO00001)",
        "partner_id": "FOURNISSEUR → JOIN res_partner rp ON po.partner_id = rp.id",
        "state": "'draft'=brouillon, 'purchase'=confirmée, 'done'=terminée",
        "date_order": "date de la commande",
        "amount_untaxed": "montant HT",
        "amount_total": "montant TTC",
        "user_id": "acheteur → JOIN res_users",
    },
    "stock_quant": {
        "_description": "Stock disponible par emplacement",
        "product_id": "variante produit → JOIN product_product pp ON sq.product_id = pp.id",
        "location_id": "emplacement → JOIN stock_location sl ON sq.location_id = sl.id",
        "quantity": "quantité disponible (utiliser SUM)",
        "reserved_quantity": "quantité réservée pour livraisons",
    },
    "stock_location": {
        "_description": "Emplacements de stock",
        "usage": "'internal'=stock interne, 'customer'=client, 'supplier'=fournisseur, 'inventory'=ajustement",
        "complete_name": "chemin complet (ex: WH/Stock)",
    },
    "crm_lead": {
        "_description": "Opportunités et leads CRM",
        "id": "identifiant",
        "name": "nom de l'opportunité",
        "type": "'opportunity'=opportunité, 'lead'=prospect",
        "stage_id": "étape du pipeline → JOIN crm_stage cs ON cl.stage_id = cs.id",
        "partner_id": "client lié → JOIN res_partner",
        "user_id": "commercial responsable → JOIN res_users",
        "expected_revenue": "revenu prévu",
        "probability": "probabilité de succès (%)",
        "date_closed": "date de clôture (NULL = en cours)",
        "active": "TRUE = actif",
    },
    "crm_stage": {
        "_description": "Étapes du pipeline CRM",
        "name": "nom de l'étape (ex: Nouveau, Qualifié, Gagné)",
        "sequence": "ordre dans le pipeline",
    },
    "project_project": {
        "_description": "Projets",
        "name": "nom du projet",
        "partner_id": "client du projet",
        "user_id": "chef de projet",
    },
    "project_task": {
        "_description": "Tâches des projets",
        "name": "titre de la tâche",
        "project_id": "projet parent → JOIN project_project",
        "user_ids": "assignés à la tâche",
        "stage_id": "étape de la tâche",
        "date_deadline": "date limite",
    },
}


# Règles de JOIN sémantiques — le LLM doit les mémoriser
SEMANTIC_JOIN_RULES = """
SEMANTIC FIELD MEANINGS (critical for correct queries):

sale_order:
  - partner_id  → CLIENT (rp.name) via JOIN res_partner rp ON so.partner_id = rp.id
  - user_id     → VENDEUR/COMMERCIAL (rp.name) via JOIN res_users ru ON so.user_id = ru.id JOIN res_partner rp ON ru.partner_id = rp.id
  - team_id     → ÉQUIPE COMMERCIALE via JOIN crm_team ct ON so.team_id = ct.id
  - amount_untaxed → montant HT (chiffre d'affaires)
  - amount_total   → montant TTC

sale_order_line:
  - name        → libellé produit/description (JAMAIS le vendeur)
  - product_id  → produit via JOIN product_product pp → product_template pt
  - order_id    → commande parente via JOIN sale_order so

res_users:
  - partner_id  → NOM AFFICHÉ via JOIN res_partner rp ON ru.partner_id = rp.id → rp.name

account_move:
  - move_type='out_invoice' → facture CLIENT
  - move_type='in_invoice'  → facture FOURNISSEUR
  - amount_residual > 0 AND payment_state IN ('not_paid','partial') → IMPAYÉE
"""
