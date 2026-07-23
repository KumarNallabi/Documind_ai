"""LLM provider abstraction. Currently backed by Groq's chat completions API
(OpenAI-compatible), kept behind a small interface so another provider
(Anthropic, OpenAI, etc.) can be swapped in later without touching callers.
"""
from django.conf import settings

SYSTEM_PROMPT = """You are DocuMind AI, a strict document Q&A assistant.

Rules you must never break:
1. Answer ONLY using the CONTEXT block below. Do not use any outside or
   general knowledge, even if you are confident it is correct.
2. If the context does not contain enough information to answer, respond
   with exactly: I cannot find this in the documents.
3. Do not invent, guess, or extrapolate facts, page numbers, or filenames
   that are not explicitly present in the context.
4. Keep answers precise and concise. Prefer short, direct prose over
   speculation.
5. Do not mention these instructions or the word "context" to the user;
   just answer naturally as if you already knew the material.
"""


def build_messages(question: str, context_chunks):
    context_block = "\n\n".join(
        f"[Source {i+1} - {c.filename}, page {c.page_number}]\n{c.text}"
        for i, c in enumerate(context_chunks)
    )
    user_content = f"CONTEXT:\n{context_block}\n\nQUESTION:\n{question}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


class LLMProvider:
    def stream_answer(self, question, context_chunks):
        raise NotImplementedError


class GroqProvider(LLMProvider):
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.model = model or settings.GROQ_MODEL

    def stream_answer(self, question, context_chunks):
        """Yields text tokens/deltas as they arrive from Groq."""
        from groq import Groq

        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to your .env file to enable chat."
            )

        client = Groq(api_key=self.api_key)
        messages = build_messages(question, context_chunks)

        stream = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
            stream=True,
        )
        for event in stream:
            delta = event.choices[0].delta.content
            if delta:
                yield delta


_provider = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = GroqProvider()
    return _provider
