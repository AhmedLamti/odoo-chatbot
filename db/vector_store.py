import logging
import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from config.settings import settings

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    Gère la connexion et les opérations sur Qdrant
    """

    # Dimension de nomic-embed-text
    VECTOR_SIZE = 768

    def __init__(self):
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        self.collection_name = settings.qdrant_collection
        self._init_collection()

    def _init_collection(self):
        """Crée la collection si elle n'existe pas"""
        existing = [c.name for c in self.client.get_collections().collections]

        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Collection '{self.collection_name}' créée")
        else:
            logger.info(f"Collection '{self.collection_name}' déjà existante")

    def upsert(self, embedded_chunks: list[dict], batch_size: int = 100):
        """
        Insère les chunks avec leurs embeddings dans Qdrant
        """
        logger.info(f"Insertion de {len(embedded_chunks)} chunks dans Qdrant...")

        for i in range(0, len(embedded_chunks), batch_size):
            batch = embedded_chunks[i:i + batch_size]

            points = [
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=chunk["embedding"],
                    payload={
                        "content": chunk["content"],
                        **chunk["metadata"],
                    },
                )
                for chunk in batch
            ]

            self.client.upsert(
                collection_name=self.collection_name,
                points=points,
            )

            logger.info(f"Batch {i // batch_size + 1} inséré ({min(i + batch_size, len(embedded_chunks))}/{len(embedded_chunks)})")

        logger.info("Insertion terminée ✓")

    def search(self, query_vector: list[float], top_k: int = 5) -> list[dict]:
        """
        Recherche les chunks les plus proches du vecteur query
        """
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
        ).points

        return [
            {
                "content": r.payload.get("content", ""),
                "metadata": {k: v for k, v in r.payload.items() if k != "content"},
                "score": r.score,
            }
            for r in results
        ]

    def search_with_filter(
            self,
            query_vector: list[float],
            filter_field: str,
            filter_value: str,
            top_k: int = 5,
    ) -> list[dict]:
        """
        Recherche avec filtre sur les métadonnées
        """
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=Filter(
                must=[
                    FieldCondition(
                        key=filter_field,
                        match=MatchValue(value=filter_value),
                    )
                ]
            ),
            limit=top_k,
        ).points

        return [
            {
                "content": r.payload.get("content", ""),
                "metadata": {k: v for k, v in r.payload.items() if k != "content"},
                "score": r.score,
            }
            for r in results
        ]

    def get_collection_info(self) -> dict:
        """Retourne les infos de la collection"""
        info = self.client.get_collection(self.collection_name)
        return {
            "name": self.collection_name,
            "vectors_count": info.points_count,
            "status": str(info.status),
        }

    def delete_collection(self):
        """Supprime la collection (attention !)"""
        self.client.delete_collection(self.collection_name)
        logger.warning(f"Collection '{self.collection_name}' supprimée")
