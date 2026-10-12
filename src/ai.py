"""Optional AI summary using the Anthropic API.

The app works fully without this. If the `anthropic` package is installed and
ANTHROPIC_API_KEY is set (environment variable or .streamlit/secrets.toml), the
Overview tab offers a "Generate AI summary" button.
"""
from __future__ import annotations

import os

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")


def get_api_key(secrets=None) -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key and secrets is not None:
        try:
            key = secrets.get("ANTHROPIC_API_KEY")
        except Exception:  # secrets.toml missing
            key = None
    return key or None


def available(secrets=None) -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return get_api_key(secrets) is not None


def summarize(context: str, question: str, secrets=None, max_tokens: int = 700) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=get_api_key(secrets))
    msg = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=max_tokens,
        system=(
            "You are a performance-marketing analyst. Use only the numbers provided. "
            "Be concise: 4-6 bullet points, then one recommended next action."
        ),
        messages=[{"role": "user", "content": f"{question}\n\nDATA:\n{context}"}],
    )
    return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
