"""Telegram group-to-channel hashtag relay."""

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

from bot.filters import compile_hashtags, eligible_content

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("telegram_hashtag_relay")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def run() -> None:
    token = required_env("BOT_TOKEN")
    source_chat_id = int(required_env("SOURCE_CHAT_ID"))
    target_chat_id = int(required_env("TARGET_CHAT_ID"))
    hashtag_pattern = compile_hashtags(required_env("HASHTAGS"))
    if source_chat_id == target_chat_id:
        raise ValueError("SOURCE_CHAT_ID and TARGET_CHAT_ID must differ")

    bot = Bot(token=token)
    dp = Dispatcher()

    @dp.message()
    async def relay(message: Message) -> None:
        if message.chat.id != source_chat_id:
            return
        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return
        if not eligible_content(message.text, message.caption, hashtag_pattern):
            return
        # Telegram cannot reliably identify the real human behind sender_chat.
        if message.sender_chat is not None or message.from_user is None:
            logger.info("SKIP non-attributable message id=%s", message.message_id)
            return
        if message.from_user.is_bot:
            return

        try:
            member = await bot.get_chat_member(
                chat_id=source_chat_id,
                user_id=message.from_user.id,
            )
        except TelegramAPIError:
            logger.exception("SKIP role verification error message=%s", message.message_id)
            return

        if member.status not in {
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
        }:
            logger.info("SKIP non-admin user=%s", message.from_user.id)
            return

        try:
            await bot.copy_message(
                chat_id=target_chat_id,
                from_chat_id=source_chat_id,
                message_id=message.message_id,
            )
            logger.info("PUBLISHED message=%s", message.message_id)
        except TelegramAPIError:
            logger.exception("Publish error message=%s", message.message_id)

    try:
        me = await bot.get_me()
        logger.info("Polling started bot=@%s", me.username)
        await dp.start_polling(bot, allowed_updates=["message"])
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
