# ── etl/embedder.py ───────────────────────────────────────────────────────────
# Génère les embeddings pour chaque chunk avant stockage dans Qdrant.
#
# Utilise le singleton partagé de shared/embedding.py pour éviter
# d'instancier le modèle plusieurs fois (chunker + embedder + retriever).
# ──────────────────────────────────────────────────────────────────────────────

import logging

from shared.embedding import embed_documents

logger = logging.getLogger(__name__)

_BATCH_SIZE = 32


class OllamaEmbedder:
    """
    Génère les embeddings via Ollama pour les chunks de documentation.
    """

    def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """
        Ajoute le vecteur d'embedding à chaque chunk.

        Le contenu stocké dans Qdrant (payload) reste inchangé.
        Les préfixes éventuels sont gérés dans shared/embedding.py.

        Args:
            chunks: Liste de dicts ``{content, metadata}``.

        Returns:
            Même liste enrichie d'une clé ``embedding`` (list[float]).
            Les batches en échec sont ignorés (logged).
        """
        logger.info("[embedder] %d chunks à embedder...", len(chunks))

        embedded_chunks: list[dict] = []
        total_batches = -(-len(chunks) // _BATCH_SIZE)  # ceil division

        for batch_idx, batch_start in enumerate(range(0, len(chunks), _BATCH_SIZE)):
            batch = chunks[batch_start : batch_start + _BATCH_SIZE]
            texts = [c["content"] for c in batch]

            try:
                embeddings = embed_documents(texts)

                for chunk, embedding in zip(batch, embeddings):
                    embedded_chunks.append({**chunk, "embedding": embedding})

                logger.info(
                    "[embedder] Batch %d/%d — %d/%d chunks traités",
                    batch_idx + 1,
                    total_batches,
                    len(embedded_chunks),
                    len(chunks),
                )

            except Exception as exc:
                logger.error(
                    "[embedder] Batch %d/%d échoué : %s — ignoré",
                    batch_idx + 1,
                    total_batches,
                    exc,
                )

        logger.info(
            "[embedder] Terminé : %d/%d chunks embeddés",
            len(embedded_chunks),
            len(chunks),
        )
        return embedded_chunks
