import logging
from functools import lru_cache

from langchain_core.messages import SystemMessage, HumanMessage

from agents.data_agent.model_catalogue.model_registry import MODEL_REGISTRY
from shared.llm_factory import get_llm

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════
# PROMPTS
# ══════════════════════════════════════════════════════

_TRANSLATION_PROMPT = """\
You are a business terminology translator.
Translate the following business query into English.
If it is already in English, return it unchanged.
Return ONLY the translated text — no explanation, no quotes.

Query: {query}
"""

_CLASSIFIER_SYSTEM = """\
You are an Odoo data model expert.
Your ONLY job is to select the single most appropriate Odoo technical model name
for the user's query, choosing strictly from the provided list.

Rules:
- Read the description of each model carefully before choosing.
- When two models are similar (e.g. sale.order vs sale.order.line), pick the one
  whose description best matches the intent of the query.
- Reply with ONLY the technical model name. No explanation. No punctuation.

Example reply: sale.order
"""

_CLASSIFIER_USER = """\
User query: "{query}"

Available models:
{model_list}

Reply with ONLY the technical model name.
"""


# ══════════════════════════════════════════════════════
# LLM (singleton)
# ══════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _get_llm():
    return get_llm(temperature=0)


# ══════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════

def _translate(query: str) -> str:
    """Translate any query to English for consistent classification."""
    prompt = _TRANSLATION_PROMPT.format(query=query)
    try:
        result = _get_llm().invoke(prompt)
        translated = result.content.strip()
        logger.debug("[resolver] translation: '%s' → '%s'", query, translated)
        return translated
    except Exception as exc:
        logger.warning("[resolver] translation failed, using original: %s", exc)
        return query


def _build_model_list() -> str:
    """Format the registry as a numbered list for the classifier prompt."""
    lines = []
    for model, meta in MODEL_REGISTRY.items():
        lines.append(f"- {model}: {meta['description']}")
    return "\n".join(lines)


def _classify(query_en: str) -> str:
    """Ask the LLM to pick the best model from the registry."""
    model_list = _build_model_list()
    user_message = _CLASSIFIER_USER.format(query=query_en, model_list=model_list)

    response = _get_llm().invoke([
        SystemMessage(content=_CLASSIFIER_SYSTEM),
        HumanMessage(content=user_message),
    ])
    return response.content.strip().strip('"').strip("'")


# ══════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════

def resolve_model(concept: str) -> str:
    """
    Resolve a natural-language concept (FR / AR / EN) to an Odoo technical model name.

    Pipeline:
        1. Translate the query to English.
        2. Ask the LLM to classify against the static MODEL_REGISTRY.
        3. Validate the result; fall back to the first registry key on invalid output.

    Args:
        concept: Natural-language question or keyword.

    Returns:
        Odoo technical model name (e.g. "sale.order").

    Raises:
        ValueError: If concept is empty.
    """
    concept = concept.strip()
    if not concept:
        raise ValueError("concept must not be empty")

    # Step 1 — translate
    concept_en = _translate(concept)

    # Step 2 — classify
    chosen = _classify(concept_en)

    # Step 3 — validate
    if chosen not in MODEL_REGISTRY:
        logger.warning(
            "[resolver] LLM returned unknown model '%s' for '%s' → fallback to first entry",
            chosen, concept_en,
        )
        chosen = next(iter(MODEL_REGISTRY))

    logger.info("[resolver] '%s' → EN:'%s' → %s", concept, concept_en, chosen)
    return chosen
