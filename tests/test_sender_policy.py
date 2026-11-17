import unittest
from types import SimpleNamespace

from bot.sender_policy import is_anonymous_group_post


def message(chat_id, chat_type="supergroup", sender_id=None, sender_type="supergroup"):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type),
        sender_chat=None if sender_id is None else SimpleNamespace(id=sender_id, type=sender_type),
    )


class AnonymousSenderTests(unittest.TestCase):
    def test_same_group_accepted(self):
        self.assertTrue(is_anonymous_group_post(message(-100123, sender_id=-100123)))

    def test_linked_channel_rejected(self):
        self.assertFalse(is_anonymous_group_post(message(-100123, sender_id=-100456, sender_type="channel")))

    def test_no_sender_chat_rejected(self):
        self.assertFalse(is_anonymous_group_post(message(-100123)))

    def test_direct_channel_rejected(self):
        self.assertFalse(is_anonymous_group_post(message(-100123, chat_type="channel", sender_id=-100123, sender_type="channel")))

    def test_other_group_rejected(self):
        self.assertFalse(is_anonymous_group_post(message(-100123, sender_id=-100456)))


if __name__ == "__main__":
    unittest.main()
