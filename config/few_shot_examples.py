"""
Few-shot examples générés depuis schema.yaml réel
À coller dans sql_node.py et chart_node.py
"""

# ============================================================
# SQL_FEW_SHOT_EXAMPLES — à mettre dans sql_node.py
# ============================================================

SQL_FEW_SHOT_EXAMPLES = """
EXAMPLES (use EXACT column names from schema):

-- VENTES / CHIFFRE D'AFFAIRES --

Q: Quel est le chiffre d'affaires total ?
A: SELECT ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires_total
   FROM sale_order so
   WHERE so.state IN ('sale', 'done');

Q: Chiffre d'affaires par mois
A: SELECT TO_CHAR(so.date_order, 'YYYY-MM') AS mois,
          ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires
   FROM sale_order so
   WHERE so.state IN ('sale', 'done')
   GROUP BY TO_CHAR(so.date_order, 'YYYY-MM')
   ORDER BY mois
   LIMIT 12;

Q: Chiffre d'affaires par mois cette année
A: SELECT TO_CHAR(so.date_order, 'YYYY-MM') AS mois,
          ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires
   FROM sale_order so
   WHERE so.state IN ('sale', 'done')
     AND EXTRACT(YEAR FROM so.date_order) = EXTRACT(YEAR FROM CURRENT_DATE)
   GROUP BY TO_CHAR(so.date_order, 'YYYY-MM')
   ORDER BY mois;

Q: Nombre de commandes de vente
A: SELECT COUNT(*) AS nombre_commandes
   FROM sale_order so
   WHERE so.state IN ('sale', 'done');

Q: Top 10 clients par chiffre d'affaires
A: SELECT rp.name AS client,
          ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires
   FROM sale_order so
   JOIN res_partner rp ON so.partner_id = rp.id
   WHERE so.state IN ('sale', 'done')
   GROUP BY rp.name
   ORDER BY chiffre_affaires DESC
   LIMIT 10;

Q: Ventes par commercial / vendeur
A: SELECT ru_partner.name AS vendeur,
          COUNT(so.id) AS nb_commandes,
          ROUND(SUM(so.amount_untaxed)::numeric, 2) AS chiffre_affaires
   FROM sale_order so
   JOIN res_users ru ON so.user_id = ru.id
   JOIN res_partner ru_partner ON ru.partner_id = ru_partner.id
   WHERE so.state IN ('sale', 'done')
   GROUP BY ru_partner.name
   ORDER BY chiffre_affaires DESC;

-- PRODUITS --

Q: Top 10 produits les plus vendus
A: SELECT COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS produit,
          SUM(sol.product_uom_qty) AS quantite_vendue,
          ROUND(SUM(sol.price_subtotal)::numeric, 2) AS total_ventes
   FROM sale_order_line sol
   JOIN sale_order so ON sol.order_id = so.id
   JOIN product_product pp ON sol.product_id = pp.id
   JOIN product_template pt ON pp.product_tmpl_id = pt.id
   WHERE so.state IN ('sale', 'done')
   GROUP BY pt.name
   ORDER BY quantite_vendue DESC
   LIMIT 10;

Q: Liste des produits avec leur prix
A: SELECT COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS produit,
          pt.list_price AS prix,
          pc.name AS categorie
   FROM product_template pt
   JOIN product_category pc ON pt.categ_id = pc.id
   WHERE pt.active = TRUE AND pt.sale_ok = TRUE
   ORDER BY pt.list_price DESC
   LIMIT 20;

Q: Quantité vendue par produit
A: SELECT COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS produit,
          SUM(sol.product_uom_qty) AS quantite_vendue
   FROM sale_order_line sol
   JOIN sale_order so ON sol.order_id = so.id
   JOIN product_product pp ON sol.product_id = pp.id
   JOIN product_template pt ON pp.product_tmpl_id = pt.id
   WHERE so.state IN ('sale', 'done')
   GROUP BY pt.name
   ORDER BY quantite_vendue DESC
   LIMIT 15;

-- CLIENTS --

Q: Combien de clients avons-nous ?
A: SELECT COUNT(*) AS nombre_clients
   FROM res_partner rp
   WHERE rp.customer_rank > 0
     AND rp.active = TRUE;

Q: Liste des clients
A: SELECT rp.name AS client,
          rp.email,
          rp.phone,
          rp.city AS ville
   FROM res_partner rp
   WHERE rp.customer_rank > 0
     AND rp.active = TRUE
   ORDER BY rp.name
   LIMIT 20;

Q: Clients par pays
A: SELECT rc.name AS pays,
          COUNT(rp.id) AS nombre_clients
   FROM res_partner rp
   JOIN res_country rc ON rp.country_id = rc.id
   WHERE rp.customer_rank > 0
     AND rp.active = TRUE
   GROUP BY rc.name
   ORDER BY nombre_clients DESC;

-- FACTURES --

Q: Factures impayées
A: SELECT am.name AS facture,
          rp.name AS client,
          am.invoice_date AS date_facture,
          am.invoice_date_due AS date_echeance,
          ROUND(am.amount_residual::numeric, 2) AS montant_restant
   FROM account_move am
   JOIN res_partner rp ON am.partner_id = rp.id
   WHERE am.move_type = 'out_invoice'
     AND am.state = 'posted'
     AND am.payment_state IN ('not_paid', 'partial')
   ORDER BY am.invoice_date_due ASC
   LIMIT 20;

Q: Total des factures par mois
A: SELECT TO_CHAR(am.invoice_date, 'YYYY-MM') AS mois,
          ROUND(SUM(am.amount_untaxed)::numeric, 2) AS total_factures
   FROM account_move am
   WHERE am.move_type = 'out_invoice'
     AND am.state = 'posted'
   GROUP BY TO_CHAR(am.invoice_date, 'YYYY-MM')
   ORDER BY mois
   LIMIT 12;

Q: Chiffre d'affaires facturé total
A: SELECT ROUND(SUM(am.amount_untaxed)::numeric, 2) AS ca_facture
   FROM account_move am
   WHERE am.move_type = 'out_invoice'
     AND am.state = 'posted';

-- EMPLOYÉS --

Q: Combien d'employés avons-nous ?
A: SELECT COUNT(*) AS nombre_employes
   FROM hr_employee he
   WHERE he.active = TRUE;

Q: Employés par département
A: SELECT hd.name AS departement,
          COUNT(he.id) AS nombre_employes
   FROM hr_employee he
   JOIN hr_department hd ON he.department_id = hd.id
   WHERE he.active = TRUE
   GROUP BY hd.name
   ORDER BY nombre_employes DESC;

Q: Liste des employés
A: SELECT he.name AS employe,
          hd.name AS departement,
          he.job_title AS poste,
          he.work_email AS email
   FROM hr_employee he
   LEFT JOIN hr_department hd ON he.department_id = hd.id
   WHERE he.active = TRUE
   ORDER BY he.name
   LIMIT 20;

-- ACHATS --

Q: Total des achats
A: SELECT ROUND(SUM(po.amount_untaxed)::numeric, 2) AS total_achats
   FROM purchase_order po
   WHERE po.state IN ('purchase', 'done');

Q: Top 10 fournisseurs par montant d'achat
A: SELECT rp.name AS fournisseur,
          ROUND(SUM(po.amount_untaxed)::numeric, 2) AS total_achats
   FROM purchase_order po
   JOIN res_partner rp ON po.partner_id = rp.id
   WHERE po.state IN ('purchase', 'done')
   GROUP BY rp.name
   ORDER BY total_achats DESC
   LIMIT 10;

-- STOCK --

Q: Stock disponible par produit
A: SELECT COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text) AS produit,
          SUM(sq.quantity) AS stock_disponible
   FROM stock_quant sq
   JOIN product_product pp ON sq.product_id = pp.id
   JOIN product_template pt ON pp.product_tmpl_id = pt.id
   WHERE sq.location_id IN (
       SELECT id FROM stock_location WHERE usage = 'internal'
   )
   GROUP BY pt.name
   HAVING SUM(sq.quantity) > 0
   ORDER BY stock_disponible DESC
   LIMIT 20;

-- OPPORTUNITÉS CRM --

Q: Nombre d'opportunités en cours
A: SELECT COUNT(*) AS nb_opportunites
   FROM crm_lead cl
   WHERE cl.type = 'opportunity'
     AND cl.active = TRUE
     AND cl.date_closed IS NULL;

Q: Opportunités par étape
A: SELECT cs.name AS etape,
          COUNT(cl.id) AS nb_opportunites,
          ROUND(SUM(cl.expected_revenue)::numeric, 2) AS revenus_prevus
   FROM crm_lead cl
   JOIN crm_stage cs ON cl.stage_id = cs.id
   WHERE cl.type = 'opportunity'
     AND cl.active = TRUE
   GROUP BY cs.name
   ORDER BY nb_opportunites DESC;
"""

