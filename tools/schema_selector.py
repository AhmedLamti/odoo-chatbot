import logging
import requests
from db.schema_cache import SchemaCache
from config.settings import settings

logger = logging.getLogger(__name__)

# Mapping mots-clés → tables pertinentes
KEYWORD_TABLE_MAP = {
    # Clients / Partners
    "client": ["res_partner"],
    "clients": ["res_partner"],
    "customer": ["res_partner"],
    "partner": ["res_partner"],
    "contact": ["res_partner"],
    "fournisseur": ["res_partner"],
    "supplier": ["res_partner"],

    # Ventes
    "vente": ["sale_order", "sale_order_line"],
    "commande": ["sale_order", "sale_order_line"],
    "sale": ["sale_order", "sale_order_line"],
    "order": ["sale_order", "sale_order_line"],
    "chiffre d'affaires": ["sale_order", "sale_order_line"],
    "revenue": ["sale_order", "sale_order_line"],
    "ca": ["sale_order", "sale_order_line"],

    # Factures
    "facture": ["account_move", "account_move_line"],
    "invoice": ["account_move", "account_move_line"],
    "paiement": ["account_payment", "account_move"],
    "payment": ["account_payment", "account_move"],
    "impayé": ["account_move"],
    "unpaid": ["account_move"],

    # Produits
    "produit": ["product_template", "product_product"],
    "product": ["product_template", "product_product"],
    "article": ["product_template", "product_product"],
    "catégorie": ["product_category"],
    "category": ["product_category"],

    # Stock
    "stock": ["stock_quant", "stock_move"],
    "inventaire": ["stock_quant"],
    "inventory": ["stock_quant"],
    "livraison": ["stock_picking"],
    "delivery": ["stock_picking"],

    # Achats
    "achat": ["purchase_order", "purchase_order_line"],
    "purchase": ["purchase_order", "purchase_order_line"],

    # RH
    "employé": ["hr_employee", "hr_department"],
    "employee": ["hr_employee", "hr_department"],
    "employe": ["hr_employee"],
    "département": ["hr_department"],
    "department": ["hr_department"],

    # CRM
    "lead": ["crm_lead"],
    "opportunité": ["crm_lead"],
    "opportunity": ["crm_lead"],
    "prospect": ["crm_lead"],

    # Projet
    "projet": ["project_project", "project_task"],
    "project": ["project_project", "project_task"],
    "tâche": ["project_task"],
    "task": ["project_task"],

    # Général
    "utilisateur": ["res_users"],
    "user": ["res_users"],
    "société": ["res_company"],
    "company": ["res_company"],
    "devise": ["res_currency"],
    "currency": ["res_currency"],
    "compte": ["account_account"],
    "account": ["account_account"],
}


class SchemaSelector:
    """
    Sélectionne dynamiquement les tables pertinentes
    pour une question donnée
    """

    def __init__(self):
        self.cache = SchemaCache()
        self.full_schema = self.cache.load()

    def _detect_tables_by_keywords(self, question: str) -> list[str]:
        """Détecte les tables pertinentes par mots-clés"""
        question_lower = question.lower()
        relevant_tables = set()

        for keyword, tables in KEYWORD_TABLE_MAP.items():
            if keyword in question_lower:
                relevant_tables.update(tables)

        return list(relevant_tables)

    def _detect_tables_by_llm(self, question: str) -> list[str]:
        """Utilise le LLM pour détecter les tables si les mots-clés échouent"""
        available_tables = list(self.full_schema.keys())

        prompt = f"""Given this question about an Odoo database:
"{question}"

Available tables: {', '.join(available_tables)}

Which tables are needed to answer this question?
Reply with ONLY the table names separated by commas, nothing else.
Example: res_partner, sale_order
"""
        try:
            response = requests.post(
                f"{settings.ollama_base_url}/api/chat",
                json={
                    "model": settings.ollama_sql_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=30,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"].strip()

            # Parser les tables retournées
            tables = [t.strip() for t in content.split(",")]
            valid_tables = [t for t in tables if t in self.full_schema]
            return valid_tables

        except Exception as e:
            logger.error(f"Erreur LLM schema selection: {e}")
            return []

    def get_relevant_schema(self, question: str) -> str:
        """
        Retourne le schéma ciblé pour la question
        """
        # Étape 1 : Détection par mots-clés
        tables = self._detect_tables_by_keywords(question)
        logger.info(f"Tables détectées par mots-clés: {tables}")

        # Étape 2 : Si aucune table → utiliser le LLM
        if not tables:
            tables = self._detect_tables_by_llm(question)
            logger.info(f"Tables détectées par LLM: {tables}")

        # Étape 3 : Si toujours rien → envoyer les tables principales
        if not tables:
            tables = ["res_partner", "sale_order", "account_move", "product_template"]
            logger.warning(f"Fallback sur tables principales: {tables}")

        # Construire le schéma ciblé
        lines = [f"Relevant tables for this question:"]
        for table in tables:
            if table in self.full_schema:
                info = self.full_schema[table]
                lines.append(f"\nTable: {table}")
                lines.append("Columns:")
                for col in info["columns"]:
                    nullable = "NULL" if col["is_nullable"] == "YES" else "NOT NULL"
                    lines.append(f"  - {col['column_name']} ({col['data_type']}) {nullable}")
                if info["foreign_keys"]:
                    lines.append("Relations:")
                    for fk in info["foreign_keys"]:
                        lines.append(f"  - {fk['column_name']} → {fk['foreign_table']}.{fk['foreign_column']}")

        schema_text = "\n".join(lines)
        logger.info(f"Schéma ciblé: {len(schema_text)} caractères (vs {49426} avant)")
        return schema_text
