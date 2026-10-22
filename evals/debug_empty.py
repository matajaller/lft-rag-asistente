# One-off check: why did two questions come back with an empty answer?
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "rag"))

import answer as a                 # noqa: E402
from search import hybrid_search   # noqa: E402

QUESTIONS = [
    "¿Por qué causas me puede despedir el patrón de forma justificada?",
    "¿Qué causas me permiten dejar el trabajo sin perder mi indemnización?",
]

for q in QUESTIONS:
    results = hybrid_search(q, k=a.TOP_K)
    message = f"<extractos>\n{a.build_context(results)}\n</extractos>\n\n<pregunta>\n{q}\n</pregunta>"
    resp = a.client.messages.create(
        model=a.MODEL, max_tokens=1024, system=a.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": message}],
    )
    text = "".join(getattr(b, "text", "") for b in resp.content)
    print(q)
    print("   retrieved:  ", [r["article_id"] for r in results])
    print("   stop_reason:", resp.stop_reason)
    print("   blocks:     ", [b.type for b in resp.content])
    print("   text:       ", repr(text[:300]))
    print("   tokens:     ", resp.usage.input_tokens, "in /", resp.usage.output_tokens, "out\n")
