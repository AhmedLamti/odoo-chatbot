import json

from langchain_core.tools import tool


@tool
def request_confirmation(
    action_type: str,
    action_summary: str,
    tool_name: str,
    tool_args: str,
) -> str:
    """
    Demande à l'utilisateur de confirmer une opération avant son exécution.

    tool_name = nom exact du tool à exécuter après confirmation
    tool_args = arguments JSON string du tool à exécuter après confirmation
    """
    try:
        parsed_args = json.loads(tool_args)
    except Exception:
        parsed_args = tool_args

    payload = {
        "status": "WAITING_CONFIRMATION",
        "action_type": action_type,
        "summary": action_summary,
        "pending_action": {
            "tool_name": tool_name,
            "tool_args": parsed_args,
        },
        "message": (
            f"⚠️ Confirmation requise\n\n"
            f"{action_summary}\n\n"
            "Cliquez sur **Confirmer** pour valider ou **Annuler** pour abandonner."
        ),
        "instruction": "Retourne le champ 'message' à l'utilisateur. Stop. N'appelle aucun autre outil.",
    }

    return json.dumps(payload, ensure_ascii=False)
