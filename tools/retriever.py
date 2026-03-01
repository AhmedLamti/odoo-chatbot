import logging
from llama_index.embeddings.ollama import OllamaEmbedding
from db.vector_store import VectorStoreManager
from config.settings import settings

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    Recherche les chunks pertinents dans Qdrant
    """

    def __init__(self, top_k: int = 5):
        self.top_k = top_k
        self.embed_model = OllamaEmbedding(
            model_name=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
        )
        self.vector_store = VectorStoreManager()

    def retrieve(self, query: str) -> list[dict]:
        """
        Recherche les chunks les plus pertinents pour une query
        """
        logger.info(f"Recherche RAG: '{query}'")

        # Embed la query
        query_embedding = self.embed_model.get_text_embedding(query)

        # Recherche dans Qdrant
        results = self.vector_store.search(
            query_vector=query_embedding,
            top_k=self.top_k,
        )

        logger.info(f"{len(results)} chunks trouvés")
        return results

    def retrieve_as_context(self, query: str) -> str:
        """
        Retourne les résultats formatés en contexte pour le LLM
        """
        results = self.retrieve(query)

        if not results:
            return "Aucun contexte trouvé."

        context_parts = []
        for i, r in enumerate(results):
            source = r["metadata"].get("source", "unknown")
            score = r["score"]
            content = r["content"]
            context_parts.append(
                f"[Source {i+1}: {source} (score: {score:.2f})]\n{content}"
            )

        return "\n\n---\n\n".join(context_parts)
