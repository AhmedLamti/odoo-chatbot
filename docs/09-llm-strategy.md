# 09 — LLM Strategy (Multi-Provider Factory)

A defining characteristic of this project is that it is **not tied to one LLM vendor**. Every agent obtains its model from a single factory, and the *right model is chosen per task* (latency vs. reasoning vs. cost).

Code: [shared/llm_factory.py](../shared/llm_factory.py).

## 9.1 The factory pattern

```python
from shared.llm_factory import get_llm, LLMProvider

llm = get_llm()                              # default: Gemini Flash
llm = get_llm(LLMProvider.GROQ_LLAMA33)      # explicit choice
llm = get_llm(LLMProvider.FIREWORKS_DEEPSEEK, temperature=0)
```

`get_llm(provider, temperature=0)` returns a LangChain `BaseChatModel`. **No agent imports a vendor SDK directly** — they all go through this one function. Adding a provider = editing only this file.

> **Design pattern:** this is the classic **Factory / Strategy** pattern. The `LLMProvider` enum is the strategy key; `get_llm` is the factory that instantiates the concrete client. Benefit: provider choice becomes a one-line change and can even be driven per-request (the API accepts an `llm_provider` field).

## 9.2 Supported providers

| Enum | Provider / SDK | Concrete model | Typical use |
|------|----------------|----------------|-------------|
| `GROQ_LLAMA33` | Groq (`ChatGroq`) | `llama-3.3-70b-versatile` | Router, chat, action agent, memory extraction — fast tool-calling |
| `GROQ_QWEN3` | Groq | `qwen/qwen3-32b` | RAG generation + relevance judging |
| `GROQ_LLAMA4` | Groq | `llama-4-scout-17b-16e-instruct` | alt fast model |
| `GEMINI_FLASH` | Google (`ChatGoogleGenerativeAI`) | `gemini-2.5-flash` | **Default** ReAct agent model — strong tool calling |
| `GEMINI_FLASH_LITE` | Google | `gemini-2.5-flash-lite` | Cheap/fast helper calls: `select_models`, `format_response` |
| `CEREBRAS_LLAMA33` | Cerebras (`ChatCerebras`) | `llama3.3-70b` | Backup when Groq is rate-limited (1M free tokens/day) |
| `FIREWORKS_KIMI` | Fireworks via `ChatOpenAI` | `kimi-k2p6` | Reasoning fallback |
| `FIREWORKS_DEEPSEEK` | Fireworks via `ChatOpenAI` | `deepseek-v4-pro` (thinking disabled) | **Query planning** (`plan_query`) |
| `FIREWORKS_GPT_OSS` | Fireworks via `ChatOpenAI` | `gpt-oss-120b` | fast reasoning + tool calling |
| `ANTHROPIC_SONNET` | Anthropic (`ChatAnthropic`) | `claude-haiku-4-5` *(see note)* | Anthropic Claude option |

`DEFAULT_AGENT_PROVIDER = LLMProvider.GEMINI_FLASH`. Temperature defaults to **0** for deterministic, repeatable agent behavior.

> **Implementation notes / honest details:**
> - **Fireworks** models are reached through the **OpenAI-compatible** `ChatOpenAI` client pointed at `https://api.fireworks.ai/inference/v1` — a neat way to use any OpenAI-API-compatible endpoint without a dedicated SDK. DeepSeek's verbose "thinking" tokens are explicitly disabled via `extra_body`.
> - **Anthropic mismatch to flag:** the enum is named `ANTHROPIC_SONNET = "claude-3-5-sonnet-latest"` but the factory actually instantiates `model_name="claude-haiku-4-5-20251001"`. The enum *value* is also just a label and does not drive the model id. This is a known inconsistency worth fixing (align the enum name/value with the model actually built).

## 9.3 Which model does which job, and why

| Task | Provider chosen | Why |
|------|-----------------|-----|
| **Routing** (orchestrator) | `GROQ_LLAMA33` | The decision is one token; needs to be **fast and cheap**, not deep. Groq's inference is extremely low-latency. |
| **RAG generate + evaluate** | `GROQ_QWEN3` | Grounded summarization + a crisp binary judgment; Qwen3 is a capable instruction model and Groq keeps the two extra calls snappy. |
| **Default ReAct agents** | `GEMINI_FLASH` | Reliable **multi-step tool calling** with structured arguments — the main requirement for the data/action agents. |
| **Light helper calls** (`select_models`, `format_response`) | `GEMINI_FLASH_LITE` | Simple transforms run **many times**; the lite tier minimizes cost/latency. |
| **Query planning** (`plan_query`) | `FIREWORKS_DEEPSEEK` @ T=0 | Decomposing multi-model questions and obeying RPC constraints is a **reasoning** task; a reasoning model at temperature 0 yields stable JSON plans. |
| **Memory extraction** | Groq | Quick structured-JSON extraction from a trace. |
| **Backups** | `CEREBRAS_LLAMA33`, `FIREWORKS_KIMI` | Free/large quotas to ride out rate limits on the primary providers. |

## 9.4 Why multi-provider at all (the strategic argument)

- **Right tool for the task.** Latency-critical (routing/chat) vs. reasoning-critical (planning) vs. tool-calling-critical (agents) vs. cost-critical (helpers) have genuinely different best fits. One model can't be optimal at all four.
- **Resilience to rate limits / outages.** Free tiers (Groq, Gemini, Cerebras) have aggressive limits; the factory + backups let the system fail over instead of failing.
- **Cost control.** Cheap models for the high-frequency, low-difficulty calls; expensive reasoning models only where they earn their keep.
- **No vendor lock-in.** The abstraction means a future model (including newer Claude models) is a one-line addition. For new LLM features, defaulting to the latest, most capable Claude models is the recommended path; the `ChatAnthropic` integration is already wired in.
- **Per-request override.** The API's `llm_provider` field lets a caller pick a model per conversation without code changes.

## 9.5 Standalone client wrappers

Besides the LangChain factory, there are thin **direct** SDK wrappers used in a few non-LangChain spots — [tools/groq_client.py](../tools/groq_client.py) (`call_groq`), [tools/cerebras_client.py](../tools/cerebras_client.py) (`call_cerebras`), [tools/gemini_client.py](../tools/gemini_client.py) (`call_gemini`). The first two are wrapped in `@with_retry`. These are used where a single, prompt-in/text-out call is simpler than a full LangChain chat model (e.g. memory extraction, legacy schema selection).