# ============================================================
# DASHBOARD_FEW_SHOT_EXAMPLES — à mettre dans chart_node.py
# ============================================================

DASHBOARD_FEW_SHOT_EXAMPLES = """
CHART TYPE CLASSIFICATION EXAMPLES:

Q: Chiffre d'affaires par mois / évolution / courbe / tendance
→ chart_type: line
→ x_column: mois
→ y_column: chiffre_affaires
→ title: Évolution du chiffre d'affaires par mois

Q: Top produits vendus / comparaison produits / classement
→ chart_type: bar
→ x_column: produit
→ y_column: quantite_vendue
→ title: Top 10 produits les plus vendus

Q: Répartition clients par pays / répartition par département
→ chart_type: pie
→ x_column: pays
→ y_column: nombre_clients
→ title: Répartition des clients par pays

Q: Quantité vs prix / scatter / nuage de points
→ chart_type: scatter
→ x_column: prix
→ y_column: quantite_vendue
→ title: Quantité vendue vs Prix des produits

Q: Factures par mois / évolution facturation
→ chart_type: line
→ x_column: mois
→ y_column: total_factures
→ title: Évolution de la facturation par mois

Q: Ventes par commercial / performance vendeurs
→ chart_type: bar
→ x_column: vendeur
→ y_column: chiffre_affaires
→ title: Chiffre d'affaires par commercial

Q: Employés par département / répartition RH
→ chart_type: pie
→ x_column: departement
→ y_column: nombre_employes
→ title: Répartition des employés par département

Q: Opportunités par étape / pipeline CRM
→ chart_type: bar
→ x_column: etape
→ y_column: nb_opportunites
→ title: Pipeline CRM par étape
"""

