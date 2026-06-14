import logging
import uuid
from dataclasses import dataclass, asdict
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from config.settings import settings

logger = logging.getLogger(__name__)

MEMORY_COLLECTION = "agent_memories"
VECTOR_SIZE = 768  # nomic-embed-text
SEARCH_THRESHOLD = 0.70  # score minimum pour retenir un souvenir
DEDUP_THRESHOLD = 0.95  # score au-delà duquel on considère le souvenir déjà connu


@dataclass
class AgentMemory:
    """Un souvenir structuré d'une résolution réussie."""
    question_summary: str  # résumé court de la question (1 phrase)
    question_type: str  # ex: "count_records", "list_records", "aggregate"
    odoo_model: str  # ex: "res.partner", "sale.order"
    domain_used: str  # ex: "[('customer_rank', '>', 0)]"
    tools_sequence: list[str]  # ex: ["odoo_search_count"]
    final_answer_pattern: str  # ex: "Il y a {count} clients actifs."
    error_avoided: Optional[str] = None  # erreur commise et corrigée


class MemoryStore:
    """Gère la mémoire sémantique dans Qdrant."""

    def __init__(self):
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        self._init_collection()
        self._embed_model = None  # lazy init

    # ── Initialisation ────────────────────────────────────────────────────────

    def _get_embed_model(self):
        if self._embed_model is None:
            from llama_index.embeddings.ollama import OllamaEmbedding
            self._embed_model = OllamaEmbedding(
                model_name="nomic-embed-text",
                base_url=settings.ollama_base_url,
            )
        return self._embed_model

    def _init_collection(self):
        existing = [c.name for c in self.client.get_collections().collections]
        if MEMORY_COLLECTION not in existing:
            self.client.create_collection(
                collection_name=MEMORY_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"Collection '{MEMORY_COLLECTION}' créée")

    def _embed(self, text: str) -> list[float]:
        return self._get_embed_model().get_text_embedding(text)

    # ── Sauvegarde avec déduplication ─────────────────────────────────────────

    def save(self, memory: AgentMemory) -> bool:
        """
        Sauvegarde un souvenir dans Qdrant.

        Vérifie d'abord qu'un souvenir très similaire (score >= DEDUP_THRESHOLD)
        n'existe pas déjà pour le même modèle Odoo — si c'est le cas, on ne
        sauvegarde pas de doublon.

        Returns:
            True si sauvegardé, False si doublon détecté.
        """
        text_to_embed = f"{memory.question_summary} model:{memory.odoo_model}"
        vector = self._embed(text_to_embed)

        # Vérification doublon : chercher un souvenir très proche
        existing = self.client.query_points(
            collection_name=MEMORY_COLLECTION,
            query=vector,
            limit=1,
        ).points

        if existing and existing[0].score >= DEDUP_THRESHOLD:
            existing_summary = existing[0].payload.get("question_summary", "")[:60]
            logger.info(
                f"Souvenir doublon ignoré (score={existing[0].score:.3f} >= {DEDUP_THRESHOLD}): "
                f"'{memory.question_summary[:50]}' ≈ '{existing_summary}'"
            )
            return False

        self.client.upsert(
            collection_name=MEMORY_COLLECTION,
            points=[
                PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vector,
                    payload=asdict(memory),
                )
            ],
        )
        logger.info(f"Souvenir sauvegardé: '{memory.question_summary[:60]}'")
        return True

    # ── Recherche avec dédoublonnage des résultats ────────────────────────────

    def search(self, question: str, top_k: int = 3) -> list[AgentMemory]:
        """
        Cherche les souvenirs les plus proches d'une question.

        Filtre :
        - score >= SEARCH_THRESHOLD
        - dédoublonnage par (question_summary, odoo_model) pour éviter
          que des entrées identiques occupent plusieurs slots du top_k
        """
        vector = self._embed(question)

        # On demande plus de résultats pour absorber les doublons éventuels
        raw_results = self.client.query_points(
            collection_name=MEMORY_COLLECTION,
            query=vector,
            limit=top_k * 3,
        ).points

        memories: list[AgentMemory] = []
        seen: set[tuple] = set()  # (question_summary, odoo_model)

        for r in raw_results:
            if r.score < SEARCH_THRESHOLD:
                continue

            key = (
                r.payload.get("question_summary", ""),
                r.payload.get("odoo_model", ""),
            )
            if key in seen:
                logger.debug(f"Doublon de recherche ignoré: '{key[0][:40]}'")
                continue

            seen.add(key)
            memories.append(AgentMemory(**r.payload))

            if len(memories) >= top_k:
                break

        logger.info(f"Mémoire : {len(memories)} souvenir(s) pertinent(s) trouvé(s)")
        return memories

    # ── Formatage pour injection dans le prompt ───────────────────────────────

    def format_for_prompt(self, memories: list[AgentMemory]) -> str:
        """Formate les souvenirs pour injection dans le system prompt."""
        if not memories:
            return ""

        lines = ["\n--- EXPÉRIENCES PASSÉES (applique la même logique) ---"]
        for i, m in enumerate(memories, 1):
            lines.append(f"\nExemple {i} :")
            lines.append(f"  Question type : {m.question_summary}")
            lines.append(f"  Modèle Odoo   : {m.odoo_model}")
            lines.append(f"  Domain utilisé: {m.domain_used}")
            lines.append(f"  Outils appelés: {' → '.join(m.tools_sequence)}")
            if m.error_avoided:
                lines.append(f"  ⚠️  Erreur à éviter: {m.error_avoided}")
        lines.append("---\n")

        return "\n".join(lines)

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def count(self) -> int:
        """Retourne le nombre de souvenirs stockés."""
        return self.client.get_collection(MEMORY_COLLECTION).points_count

    def clear(self) -> None:
        """Supprime tous les souvenirs (utile pour les tests)."""
        self.client.delete_collection(MEMORY_COLLECTION)
        self._init_collection()
        logger.warning("Collection agent_memories réinitialisée")
