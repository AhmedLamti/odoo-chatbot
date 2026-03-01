import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path("config/schema.yaml")


class SchemaCache:
    """
    Sauvegarde et charge le schéma DB en YAML
    """

    def save(self, schema: dict):
        """Sauvegarde le schéma dans config/schema.yaml"""
        with open(SCHEMA_PATH, "w", encoding="utf-8") as f:
            yaml.dump(schema, f, allow_unicode=True, default_flow_style=False)
        logger.info(f"Schéma sauvegardé dans {SCHEMA_PATH}")

    def load(self) -> dict:
        """Charge le schéma depuis config/schema.yaml"""
        if not SCHEMA_PATH.exists():
            raise FileNotFoundError(
                f"Schéma non trouvé. Lance d'abord : python scripts/run_schema_extractor.py"
            )
        with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema = yaml.safe_load(f)
        logger.info(f"Schéma chargé : {len(schema)} tables")
        return schema

    def exists(self) -> bool:
        return SCHEMA_PATH.exists()

    def get_schema_as_text(self) -> str:
        """
        Retourne le schéma formaté en texte pour le SQL Agent
        """
        schema = self.load()
        lines = []

        for table, info in schema.items():
            lines.append(f"\nTable: {table}")
            lines.append("Colonnes:")
            for col in info["columns"]:
                nullable = "NULL" if col["is_nullable"] == "YES" else "NOT NULL"
                lines.append(f"  - {col['column_name']} ({col['data_type']}) {nullable}")

            if info["foreign_keys"]:
                lines.append("Relations:")
                for fk in info["foreign_keys"]:
                    lines.append(
                        f"  - {fk['column_name']} → {fk['foreign_table']}.{fk['foreign_column']}"
                    )

        return "\n".join(lines)
