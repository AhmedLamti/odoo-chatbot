"""
Client Cerebras — Router + SQL
avec retry automatique (3 tentatives, backoff exponentiel)
"""

import logging
from cerebras.cloud.sdk import Cerebras
from config.settings import settings
from utils.retry import with_retry

logger = logging.getLogger(__name__)


@with_retry(max_attempts=3, delay=1.0, backoff=2.0)
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
