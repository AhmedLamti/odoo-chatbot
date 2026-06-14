# ── agents/rag_agent/retriever.py ─────────────────────────────────────────────
# Recherche sémantique dans Qdrant pour le RAG Agent.
#
# Changements clés vs version précédente :
#   - Suppression des instanciations globales (embed_model, vector_store)
#   - Utilisation de shared/embedding.py (singleton) pour embed_query
#   - VectorStoreManager instancié à la demande (lazy) via get_vector_store()
#   - Toutes les fonctions restent pures (pas d'état global)
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from functools import lru_cache

from db.vector_store import VectorStoreManager
from shared.embedding import embed_query

logger = logging.getLogger(__name__)

MIN_SCORE = 0.30


@lru_cache(maxsize=1)
def _get_vector_store() -> VectorStoreManager:
    """
    Retourne l'instance partagée du VectorStoreManager.
    Lazy init — pas de connexion Qdrant à l'import du module.
    """
    return VectorStoreManager()


def retrieve(query: str, top_k: int = 8) -> list[dict]:
    """
    Recherche les chunks pertinents dans Qdrant pour une requête donnée.

    Args:
        query:  Requête réécrite par le rewriter (anglais technique).
        top_k:  Nombre maximum de résultats bruts à récupérer.

    Returns:
        Liste de chunks filtrés (score >= MIN_SCORE),
        chacun avec ``content``, ``metadata`` et ``score``.
        Liste vide en cas d'erreur.
    """
    try:
        query_vector = embed_query(query)
        results = _get_vector_store().search(
            query_vector=query_vector,
            top_k=top_k,
        )
        filtered = [r for r in results if r.get("score", 0) >= MIN_SCORE]
        logger.info(
            "[retriever] %d/%d chunks au-dessus du seuil (%.2f)",
            len(filtered),
            len(results),
            MIN_SCORE,
        )
        return filtered

    except Exception as exc:
        logger.error("[retriever] Erreur lors de la recherche : %s", exc)
        return []


def format_context(chunks: list[dict]) -> str:
    """
    Formate les chunks en contexte lisible pour le LLM.

    Args:
        chunks: Sortie de ``retrieve()``.

    Returns:
        Chaîne multi-blocs séparés par ``---``.
    """
    if not chunks:
        return "Aucun contexte trouvé."

    parts = [
        f"[Extrait {i + 1} — {chunk['metadata'].get('source', 'unknown')} "
        f"(score: {chunk['score']:.2f})]\n{chunk['content']}"
        for i, chunk in enumerate(chunks)
    ]
    return "\n\n---\n\n".join(parts)


def extract_sources(chunks: list[dict]) -> list[dict]:
    """
    Extrait les sources uniques des chunks (déduplication par source).

    Args:
        chunks: Sortie de ``retrieve()``.

    Returns:
        Liste de dicts ``{source, url, score}`` sans doublons.
    """
    seen:    set[str]   = set()
    sources: list[dict] = []

    for chunk in chunks:
        source = chunk["metadata"].get("source", "unknown")
        if source not in seen:
            seen.add(source)
            sources.append({
                "source": source,
                "url":    chunk["metadata"].get("url", ""),
                "score":  chunk["score"],
            })

    return sources
