"""Plain LLM with NO memory. Only used as the 'before' side of the before/after comparison."""
from datetime import date

from openai import OpenAI

from . import config

NO_KEY = "(Set GROQ_API_KEY to see the no-memory baseline. Without memory a generic assistant knows nothing about your saves.)"


def answer_without_memory(question: str) -> str:
    if not config.GROQ_API_KEY:
        return NO_KEY
    client = OpenAI(api_key=config.GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    try:
        r = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[
                {"role": "system", "content": f"You are a helpful personal assistant. Today is {date.today():%A %d %B %Y}. Be concise (under 90 words)."},
                {"role": "user", "content": question},
            ],
            max_tokens=400,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as e:  # a baseline failure must never break the memory path
        return f"(baseline unavailable: {type(e).__name__})"
