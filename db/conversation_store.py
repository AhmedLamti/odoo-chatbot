import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

HISTORY_DIR = Path("data/conversations")


class ConversationStore:
    """
    Gère l'historique des conversations par session
    Stockage local en JSON
    """

    def __init__(self):
        HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    def _get_path(self, session_id: str) -> Path:
        return HISTORY_DIR / f"{session_id}.json"

    def get_history(self, session_id: str) -> list[dict]:
        """Charge l'historique d'une session"""
        path = self._get_path(session_id)
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def add_message(self, session_id: str, role: str, content: str):
        """Ajoute un message à l'historique"""
        history = self.get_history(session_id)
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
        })
        with open(self._get_path(session_id), "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def get_last_n(self, session_id: str, n: int = 6) -> list[dict]:
        """Retourne les n derniers messages"""
        history = self.get_history(session_id)
        return history[-n:]

    def format_history(self, session_id: str, n: int = 6) -> str:
        """Formate l'historique pour injection dans le prompt"""
        messages = self.get_last_n(session_id, n)
        if not messages:
            return ""
        lines = ["Previous conversation:"]
        for msg in messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)

    def clear(self, session_id: str):
        """Supprime l'historique d'une session"""
        path = self._get_path(session_id)
        if path.exists():
            path.unlink()
        logger.info(f"Historique supprimé: {session_id}")

    def list_sessions(self) -> list[str]:
        """Liste toutes les sessions actives"""
        return [p.stem for p in HISTORY_DIR.glob("*.json")]
