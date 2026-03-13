"""
Client Gemini — RAG
"""
import logging
import google.generativeai as genai
from config.settings import settings

logger = logging.getLogger(__name__)


def call_gemini(
    prompt: str,
    system: str,
    max_tokens: int = 1000,
    temperature: float = 0,
) -> str:
    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(
        model_name=settings.gemini_model,
        system_instruction=system,
        generation_config=genai.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )
    response = model.generate_content(prompt)
    return response.text.strip()
