import logging
from etl.loader import OdooDocLoader
from etl.chunker import RSTChunker
from etl.embedder import OllamaEmbedder
from db.vector_store import VectorStoreManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ETLPipeline:
    """
    Pipeline ETL complet :
    Load → Chunk → Embed → Store
    """

    def __init__(self):
        self.loader = OdooDocLoader()
        self.chunker = RSTChunker(chunk_size=150, chunk_overlap=30, min_chunk_size=40)
        self.embedder = OllamaEmbedder()
        self.vector_store = VectorStoreManager()

    def run(self):
        logger.info("=== Démarrage ETL Pipeline ===")

        # Étape 1 : Chargement
        logger.info(">>> ÉTAPE 1 : Chargement des fichiers GitHub")
        documents = self.loader.load_all()

        # Étape 2 : Chunking
        logger.info(">>> ÉTAPE 2 : Chunking des documents")
        chunks = self.chunker.chunk_documents(documents)

        # Étape 3 : Embeddings
        logger.info(">>> ÉTAPE 3 : Génération des embeddings")
        embedded_chunks = self.embedder.embed_chunks(chunks)

        # Étape 4 : Stockage dans Qdrant
        logger.info(">>> ÉTAPE 4 : Stockage dans Qdrant")
        self.vector_store.upsert(embedded_chunks)

        logger.info(f"=== ETL terminé : {len(embedded_chunks)} chunks indexés ===")
