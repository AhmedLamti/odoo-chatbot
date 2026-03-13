"""
Client Groq — Chart + Analysis
"""
import logging
from groq import Groq
from config.settings import settings

logger = logging.getLogger(__name__)


def call_groq(
    prompt: str,
    system: str,
    max_tokens: int = 500,
    temperature: float = 0,
) -> str:
    client = Groq(api_key=settings.groq_api_key)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()
