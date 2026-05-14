"""
shared/llm_factory.py

Fabrique centralisée de LLMs.
Tous les agents importent leur LLM depuis ici — jamais directement depuis
langchain_groq / langchain_google_genai.

Ajouter un nouveau provider = modifier uniquement ce fichier.
"""
from enum import Enum

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from config.settings import settings


class LLMProvider(str, Enum):
    GROQ = "groq"
    GEMINI = "gemini"


def get_llm(provider: LLMProvider = LLMProvider.GROQ, temperature: float = 0):
    """
    Instancie et retourne un LLM selon le provider demandé.

    Args:
        provider:    LLMProvider.GROQ ou LLMProvider.GEMINI
        temperature: Température du modèle (0 = déterministe)

    Usage dans un agent :
        from shared.llm_factory import get_llm, LLMProvider
        llm = get_llm(LLMProvider.GROQ)
    """
    if provider == LLMProvider.GROQ:
        return ChatGroq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            api_key=settings.groq_api_key,
            temperature=temperature,
        )

    if provider == LLMProvider.GEMINI:
        return ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-lite",
            google_api_key=settings.google_api_key,
            temperature=temperature,
        )

    raise ValueError(f"Provider inconnu : {provider}")
