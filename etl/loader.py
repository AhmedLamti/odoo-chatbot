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
    CACHE_DIR = Path("data/raw")  # sauvegarde locale

    def __init__(self):
        self.github = Github(settings.github_token)
        self.repo = self.github.get_repo(self.REPO_NAME)
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get_all_rst_files(self) -> list[dict]:
        logger.info(f"Récupération de la liste des fichiers .rst...")
        rst_files = []
        self._walk_directory(self.DOC_PATH, rst_files)
        logger.info(f"{len(rst_files)} fichiers .rst trouvés")
        return rst_files

    def _walk_directory(self, path: str, rst_files: list):
        try:
            contents = self.repo.get_contents(path, ref=self.BRANCH)
            for item in contents:
                if item.type == "dir":
                    self._walk_directory(item.path, rst_files)
                elif item.type == "file" and item.name.endswith(".rst"):
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
        """Retourne le chemin local du fichier caché"""
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
        """Récupère le contenu — depuis le cache ou GitHub"""
        # Si déjà en cache → lecture locale
        if self._is_cached(file_info["path"]):
            return self._load_from_cache(file_info["path"])

        # Sinon → téléchargement GitHub + mise en cache
        try:
            file = self.repo.get_contents(file_info["path"], ref=self.BRANCH)
            content = file.decoded_content.decode("utf-8")
            self._save_to_cache(file_info["path"], content)
            return content
        except Exception as e:
            logger.error(f"Erreur lecture {file_info['path']}: {e}")
            return ""

    def load_all(self) -> list[dict]:
        """Charge tous les fichiers (cache ou GitHub)"""
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

            # Pause seulement si on télécharge depuis GitHub
            if not cached and i % 30 == 0 and i > 0:
                time.sleep(2)

        logger.info(f"{len(documents)} documents chargés")
        return documents

    def get_cache_stats(self):
        """Stats sur le cache local"""
        cached_files = list(self.CACHE_DIR.glob("*.rst"))
        print(f"Fichiers en cache : {len(cached_files)}")
        total_size = sum(f.stat().st_size for f in cached_files)
        print(f"Taille totale : {total_size / 1024 / 1024:.1f} MB")
