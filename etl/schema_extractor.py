import logging
from db.sql_connector import SQLConnector
from db.schema_cache import SchemaCache

logger = logging.getLogger(__name__)

# Tables Odoo importantes pour le SQL Agent
ODOO_CORE_TABLES = [
    # Ventes
    "sale_order", "sale_order_line",
    # Achats
    "purchase_order", "purchase_order_line",
    # Facturation
    "account_move", "account_move_line",
    "account_payment", "account_account",
    # Stock
    "stock_move", "stock_picking", "stock_quant",
    # Produits
    "product_template", "product_product",
    "product_category",
    # Clients / Fournisseurs
    "res_partner",
    # Employés
    "hr_employee", "hr_department",
    # CRM
    "crm_lead",
    # Projet
    "project_project", "project_task",
    # Général
    "res_company", "res_users", "res_currency",
]


class SchemaExtractor:
    """
    Extrait le schéma de la base Odoo et le sauvegarde
    """

    def __init__(self):
        self.connector = SQLConnector()
        self.cache = SchemaCache()

    def extract(self) -> dict:
        """
        Extrait le schéma des tables Odoo importantes
        """
        logger.info("Extraction du schéma Odoo...")

        # Vérifier quelles tables existent vraiment
        all_tables = self.connector.get_tables()
        tables_to_extract = [t for t in ODOO_CORE_TABLES if t in all_tables]

        logger.info(f"{len(tables_to_extract)}/{len(ODOO_CORE_TABLES)} tables trouvées")

        schema = {}
        for table in tables_to_extract:
            logger.info(f"Extraction: {table}")
            columns = self.connector.get_table_columns(table)
            foreign_keys = self.connector.get_foreign_keys(table)

            schema[table] = {
                "columns": columns,
                "foreign_keys": foreign_keys,
            }

        # Sauvegarder le schéma
        self.cache.save(schema)
        logger.info(f"Schéma extrait et sauvegardé : {len(schema)} tables")
        return schema
