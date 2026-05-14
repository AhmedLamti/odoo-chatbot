import json
import logging


def get_logger(name: str) -> logging.Logger:
    """
    Retourne un logger configuré pour le module demandé.
    Utilisation : logger = get_logger(__name__)
    """
    return logging.getLogger(name)


def safe_json(obj: object) -> str:
    """Sérialise un objet en JSON UTF-8, sans lever d'exception sur les types non standards."""
    return json.dumps(obj, ensure_ascii=False, default=str)
