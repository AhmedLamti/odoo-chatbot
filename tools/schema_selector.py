import logging
from db.schema_cache import SchemaCache
from tools.cerebras_client import call_cerebras
from config.schema_descriptions import SCHEMA_DESCRIPTIONS, SEMANTIC_JOIN_RULES

logger = logging.getLogger(__name__)

KEYWORD_TABLE_MAP = {
    "client": ["res_partner", "sale_order"],
    "clients": ["res_partner", "sale_order"],
    "customer": ["res_partner", "sale_order"],
    "fournisseur": ["res_partner", "purchase_order"],
    "supplier": ["res_partner", "purchase_order"],
    "vente": ["sale_order", "sale_order_line"],
    "ventes": ["sale_order", "sale_order_line"],
    "commande": ["sale_order", "sale_order_line"],
    "commandes": ["sale_order", "sale_order_line"],
    "meilleure": ["sale_order", "res_partner"],
    "meilleures": ["sale_order", "res_partner"],
    "vendeur": ["sale_order", "res_users", "res_partner"],
    "commercial": ["sale_order", "res_users", "res_partner"],
    "sale": ["sale_order", "sale_order_line"],
    "chiffre": ["sale_order"],
    "affaires": ["sale_order"],
    "revenue": ["sale_order"],
    "facture": ["account_move", "account_move_line", "res_partner"],
    "factures": ["account_move", "account_move_line", "res_partner"],
    "invoice": ["account_move", "res_partner"],
    "impayé": ["account_move"],
    "impayées": ["account_move"],
    "paiement": ["account_payment", "account_move"],
    "produit": ["product_template", "product_product"],
    "produits": ["product_template", "product_product"],
    "product": ["product_template", "product_product"],
    "stock": ["stock_quant", "product_product", "product_template"],
    "inventaire": ["stock_quant", "product_product", "product_template"],
    "achat": ["purchase_order", "res_partner"],
    "achats": ["purchase_order", "res_partner"],
    "employé": ["hr_employee", "hr_department"],
    "employés": ["hr_employee", "hr_department"],
    "employee": ["hr_employee", "hr_department"],
    "département": ["hr_department", "hr_employee"],
    "lead": ["crm_lead", "crm_stage"],
    "opportunité": ["crm_lead", "crm_stage"],
    "projet": ["project_project", "project_task"],
    "tâche": ["project_task", "project_project"],
}

AUTO_INCLUDE = {
    "sale_order_line": ["product_product", "product_template"],
    "product_product": ["product_template"],
    "hr_employee": ["hr_department"],
    "crm_lead": ["crm_stage"],
    "stock_quant": ["product_product", "product_template"],
}


class SchemaSelector:
    def __init__(self):
        self.cache = SchemaCache()
        self.full_schema = self.cache.load()

    def _detect_tables_by_keywords(self, question: str) -> list[str]:
        question_lower = question.lower()
        relevant_tables = set()
        for keyword, tables in KEYWORD_TABLE_MAP.items():
            if keyword in question_lower:
                relevant_tables.update(tables)
        # Tables liées automatiquement
        for t in list(relevant_tables):
            if t in AUTO_INCLUDE:
                relevant_tables.update(AUTO_INCLUDE[t])
        return list(relevant_tables)

    def _detect_tables_by_llm(self, question: str) -> list[str]:
        available_tables = list(self.full_schema.keys())
        try:
            content = call_cerebras(
                prompt=f'Question: "{question}"\nAvailable tables: {", ".join(available_tables)}\nWhich tables needed? Reply ONLY comma-separated table names.',
                system="You are an Odoo 16 database expert. Return ONLY table names separated by commas.",
                max_tokens=50,
                temperature=0,
            )
            tables = [t.strip() for t in content.split(",")]
            return [t for t in tables if t in self.full_schema]
        except Exception as e:
            logger.error(f"Erreur LLM schema selection: {e}")
            return []

    def get_relevant_schema(self, question: str) -> str:
        # Détection tables
        tables = self._detect_tables_by_keywords(question)
        logger.info(f"Tables détectées: {tables}")

        if not tables:
            tables = self._detect_tables_by_llm(question)

        if not tables:
            tables = ["res_partner", "sale_order", "account_move", "product_template"]
            logger.warning(f"Fallback tables: {tables}")

        lines = []

        # 1 — Règles critiques toujours présentes
        lines.append("=== CRITICAL RULES ===")
        lines.append("- sale_order WHERE state IN ('sale','done') → ventes confirmées")
        lines.append("- account_move WHERE move_type='out_invoice' AND state='posted' → factures clients")
        lines.append("- product_template.name is JSONB → COALESCE(pt.name->>'fr_FR', pt.name->>'en_US', pt.name::text)")
        lines.append("- COUNT only when question asks 'combien'/'how many' — otherwise SELECT columns")
        lines.append("- 'meilleur/meilleures/top' → ORDER BY montant/quantité DESC LIMIT 10")
        lines.append("- NEVER use sale_order_line.name as vendeur — vendeur = sale_order.user_id → res_users → res_partner.name")
        lines.append("")

        # 2 — Règles JOIN sémantiques
        lines.append("=== SEMANTIC FIELD MEANINGS ===")
        lines.append(SEMANTIC_JOIN_RULES)
        lines.append("")

        # 3 — Schéma des tables avec descriptions
        lines.append("=== RELEVANT TABLES ===")
        skip_cols = {"create_uid", "write_uid", "message_main_attachment_id",
                     "campaign_id", "source_id", "medium_id", "access_token",
                     "signed_by", "signed_on", "require_signature", "require_payment"}

        for table in tables:
            if table not in self.full_schema:
                continue
            info = self.full_schema[table]
            desc = SCHEMA_DESCRIPTIONS.get(table, {})
            table_desc = desc.get("_description", "")

            lines.append(f"\nTable: {table}" + (f"  -- {table_desc}" if table_desc else ""))
            lines.append("Columns:")

            for col in info["columns"]:
                col_name = col["column_name"]
                if col_name in skip_cols:
                    continue
                col_type = col["data_type"]
                semantic = desc.get(col_name, "")
                semantic_str = f"  ← {semantic}" if semantic else ""
                lines.append(f"  {col_name} ({col_type}){semantic_str}")

            # FK importantes
            important_fks = [
                fk for fk in info["foreign_keys"]
                if fk["column_name"] not in skip_cols
            ]
            if important_fks:
                lines.append("FK:")
                for fk in important_fks[:6]:
                    lines.append(f"  {fk['column_name']} → {fk['foreign_table']}.{fk['foreign_column']}")

        schema_text = "\n".join(lines)
        logger.info(f"Schéma: {len(schema_text)} chars, tables: {tables}")
        return schema_text
