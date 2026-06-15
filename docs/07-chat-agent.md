# 07 — Chat Agent (Small-talk & Fallback)

The chat agent is the simplest of the four. It handles everything that is **not** a documentation question, a data question, or an action — greetings, identity questions ("who are you?"), thanks, and off-topic chatter. It is also the **fallback route** when the orchestrator is uncertain or errors.

Code: [agents/chat_agent/node.py](../agents/chat_agent/node.py), [prompts.py](../agents/chat_agent/prompts.py).

## 7.1 Behavior

```python
def chat_node(state):
    response = _llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": state["question"]},
    ])
    return {"answer": response.content.strip(),
            "metadata": {"handled_by": "chat_agent"}}
```

- **No tools, no loop, no state changes** — a single LLM call.
- Default LLM: `GROQ_LLAMA33` (fast, cheap; conversation needs no reasoning depth).
- The system prompt makes it polite, professional, concise, and **honest about its specialty**: it can chat generally but states that its real strengths are Odoo data and actions. It replies in the language of the incoming message.

## 7.2 Why a dedicated agent for this

- **Keeps the specialists clean.** Without a catch-all, off-topic or social messages would be forced into RAG/data/action, producing awkward "not found" or failed tool calls. A dedicated conversational lane handles them gracefully.
- **It's the safe fallback.** The orchestrator degrades to `chat` on any classification error (see [03-orchestrator-and-graph.md](03-orchestrator-and-graph.md)). The worst case for an unclear message is therefore a harmless, friendly reply — never a wrong data answer or an unintended write.
- **Sets expectations.** By reminding the user what it's good at, it gently steers the conversation back toward the platform's value.
