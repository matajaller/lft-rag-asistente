import os
from functools import lru_cache

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
client = Anthropic()
MODEL = os.getenv("MODEL", "claude-haiku-5-5")

# Deliberately generic: no example mappings, so the rewrite can't be tuned to the evaluation questions
PROMPT = """Rewrite a question about Mexican labour rights so it can be used to search the text of the
Ley Federal del Trabajo. Use the formal legal terms the law itself would use for the same concepts, in Spanish.
Keep every concept from the question. Do not answer it, and do not add article numbers unless the question names one.
Reply with the rewritten question only, in one sentence."""


@lru_cache(maxsize=1024)
def rewrite_query(question):
    """Everyday wording -> the law's own vocabulary. Falls back to the original question on any problem,
    so search always has something to work with."""
    try:
        resp = client.messages.create(
            model=MODEL, max_tokens=2048, system=PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if resp.stop_reason == "max_tokens" or not text:
            return question
        return text.splitlines()[0][:500]
    except Exception:
        return question
