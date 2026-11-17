"""Telegram sender identity rules for relay authorization.

Anonymous administrator messages are sent on behalf of the source group.
Their actual human identity cannot be independently verified by bots.
"""

def is_anonymous_group_post(message) -> bool:
    sender_chat = getattr(message, "sender_chat", None)
    chat = getattr(message, "chat", None)
    if sender_chat is None or chat is None:
        return False
    return (
        getattr(chat, "type", None) in {"group", "supergroup"}
        and sender_chat.id == chat.id
        and getattr(sender_chat, "type", None) in {"group", "supergroup"}
    )
