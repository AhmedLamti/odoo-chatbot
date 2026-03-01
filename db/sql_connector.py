import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config.settings import settings

logger = logging.getLogger(__name__)


class SQLConnector:
    """
    Gère la connexion à la base PostgreSQL Odoo
    """

    def __init__(self):
        self.engine = create_engine(
            settings.postgres_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        self.Session = sessionmaker(bind=self.engine)

    def test_connection(self) -> bool:
        """Teste la connexion à la base"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✓ Connexion PostgreSQL OK")
            return True
        except Exception as e:
            logger.error(f"✗ Connexion PostgreSQL échouée: {e}")
            return False

    def execute_query(self, query: str) -> list[dict]:
        """
        Exécute une requête SQL et retourne les résultats
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                columns = result.keys()
                rows = result.fetchall()
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"Erreur exécution query: {e}")
            raise

    def get_tables(self) -> list[str]:
        """Retourne la liste de toutes les tables Odoo"""
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        results = self.execute_query(query)
        return [r["table_name"] for r in results]

    def get_table_columns(self, table_name: str) -> list[dict]:
        """Retourne les colonnes d'une table"""
        query = f"""
            SELECT 
                column_name,
                data_type,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = '{table_name}'
            ORDER BY ordinal_position
        """
        return self.execute_query(query)

    def get_foreign_keys(self, table_name: str) -> list[dict]:
        """Retourne les clés étrangères d'une table"""
        query = f"""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table,
                ccu.column_name AS foreign_column
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_name = '{table_name}'
        """
        return self.execute_query(query)
