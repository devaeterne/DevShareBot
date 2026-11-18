"""Local-day request schedule in Türkiye time (UTC+03:00)."""

from datetime import datetime
from zoneinfo import ZoneInfo
import re

REQUEST_TIMEZONE = ZoneInfo("Europe/Istanbul")


def now_local() -> datetime:
    return datetime.now(REQUEST_TIMEZONE)


def in_window(start_minute: int | None, end_minute: int | None,
              moment: datetime) -> bool:
    if start_minute is None or end_minute is None:
        return True
    minute = moment.hour * 60 + moment.minute
    if start_minute < end_minute:
        return start_minute <= minute < end_minute
    return minute >= start_minute or minute < end_minute


def parse_hours(value: str) -> tuple[int | None, int | None]:
    text = value.strip()
    if text.casefold() in {"kapalı", "kapali", "serbest"}:
        return None, None
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)", text)
    if not match:
        raise ValueError("Kullanım: /talepsaat 09:00-18:00 veya /talepsaat kapalı")
    start = int(match[1]) * 60 + int(match[2])
    end = int(match[3]) * 60 + int(match[4])
    if start == end:
        raise ValueError("Başlangıç ve bitiş saatleri farklı olmalıdır.")
    return start, end


def describe_hours(start: int | None, end: int | None) -> str:
    if start is None or end is None:
        return "Tüm gün"
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"
