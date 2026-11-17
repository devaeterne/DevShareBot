"""Pure helpers for safely deciding whether a message is eligible."""

import re


def compile_hashtags(raw: str) -> re.Pattern[str]:
    """Build a case-insensitive hashtag expression from comma-separated names."""
    tags = [part.strip().lstrip("#") for part in raw.split(",")]
    tags = [tag for tag in tags if tag]
    if not tags:
        raise ValueError("HASHTAGS must contain at least one tag")
    if any(not re.fullmatch(r"\w+", tag, flags=re.UNICODE) for tag in tags):
        raise ValueError("HASHTAGS may only contain letters, numbers, and underscores")
    return re.compile(
        r"(?<!\w)#(?:" + "|".join(re.escape(tag) for tag in tags) + r")(?!\w)",
        re.IGNORECASE,
    )


def eligible_content(text: str | None, caption: str | None, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(text or caption or ""))
