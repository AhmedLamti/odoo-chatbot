# ── etl/loader.py ─────────────────────────────────────────────────────────────
# Chargement des fichiers RST de la documentation Odoo 16.
#
# Deux modes :
#   - cache-only (défaut) : lit uniquement depuis data/raw/ — pas de réseau
#   - github              : télécharge depuis GitHub et met en cache
#
# Le mode cache-only est utilisé automatiquement si GitHub n'est pas
# disponible (token expiré, pas de réseau) et que le cache local existe.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import time
import logging
from pathlib import Path

from config.settings import settings

logger = logging.getLogger(__name__)


class OdooDocLoader:

    REPO_NAME = "odoo/documentation"
    BRANCH    = "16.0"
    DOC_PATH  = "content"
    CACHE_DIR = Path("data/raw")

    EXCLUDED_DIRS = {
        "legal",
        "releases",
        "contributing",
        "administration/odoo_accounts",
    }

    EXCLUDED_FILENAME_PATTERNS = [
        "agreement",
        "enterprise_agreement",
        "partnership_agreement",
        "terms_of_service",
        "privacy_policy",
        "CHANGELOG",
    ]

    def __init__(self) -> None:
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._github_available = False
        self._repo = None
        self._try_init_github()

    # ── Initialisation GitHub (optionnelle) ───────────────────────────────────

    def _try_init_github(self) -> None:
        """
        Tente d'initialiser le client GitHub.
        En cas d'échec, passe silencieusement en mode cache-only.
        """
        try:
            from github import Github  # noqa: F401
            github_token = getattr(settings, "github_token", None)
            if not github_token:
                raise ValueError("github_token absent dans settings")
            client     = Github(github_token)
            self._repo = client.get_repo(self.REPO_NAME)
            _          = self._repo.name  # valide le token
            self._github_available = True
            logger.info("[loader] Mode GitHub activé")
        except Exception as exc:
            logger.warning("[loader] GitHub indisponible (%s) — mode cache-only", exc)

    # ── Filtrage ───────────────────────────────────────────────────────────────

    def _is_excluded(self, path: str, filename: str) -> bool:
        """Retourne True si le fichier doit être exclu de l'index."""
        for excluded_dir in self.EXCLUDED_DIRS:
            if f"/{excluded_dir}/" in path or path.startswith(
                f"{self.DOC_PATH}/{excluded_dir}/"
            ):
                return True
        name_lower = filename.lower().replace(".rst", "")
        return any(p.lower() in name_lower for p in self.EXCLUDED_FILENAME_PATTERNS)

    # ── Cache ──────────────────────────────────────────────────────────────────

    def _cache_path(self, file_path: str) -> Path:
        return self.CACHE_DIR / file_path.replace("/", "_")

    def _is_cached(self, file_path: str) -> bool:
        return self._cache_path(file_path).exists()

    def _read_cache(self, file_path: str) -> str:
        return self._cache_path(file_path).read_text(encoding="utf-8")

    def _write_cache(self, file_path: str, content: str) -> None:
        self._cache_path(file_path).write_text(content, encoding="utf-8")

    # ── Chargement depuis le cache local ──────────────────────────────────────

    def _load_from_cache_dir(self) -> list[dict]:
        """
        Reconstruit la liste de documents depuis data/raw/.

        Note : le nom de fichier cache (ex: content_applications_sales_foo.rst)
        est utilisé directement comme identifiant source — la reconstruction
        exacte du chemin GitHub est impossible sans métadonnées supplémentaires
        (les underscores sont ambigus).
        """
        documents = []
        rst_files = sorted(self.CACHE_DIR.glob("*.rst"))
        logger.info("[loader] %d fichiers RST trouvés dans le cache", len(rst_files))

        for cache_file in rst_files:
            filename = cache_file.name

            if self._is_excluded(filename, filename):
                logger.debug("[loader] Exclu : %s", filename)
                continue

            content = cache_file.read_text(encoding="utf-8").strip()
            if not content:
                continue

            documents.append({
                "content":  content,
                "metadata": {
                    "source":   filename,
                    "filename": filename,
                    "branch":   self.BRANCH,
                    "url": (
                        f"https://github.com/{self.REPO_NAME}/blob/"
                        f"{self.BRANCH}/{filename}"
                    ),
                },
            })

        logger.info("[loader] %d documents chargés depuis le cache", len(documents))
        return documents

    # ── Chargement depuis GitHub ───────────────────────────────────────────────

    def _walk_github(self, path: str, rst_files: list[dict]) -> None:
        """Parcourt récursivement le dépôt GitHub et collecte les fichiers RST."""
        from github import RateLimitExceededException
        try:
            contents = self._repo.get_contents(path, ref=self.BRANCH)
            for item in contents:
                if item.type == "dir":
                    self._walk_github(item.path, rst_files)
                elif item.type == "file" and item.name.endswith(".rst"):
                    if not self._is_excluded(item.path, item.name):
                        rst_files.append({"path": item.path, "name": item.name})
        except RateLimitExceededException:
            logger.warning("[loader] Rate limit GitHub — pause 60s")
            time.sleep(60)
            self._walk_github(path, rst_files)
        except Exception as exc:
            logger.error("[loader] Erreur GitHub sur %s : %s", path, exc)

    def _load_from_github(self) -> list[dict]:
        """Télécharge les fichiers RST depuis GitHub avec mise en cache locale."""
        rst_files: list[dict] = []
        self._walk_github(self.DOC_PATH, rst_files)
        logger.info("[loader] %d fichiers .rst trouvés sur GitHub", len(rst_files))

        documents = []
        for i, file_info in enumerate(rst_files):
            if self._is_cached(file_info["path"]):
                content = self._read_cache(file_info["path"])
                source  = "cache"
            else:
                try:
                    gh_file = self._repo.get_contents(file_info["path"], ref=self.BRANCH)
                    content = gh_file.decoded_content.decode("utf-8")
                    self._write_cache(file_info["path"], content)
                    source = "GitHub"
                    if i % 30 == 0 and i > 0:
                        time.sleep(2)  # politesse envers l'API GitHub
                except Exception as exc:
                    logger.error("[loader] Erreur lecture %s : %s", file_info["path"], exc)
                    continue

            logger.info(
                "[loader] [%d/%d] [%s] %s",
                i + 1, len(rst_files), source, file_info["path"],
            )

            if content.strip():
                documents.append({
                    "content":  content,
                    "metadata": {
                        "source":   file_info["path"],
                        "filename": file_info["name"],
                        "branch":   self.BRANCH,
                        "url": (
                            f"https://github.com/{self.REPO_NAME}/blob/"
                            f"{self.BRANCH}/{file_info['path']}"
                        ),
                    },
                })

        logger.info("[loader] %d documents chargés depuis GitHub", len(documents))
        return documents

    # ── Interface publique ─────────────────────────────────────────────────────

    def load_all(self) -> list[dict]:
        """
        Charge tous les fichiers RST.

        Priorité :
          1. GitHub  — si token valide et réseau disponible
          2. Cache   — sinon, lecture directe depuis data/raw/

        Returns:
            Liste de dicts ``{content, metadata}`` prêts pour le chunker.
        """
        if self._github_available:
            return self._load_from_github()
        return self._load_from_cache_dir()

    def get_cache_stats(self) -> None:
        """Affiche des statistiques sur le cache local."""
        cached = list(self.CACHE_DIR.glob("*.rst"))
        total  = sum(f.stat().st_size for f in cached)
        print(f"Fichiers en cache : {len(cached)}")
        print(f"Taille totale     : {total / 1024 / 1024:.1f} MB")
