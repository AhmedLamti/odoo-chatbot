"""
shared/llm_factory.py

Fabrique centralisée de LLMs.
Tous les agents importent leur LLM depuis ici — jamais directement depuis
les packages langchain.

Ajouter un nouveau provider = modifier uniquement ce fichier.
"""
from enum import Enum

from langchain_anthropic import ChatAnthropic
from langchain_cerebras import ChatCerebras
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from config.settings import settings


class LLMProvider(str, Enum):
    ANTHROPIC_SONNET = "claude-3-5-sonnet-latest"
    # Groq — modèles
    GROQ_LLAMA33 = "groq_llama33"  # ✅ tool calling stable  — recommandé agent
    GROQ_QWEN3 = "groq_qwen3"  # ✅ meilleur raisonnement sur Groq
    GROQ_LLAMA4 = "groq_llama4"  # ⚠️  tool calling instable — éviter pour agent

    # Google
    GEMINI_FLASH = "gemini_flash"  # ✅ meilleur tool calling global
    GEMINI_FLASH_LITE = "gemini_flash_lite"  # ✅ plus rapide, légèrement moins capable

    # Cerebras — backup si rate limit Groq
    CEREBRAS_LLAMA33 = "cerebras_llama33"  # ✅ 1M tokens/jour gratuit
    FIREWORKS_KIMI = "fireworks_kimi"  # ✅ meilleur raisonnement disponible
    FIREWORKS_DEEPSEEK = "fireworks_deepseek"  # ✅ raisonnement avancé (thinking disabled)
    FIREWORKS_GPT_OSS = "fireworks_gpt_oss"  # ✅ rapide, bon tool calling


_FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

_FIREWORKS_MODELS = {
    LLMProvider.FIREWORKS_KIMI: "accounts/fireworks/models/kimi-k2p6",
    LLMProvider.FIREWORKS_DEEPSEEK: "accounts/fireworks/models/deepseek-v4-pro",
    LLMProvider.FIREWORKS_GPT_OSS: "accounts/fireworks/models/gpt-oss-120b",
}
# Provider par défaut pour les agents ReAct
DEFAULT_AGENT_PROVIDER = LLMProvider.GEMINI_FLASH


def get_llm(
        provider: LLMProvider = DEFAULT_AGENT_PROVIDER,
        temperature: float = 0,
):
    """
    Instancie et retourne un LLM selon le provider demandé.

    Args:
        provider:    LLMProvider.GEMINI_FLASH, GROQ_LLAMA33, etc.
        temperature: 0 = déterministe (recommandé pour les agents)

    Usage dans un agent :
        from shared.llm_factory import get_llm, LLMProvider

        llm = get_llm()                              # défaut : Gemini Flash
        llm = get_llm(LLMProvider.GROQ_LLAMA33)     # Groq fallback
        llm = get_llm(LLMProvider.CEREBRAS_LLAMA33)  # backup si rate limit
    """

    # ── Groq ──────────────────────────────────────────────────────────────────
    if provider == LLMProvider.GROQ_LLAMA33:
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=settings.groq_api_key,
            temperature=temperature,
        )

    if provider == LLMProvider.GROQ_QWEN3:
        return ChatGroq(
            model="qwen/qwen3-32b",
            api_key=settings.groq_api_key,
            temperature=temperature,
        )

    if provider == LLMProvider.GROQ_LLAMA4:
        return ChatGroq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            api_key=settings.groq_api_key,
            temperature=temperature,
        )

    # ── Google Gemini ─────────────────────────────────────────────────────────
    if provider == LLMProvider.GEMINI_FLASH:
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=settings.google_api_key,
            temperature=temperature,
        )

    if provider == LLMProvider.GEMINI_FLASH_LITE:
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=settings.google_api_key,
            temperature=temperature,
        )

    # ── Cerebras ──────────────────────────────────────────────────────────────
    if provider == LLMProvider.CEREBRAS_LLAMA33:
        return ChatCerebras(
            model="llama3.3-70b",
            api_key=settings.cerebras_api_key,
            temperature=temperature,
        )
    if provider in _FIREWORKS_MODELS:
        extra = {}
        # DeepSeek V4 Pro active le thinking par défaut — on le désactive
        # pour éviter les tokens de raisonnement verbeux inutiles
        if provider == LLMProvider.FIREWORKS_DEEPSEEK:
            extra = {"model_kwargs": {"extra_body": {"thinking": {"type": "disabled"}}}}

        return ChatOpenAI(
            model=_FIREWORKS_MODELS[provider],
            openai_api_key=settings.openai_api_key,
            openai_api_base=_FIREWORKS_BASE_URL,
            temperature=temperature,
            **extra,
        )
    if provider == LLMProvider.ANTHROPIC_SONNET:
        return ChatAnthropic(
            model_name="claude-3-5-sonnet-latest",
            temperature=0,
            anthropic_api_key=settings.anthropic_api_key,
        )

    raise ValueError(f"Provider inconnu : {provider}")
