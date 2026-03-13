"""
Client Cerebras — Router + SQL
"""
import logging
from cerebras.cloud.sdk import Cerebras
from config.settings import settings

logger = logging.getLogger(__name__)


def call_cerebras(
    prompt: str,
    system: str,
    max_tokens: int = 500,
    temperature: float = 0,
) -> str:
    client = Cerebras(api_key=settings.cerebras_api_key)
    response = client.chat.completions.create(
        model=settings.cerebras_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    message = response.choices[0].message
    content = message.content or getattr(message, "reasoning", None) or ""
    return content.strip()
