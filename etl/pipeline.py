import logging

from etl.loader import OdooDocLoader
from etl.chunker import SemanticRSTChunker
from etl.embedder import OllamaEmbedder
from db.vector_store import VectorStoreManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ETLPipeline:
    """
    Pipeline ETL complet :
      1. Load    — télécharge les fichiers RST depuis GitHub (avec cache)
      2. Chunk   — chunking sémantique via SemanticRSTChunker
      3. Embed   — génère les vecteurs avec préfixe search_document:
      4. Store   — upsert dans Qdrant
    """

    def __init__(self):
        self.loader      = OdooDocLoader()
        self.chunker     = SemanticRSTChunker()
        self.embedder    = OllamaEmbedder()
        self.vector_store = VectorStoreManager()

    def run(self):
        logger.info("=== Démarrage ETL Pipeline ===")

        # Étape 1 : Chargement
        logger.info(">>> ÉTAPE 1 : Chargement des fichiers GitHub")
        documents = self.loader.load_all()
        logger.info("    %d documents chargés", len(documents))

        # Étape 2 : Chunking sémantique
        logger.info(">>> ÉTAPE 2 : Chunking sémantique")
        chunks = self.chunker.chunk_documents(documents)
        logger.info("    %d chunks produits", len(chunks))

        # Étape 3 : Embeddings (avec préfixe search_document:)
        logger.info(">>> ÉTAPE 3 : Génération des embeddings")
        embedded_chunks = self.embedder.embed_chunks(chunks)
        logger.info("    %d chunks embeddés", len(embedded_chunks))

        # Étape 4 : Stockage dans Qdrant
        logger.info(">>> ÉTAPE 4 : Stockage dans Qdrant")
        self.vector_store.upsert(embedded_chunks)

        logger.info("=== ETL terminé : %d chunks indexés ===", len(embedded_chunks))
