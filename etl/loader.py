import os
import time
import json
import logging
from pathlib import Path
from github import Github
from github import RateLimitExceededException
from config.settings import settings

logger = logging.getLogger(__name__)


class OdooDocLoader:

    REPO_NAME = "odoo/documentation"
    BRANCH = "16.0"
    DOC_PATH = "content"
    CACHE_DIR = Path("data/raw")

    # Dossiers à exclure — contrats légaux, release notes, conf
    EXCLUDED_DIRS = {
        "legal",
        "releases",
        "contributing",
        "administration/odoo_accounts",
    }

    # Fichiers à exclure — contrats, CGU, accords partenaires
    EXCLUDED_FILENAME_PATTERNS = [
        "agreement",
        "enterprise_agreement",
        "partnership_agreement",
        "terms_of_service",
        "privacy_policy",
        "CHANGELOG",
    ]

    def __init__(self):
        self.github = Github(settings.github_token)
        self.repo = self.github.get_repo(self.REPO_NAME)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _is_excluded(self, path: str, filename: str) -> bool:
        """Retourne True si le fichier doit être exclu de l'index"""
        # Exclure les dossiers légaux/non-fonctionnels
        for excluded_dir in self.EXCLUDED_DIRS:
            if f"/{excluded_dir}/" in path or path.startswith(f"{self.DOC_PATH}/{excluded_dir}/"):
                return True

        # Exclure les fichiers par pattern de nom
        name_lower = filename.lower().replace(".rst", "")
        for pattern in self.EXCLUDED_FILENAME_PATTERNS:
            if pattern.lower() in name_lower:
                return True

        return False

    def get_all_rst_files(self) -> list[dict]:
        logger.info(f"Récupération de la liste des fichiers .rst...")
        rst_files = []
        self._walk_directory(self.DOC_PATH, rst_files)
        logger.info(f"{len(rst_files)} fichiers .rst trouvés (après filtrage)")
        return rst_files

    def _walk_directory(self, path: str, rst_files: list):
        try:
            contents = self.repo.get_contents(path, ref=self.BRANCH)
            for item in contents:
                if item.type == "dir":
                    self._walk_directory(item.path, rst_files)
                elif item.type == "file" and item.name.endswith(".rst"):
                    # Appliquer le filtre d'exclusion
                    if self._is_excluded(item.path, item.name):
                        logger.debug(f"Exclu (légal/non-fonctionnel): {item.path}")
                        continue
                    rst_files.append({
                        "path": item.path,
                        "name": item.name,
                        "download_url": item.download_url,
                        "sha": item.sha,
                    })
        except RateLimitExceededException:
            logger.warning("Rate limit GitHub, pause 60s...")
            time.sleep(60)
            self._walk_directory(path, rst_files)
        except Exception as e:
            logger.error(f"Erreur sur {path}: {e}")

    def _get_cache_path(self, file_path: str) -> Path:
        safe_path = file_path.replace("/", "_")
        return self.CACHE_DIR / safe_path

    def _is_cached(self, file_path: str) -> bool:
        return self._get_cache_path(file_path).exists()

    def _save_to_cache(self, file_path: str, content: str):
        cache_path = self._get_cache_path(file_path)
        cache_path.write_text(content, encoding="utf-8")

    def _load_from_cache(self, file_path: str) -> str:
        cache_path = self._get_cache_path(file_path)
        return cache_path.read_text(encoding="utf-8")

    def get_file_content(self, file_info: dict) -> str:
        if self._is_cached(file_info["path"]):
            return self._load_from_cache(file_info["path"])

        try:
            file = self.repo.get_contents(file_info["path"], ref=self.BRANCH)
            content = file.decoded_content.decode("utf-8")
            self._save_to_cache(file_info["path"], content)
            return content
        except Exception as e:
            logger.error(f"Erreur lecture {file_info['path']}: {e}")
            return ""

    def load_all(self) -> list[dict]:
        rst_files = self.get_all_rst_files()
        documents = []

        for i, file_info in enumerate(rst_files):
            cached = self._is_cached(file_info["path"])
            source = "cache" if cached else "GitHub"
            logger.info(f"[{i+1}/{len(rst_files)}] [{source}] {file_info['path']}")

            content = self.get_file_content(file_info)

            if content.strip():
                documents.append({
                    "content": content,
                    "metadata": {
                        "source": file_info["path"],
                        "filename": file_info["name"],
                        "branch": self.BRANCH,
                        "url": f"https://github.com/{self.REPO_NAME}/blob/{self.BRANCH}/{file_info['path']}",
                    }
                })

            if not cached and i % 30 == 0 and i > 0:
                time.sleep(2)

        logger.info(f"{len(documents)} documents chargés (légaux exclus)")
        return documents

    def get_cache_stats(self):
        cached_files = list(self.CACHE_DIR.glob("*.rst"))
        print(f"Fichiers en cache : {len(cached_files)}")
        total_size = sum(f.stat().st_size for f in cached_files)
        print(f"Taille totale : {total_size / 1024 / 1024:.1f} MB")