# ============================================================
# RÈGLES CRITIQUES — à ajouter dans SQL_SYSTEM_PROMPT
# ============================================================

SQL_CRITICAL_RULES = """
CRITICAL RULES:
1. ALWAYS use table aliases (so, sol, pt, pp, rp, am, he, po, sq...)
2. ALWAYS prefix ALL columns with their alias (so.state, rp.name, pt.name...)
3. NEVER use column names without alias in JOINs
4. product_template.name is JSONB → use COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text)
5. Products: sale_order_line → product_product (pp) → product_template (pt) via pp.product_tmpl_id
6. Customers: res_partner WHERE customer_rank > 0 AND active = TRUE
7. Employees: hr_employee WHERE active = TRUE
8. Sales: sale_order WHERE state IN ('sale', 'done')
9. Invoices: account_move WHERE move_type = 'out_invoice' AND state = 'posted'
10. NEVER use account_invoice (deprecated) → use account_move
11. Return ONLY the SQL query, ending with semicolon
12. NO explanation, NO comment after the semicolon
13. Use ROUND(value::numeric, 2) for monetary amounts
"""

if __name__ == "__main__":
    print("=== SQL FEW-SHOT EXAMPLES ===")
    print(SQL_FEW_SHOT_EXAMPLES)
    print("\n=== DASHBOARD FEW-SHOT EXAMPLES ===")
    print(DASHBOARD_FEW_SHOT_EXAMPLES)
    print("\n=== CRITICAL RULES ===")
    print(SQL_CRITICAL_RULES)
