"""Pure matching logic for user-created requests."""

import re

REQUEST_PREFIX = re.compile(r"^\s*#talep(?=\s|$)", re.IGNORECASE)


def parse_request(text: str | None) -> tuple[bool, str]:
    """Return (is_request, payload). Only #Talep at message start triggers."""
    if text is None:
        return False, ""
    match = REQUEST_PREFIX.match(text)
    if match is None:
        return False, ""
    return True, text[match.end():].strip()
