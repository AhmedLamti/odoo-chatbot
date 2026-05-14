import logging

from llama_index.embeddings.ollama import OllamaEmbedding

from config.settings import settings
from db.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)

embed_model = OllamaEmbedding(
    model_name=settings.ollama_embed_model,
    base_url=settings.ollama_base_url,
)

vector_store = VectorStoreManager()

MIN_SCORE = 0.30


def retrieve(query: str, top_k: int = 8) -> list[dict]:
    """
    Recherche les chunks pertinents dans Qdrant.
    Retourne une liste de chunks avec content, metadata et score.
    """
    try:
        query_embedding = embed_model.get_text_embedding(query)
        results = vector_store.search(
            query_vector=query_embedding,
            top_k=top_k,
        )
        filtered = [r for r in results if r.get("score", 0) >= MIN_SCORE]
        logger.info(f"Retriever: {len(filtered)}/{len(results)} chunks au dessus du seuil")
        return filtered
    except Exception as e:
        logger.error(f"Erreur retriever: {e}")
        return []


def format_context(chunks: list[dict]) -> str:
    """
    Formate les chunks en contexte pour le LLM.
    """
    if not chunks:
        return "Aucun contexte trouvé."
    parts = []
    for i, chunk in enumerate(chunks):
        source = chunk["metadata"].get("source", "unknown")
        score = chunk["score"]
        content = chunk["content"]
        parts.append(f"[Extrait {i + 1} — {source} (score: {score:.2f})]\n{content}")
    return "\n\n---\n\n".join(parts)


def extract_sources(chunks: list[dict]) -> list[dict]:
    """
    Extrait les sources uniques des chunks.
    """
    sources = []
    seen = set()
    for chunk in chunks:
        source = chunk["metadata"].get("source", "unknown")
        if source not in seen:
            seen.add(source)
            sources.append({
                "source": source,
                "url": chunk["metadata"].get("url", ""),
                "score": chunk["score"],
            })
    return sources
