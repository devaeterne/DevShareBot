"""Pure helpers for hashtag configuration and matching."""

import re


def normalize_tags(raw: str) -> list[str]:
    tags = [part.strip().lstrip("#") for part in raw.split(",")]
    tags = [tag for tag in tags if tag]
    if not 1 <= len(tags) <= 20:
        raise ValueError("1-20 hashtag girin (virgülle ayırın).")
    if any(len(tag) > 32 or not re.fullmatch(r"\w+", tag, re.UNICODE) for tag in tags):
        raise ValueError("Hashtag yalnızca harf, rakam ve alt çizgi içerebilir (en fazla 32 karakter).")
    return list(dict.fromkeys(tag.casefold() for tag in tags))


def compile_hashtags(raw: str) -> re.Pattern[str]:
    tags = normalize_tags(raw)
    return re.compile(
        r"(?<!\w)#(?:" + "|".join(re.escape(tag) for tag in tags) + r")(?!\w)",
        re.IGNORECASE,
    )


def eligible_content(text: str | None, caption: str | None, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(text or caption or ""))
