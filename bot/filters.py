"""Pure helpers for hashtag configuration and matching."""

import re
import unicodedata


def normalize_tags(raw: str) -> list[str]:
    # Python casefold() expands Turkish capital İ into i + COMBINING DOT ABOVE.
    # Keep the regex pattern in composed form so re.IGNORECASE can match both
    # #ANALİZ and #analiz. Also repair tags persisted by older bot versions.
    tags = [
        unicodedata.normalize("NFC", part.strip().lstrip("#").casefold().replace("\u0307", ""))
        for part in raw.split(",")
    ]
    tags = [tag for tag in tags if tag]
    if not 1 <= len(tags) <= 20:
        raise ValueError("1-20 hashtag girin (virgülle ayırın).")
    if any(len(tag) > 32 or not re.fullmatch(r"\w+", tag, re.UNICODE) for tag in tags):
        raise ValueError("Hashtag yalnızca harf, rakam ve alt çizgi içerebilir (en fazla 32 karakter).")
    return list(dict.fromkeys(tags))


def compile_hashtags(raw: str) -> re.Pattern[str]:
    tags = normalize_tags(raw)
    return re.compile(
        r"(?<!\w)#(?:" + "|".join(re.escape(tag) for tag in tags) + r")(?!\w)",
        re.IGNORECASE,
    )


def eligible_content(text: str | None, caption: str | None, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(text or caption or ""))
