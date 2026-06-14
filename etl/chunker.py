# ── etl/chunker.py ────────────────────────────────────────────────────────────
# Chunking sémantique des fichiers RST de la documentation Odoo 16.
#
# Stratégie :
#   1. Nettoyage RST (suppression directives, balises, séparateurs)
#   2. Découpage par sections RST (titres) — frontières structurelles dures
#   3. Dans chaque section : SemanticChunker (LangChain) mesure la distance
#      cosine entre phrases consécutives et coupe quand le sujet change
#   4. Préfixage de chaque chunk avec son titre de section pour le contexte
#   5. Filtrage des chunks trop courts (bruit)
#
# Pourquoi section d'abord, sémantique ensuite ?
#   Les sections RST sont des frontières thématiques garanties par l'auteur.
#   Le SemanticChunker affine le découpage à l'intérieur de chaque section
#   sans jamais fusionner du contenu de sections différentes.
# ──────────────────────────────────────────────────────────────────────────────

import re
import logging

from langchain_experimental.text_splitter import SemanticChunker
from langchain_community.embeddings import OllamaEmbeddings

from config.settings import settings

logger = logging.getLogger(__name__)

# ── Constantes ─────────────────────────────────────────────────────────────────

# Nombre minimal de mots pour qu'un chunk soit conservé.
_MIN_WORDS = 30

# Seuil de breakpoint sémantique.
# "percentile" = coupe quand la distance entre deux phrases dépasse
# le Nth percentile des distances de ce document.
# Valeur recommandée : 85–95. Plus haute = chunks plus grands.
_BREAKPOINT_TYPE       = "percentile"
_BREAKPOINT_THRESHOLD  = 90


