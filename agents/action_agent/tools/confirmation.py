import json

from langchain_core.tools import tool


@tool
def request_confirmation(action_type: str, action_summary: str) -> str:
    """
    Demande à l'utilisateur de confirmer une opération avant son exécution.

    Appelle cet outil AVANT create_record, update_record, delete_record,
    execute_action ou send_email.

    Après avoir appelé cet outil, tu DOIS immédiatement retourner le champ
    'message' à l'utilisateur et attendre sa réponse. Ne pas appeler d'autres outils.
    """
    payload = {
        "status": "WAITING_CONFIRMATION",
        "action_type": action_type,
        "summary": action_summary,
        "message": (
            f"⚠️ Confirmation requise\n\n"
            f"{action_summary}\n\n"
            "Répondez **CONFIRMER** pour valider ou **ANNULER** pour abandonner."
        ),
        "instruction": "Retourne le champ 'message' à l'utilisateur. Stop. N'appelle aucun autre outil."
    }
    return json.dumps(payload, ensure_ascii=False)
