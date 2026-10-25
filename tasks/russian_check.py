"""Russian text check scenario."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = (
    "Check the spelling, punctuation, and style of the following Russian text.\n"
    "Return the corrected text and a brief list of edits (no more than 5 items).\n\n"
    "Text:\n{text}\n"
)


async def check_russian_text(
    provider,
    text: str,
    file_hint: Optional[str] = None,
) -> str:
    if not text or not text.strip():
        return "[Empty text - nothing to check]"
    prompt = PROMPT_TEMPLATE.format(text=text)
    return await provider.ask(prompt, file_hint=file_hint)