class SemanticRSTChunker:
    """
    Chunker sémantique pour les fichiers RST de la documentation Odoo.

    Combine :
    - Nettoyage RST structurel (regex)
    - Découpage par sections RST (frontières dures)
    - SemanticChunker LangChain (frontières sémantiques à l'intérieur)
    """

    def __init__(
        self,
        breakpoint_threshold_type: str = _BREAKPOINT_TYPE,
        breakpoint_threshold_amount: int = _BREAKPOINT_THRESHOLD,
        min_words: int = _MIN_WORDS,
    ):
        self.min_words = min_words

        # Modèle d'embedding partagé avec le retriever.
        # Pas de préfixe ici — SemanticChunker compare des phrases
        # entre elles (même espace vectoriel suffit).
        _embeddings = OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
        )

        self._splitter = SemanticChunker(
            embeddings=_embeddings,
            breakpoint_threshold_type=breakpoint_threshold_type,
            breakpoint_threshold_amount=breakpoint_threshold_amount,
        )

        logger.info(
            "[chunker] SemanticChunker initialisé — modèle=%s  breakpoint=%s@%s  min_words=%d",
            settings.ollama_embed_model,
            breakpoint_threshold_type,
            breakpoint_threshold_amount,
            min_words,
        )

    # ── Helpers RST ────────────────────────────────────────────────────────────

    def is_index_file(self, text: str) -> bool:
        """
        Retourne True si le fichier est un index/navigation RST.
        Ces fichiers ne contiennent pas de contenu exploitable.
        """
        toctree_count = text.count(".. toctree::")
        word_count    = len(text.split())
        return toctree_count > 0 and word_count < 300

    def clean_rst(self, text: str) -> str:
        """
        Supprime les éléments RST non-sémantiques :
        directives, options, références, séparateurs, espaces excessifs.
        """
        # Directives toctree complètes (multi-lignes)
        text = re.sub(r'\.\. toctree::.*?(?=\n\S|\Z)', '', text, flags=re.DOTALL)
        # Autres directives RST (.. note::, .. code-block::, etc.)
        text = re.sub(r'\.\. \w+::.*?\n', '', text)
        # Options RST (:nosearch:, :show-content:, etc.)
        text = re.sub(r'^:\w[\w-]*:.*$', '', text, flags=re.MULTILINE)
        # Références inline :role:`text` → text
        text = re.sub(r':\w+:`([^`]+)`', r'\1', text)
        # Liens `text`_ → text
        text = re.sub(r'`([^`]+)`_+', r'\1', text)
        # Séparateurs de section (===, ---, ~~~, etc.)
        text = re.sub(r'^[=\-~#\^*+]{3,}\s*$', '', text, flags=re.MULTILINE)
        # Lignes vides excessives
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def extract_title(self, raw_text: str) -> str:
        """
        Extrait le titre principal du fichier RST (avant nettoyage).
        Le titre est la ligne précédant un séparateur RST.
        """
        lines = raw_text.split('\n')
        for i, line in enumerate(lines):
            if i + 1 < len(lines) and re.match(r'^[=\-~#\^*+]{3,}$', lines[i + 1].strip()):
                return line.strip()
        return ""

    def split_by_sections(self, text: str) -> list[tuple[str, str]]:
        """
        Découpe le texte RST nettoyé en sections (titre, contenu).

        Les sections sont délimitées par les titres RST.
        Retourne ``[("", texte_complet)]`` si aucun titre trouvé.
        """
        pattern = re.compile(r'^(.+)\n([=\-~#\^*+]{3,})\s*$', re.MULTILINE)
        matches = list(pattern.finditer(text))

        if not matches:
            return [("", text)]

        sections = []
        for i, match in enumerate(matches):
            title   = match.group(1).strip()
            start   = match.end()
            end     = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                sections.append((title, content))

        return sections

    # ── Chunking sémantique ────────────────────────────────────────────────────

    def _semantic_split(self, text: str) -> list[str]:
        """
        Applique le SemanticChunker LangChain sur un bloc de texte.
        Retourne une liste de chunks textuels.
        """
        try:
            docs = self._splitter.create_documents([text])
            return [d.page_content for d in docs]
        except Exception as exc:
            # Fallback : retourner le texte entier comme un seul chunk
            logger.warning("[chunker] SemanticChunker échoué, fallback chunk entier : %s", exc)
            return [text]

    # ── Interface publique ─────────────────────────────────────────────────────

    def chunk_document(self, document: dict) -> list[dict]:
        """
        Traite un document RST et retourne ses chunks sémantiques.

        Args:
            document: Dict ``{content: str, metadata: dict}``.

        Returns:
            Liste de dicts ``{content, metadata}`` prêts pour l'embedder.
            Liste vide si le document est un index ou vide.
        """
        content  = document["content"]
        metadata = document["metadata"]

        # Ignorer les fichiers index/navigation
        if self.is_index_file(content):
            logger.debug("[chunker] Index ignoré : %s", metadata.get("filename"))
            return []

        # Titre principal (extrait avant nettoyage RST)
        main_title = self.extract_title(content)

        # Nettoyage RST
        clean_content = self.clean_rst(content)
        if not clean_content:
            return []

        # Découpage structurel par sections RST
        sections = self.split_by_sections(clean_content)

        chunks: list[dict] = []

        for section_title, section_content in sections:
            # Titre de contexte = titre principal + titre de section
            context_title = (
                f"{main_title} - {section_title}".strip(" -")
                if section_title
                else main_title
            )

            # Chunking sémantique à l'intérieur de la section
            semantic_chunks = self._semantic_split(section_content)

            for i, chunk_text in enumerate(semantic_chunks):
                # Préfixer avec le titre de section pour le contexte LLM
                content_with_title = (
                    f"{context_title}\n{chunk_text}".strip()
                    if context_title
                    else chunk_text.strip()
                )

                # Filtrer les chunks trop courts (bruit)
                if len(content_with_title.split()) < self.min_words:
                    continue

                chunks.append({
                    "content": content_with_title,
                    "metadata": {
                        **metadata,
                        "title":       context_title,
                        "chunk_index": i,
                    },
                })

        return chunks

    def chunk_documents(self, documents: list[dict]) -> list[dict]:
        """
        Traite une liste de documents.

        Args:
            documents: Sortie de ``OdooDocLoader.load_all()``.

        Returns:
            Liste complète de chunks prêts pour l'embedder.
        """
        all_chunks: list[dict] = []
        skipped = 0

        for doc in documents:
            chunks = self.chunk_document(doc)
            if not chunks:
                skipped += 1
            else:
                all_chunks.extend(chunks)
                logger.info(
                    "[chunker] %s → %d chunks",
                    doc["metadata"].get("filename", "?"),
                    len(chunks),
                )

        logger.info(
            "[chunker] Total : %d chunks | %d fichiers ignorés (index/vides)",
            len(all_chunks),
            skipped,
        )
        return all_chunks
