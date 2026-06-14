# ── shared/embedding.py ───────────────────────────────────────────────────────
# Singleton d'embedding partagé entre chunker, embedder et retriever.
#
# Problème résolu : instanciation multiple du même modèle Ollama dans
# chunker.py, embedder.py et retriever.py — coûteux et incohérent.
#
# bge-m3 est un modèle à instructions (comme nomic-embed-text-v2-moe).
# Il requiert des préfixes selon le contexte :
#   - ingestion  : "Represent this sentence for searching relevant passages: <text>"
#   - query      : "Represent this sentence for searching relevant passages: <text>"
#
# Note : bge-m3 utilise le même préfixe pour query et document
# (contrairement à nomic qui distingue search_query / search_document).
# Pour une cohérence maximale, on expose les deux constantes explicitement.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from functools import lru_cache

from llama_index.embeddings.ollama import OllamaEmbedding

from config.settings import settings

logger = logging.getLogger(__name__)

# Préfixes bge-m3
# bge-m3 fonctionne bien SANS préfixe (modèle multi-tâche natif),
# mais l'ajout du préfixe standard améliore légèrement les scores
# en mode asymétrique (query courte → passage long).
DOCUMENT_PREFIX = ""   # bge-m3 n'exige pas de préfixe document
QUERY_PREFIX    = ""   # bge-m3 n'exige pas de préfixe query

# Si tu utilises nomic-embed-text-v2-moe à la place, décommente :
# DOCUMENT_PREFIX = "search_document: "
# QUERY_PREFIX    = "search_query: "


@lru_cache(maxsize=1)
def get_embed_model() -> OllamaEmbedding:
    """
    Retourne l'instance partagée du modèle d'embedding Ollama.

    Singleton garanti par @lru_cache — un seul modèle chargé
    en mémoire, partagé entre chunker, embedder et retriever.
    """
    logger.info(
        "[embedding] Initialisation du modèle d'embedding : %s @ %s",
        settings.ollama_embed_model,
        settings.ollama_base_url,
    )
    return OllamaEmbedding(
        model_name=settings.ollama_embed_model,
        base_url=settings.ollama_base_url,
    )


def embed_documents(texts: list[str]) -> list[list[float]]:
    """
    Génère les embeddings pour une liste de textes (mode ingestion).

    Args:
        texts: Textes bruts sans préfixe.

    Returns:
        Liste de vecteurs float.
    """
    model = get_embed_model()
    prefixed = [f"{DOCUMENT_PREFIX}{t}" for t in texts] if DOCUMENT_PREFIX else texts
    return model.get_text_embedding_batch(prefixed)


def embed_query(text: str) -> list[float]:
    """
    Génère l'embedding pour une requête utilisateur (mode retrieval).

    Args:
        text: Requête réécrite par le rewriter.

    Returns:
        Vecteur float.
    """
    model = get_embed_model()
    prefixed = f"{QUERY_PREFIX}{text}" if QUERY_PREFIX else text
    return get_embed_model().get_text_embedding(prefixed)
