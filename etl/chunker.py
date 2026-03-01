import re
import logging

logger = logging.getLogger(__name__)


class RSTChunker:

    def __init__(self, chunk_size: int = 150, chunk_overlap: int = 30, min_chunk_size: int = 40):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size  # ignorer les chunks trop petits

    def is_index_file(self, text: str) -> bool:
        """Détecte si c'est un fichier index/navigation"""
        toctree_count = text.count(".. toctree::")
        directive_count = len(re.findall(r'\.\. \w+::', text))
        word_count = len(text.split())
        # Fichier index = beaucoup de directives, peu de texte
        return toctree_count > 0 and word_count < 300

    def clean_rst(self, text: str) -> str:
        """Nettoie les balises RST"""
        # Supprimer les directives toctree complètes
        text = re.sub(r'\.\. toctree::.*?(?=\n\S|\Z)', '', text, flags=re.DOTALL)
        # Supprimer les autres directives
        text = re.sub(r'\.\. \w+::.*?\n', '', text)
        # Supprimer les options RST (:nosearch:, :show-content:...)
        text = re.sub(r'^:\w[\w-]*:.*$', '', text, flags=re.MULTILINE)
        # Supprimer les références RST :role:`text`
        text = re.sub(r':\w+:`([^`]+)`', r'\1', text)
        # Supprimer les liens `text`_
        text = re.sub(r'`([^`]+)`_+', r'\1', text)
        # Supprimer les séparateurs (===, ---, ~~~)
        text = re.sub(r'^[=\-~#\^*+]{3,}\s*$', '', text, flags=re.MULTILINE)
        # Nettoyer les espaces multiples
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def extract_title(self, text: str) -> str:
        """Extrait le titre principal du fichier RST"""
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if i + 1 < len(lines) and re.match(r'^[=\-~#\^*+]{3,}$', lines[i + 1].strip()):
                return line.strip()
        return ""

    def split_by_sections(self, text: str) -> list[tuple[str, str]]:
        """
        Découpe par sections RST avec leur titre
        Retourne une liste de (titre, contenu)
        """
        # Patterns de titres RST par niveau
        pattern = re.compile(
            r'^(.+)\n([=\-~#\^*+]{3,})\s*$',
            re.MULTILINE
        )

        matches = list(pattern.finditer(text))

        if not matches:
            return [("", text)]

        sections = []
        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if content:
                sections.append((title, content))

        return sections

    def chunk_text(self, text: str, title: str = "") -> list[str]:
        """Découpe un texte en chunks avec overlap"""
        words = text.split()

        if len(words) <= self.chunk_size:
            return [f"{title}\n{text}".strip() if title else text]

        chunks = []
        start = 0
        while start < len(words):
            end = start + self.chunk_size
            chunk_words = words[start:end]
            chunk = " ".join(chunk_words)
            # Préfixer avec le titre pour contexte
            if title:
                chunk = f"{title}\n{chunk}"
            chunks.append(chunk)
            start += self.chunk_size - self.chunk_overlap

        return chunks

    def chunk_document(self, document: dict) -> list[dict]:
        """Traite un document et retourne ses chunks"""
        content = document["content"]
        metadata = document["metadata"]

        # Ignorer les fichiers index
        if self.is_index_file(content):
            logger.debug(f"Fichier index ignoré: {metadata['filename']}")
            return []

        # Extraire le titre principal
        main_title = self.extract_title(content)

        # Nettoyage
        clean_content = self.clean_rst(content)

        if not clean_content:
            return []

        # Découpage par sections
        sections = self.split_by_sections(clean_content)

        chunks = []
        for section_title, section_content in sections:
            # Titre de contexte = titre principal + titre de section
            context_title = f"{main_title} - {section_title}".strip(" -") if section_title else main_title

            sub_chunks = self.chunk_text(section_content, context_title)

            for i, chunk in enumerate(sub_chunks):
                words = chunk.split()
                # Ignorer les chunks trop petits
                if len(words) < self.min_chunk_size:
                    continue

                chunks.append({
                    "content": chunk,
                    "metadata": {
                        **metadata,
                        "title": context_title,
                        "chunk_index": i,
                    }
                })

        return chunks

    def chunk_documents(self, documents: list[dict]) -> list[dict]:
        """Traite une liste de documents"""
        all_chunks = []
        skipped = 0

        for doc in documents:
            chunks = self.chunk_document(doc)
            if not chunks:
                skipped += 1
            else:
                all_chunks.extend(chunks)
                logger.info(f"{doc['metadata']['filename']} → {len(chunks)} chunks")

        logger.info(f"Total chunks: {len(all_chunks)} | Fichiers ignorés (index): {skipped}")
        return all_chunks
