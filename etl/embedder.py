import logging
from llama_index.embeddings.ollama import OllamaEmbedding
from config.settings import settings

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """
    Génère les embeddings avec nomic-embed-text via Ollama
    """

    def __init__(self):
        self.embed_model = OllamaEmbedding(
            model_name=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
        )

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """
        Ajoute les embeddings à chaque chunk
        Retourne les chunks enrichis avec le vecteur
        """
        logger.info(f"Génération des embeddings pour {len(chunks)} chunks...")

        embedded_chunks = []
        batch_size = 32

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["content"] for c in batch]

            try:
                embeddings = self.embed_model.get_text_embedding_batch(texts)

                for chunk, embedding in zip(batch, embeddings):
                    embedded_chunks.append({
                        **chunk,
                        "embedding": embedding
                    })

                logger.info(f"Batch {i // batch_size + 1} traité ({len(embedded_chunks)}/{len(chunks)})")

            except Exception as e:
                logger.error(f"Erreur embedding batch {i}: {e}")
                continue

        logger.info(f"Embeddings générés: {len(embedded_chunks)}/{len(chunks)}")
        return embedded_chunks
