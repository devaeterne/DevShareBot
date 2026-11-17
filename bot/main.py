"""Multi-tenant Telegram hashtag relay with in-chat setup."""

import asyncio
import logging
import os
import secrets
from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    KeyboardButton,
    KeyboardButtonRequestChat,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot.filters import compile_hashtags, eligible_content, normalize_tags
from bot.storage import RouteStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("telegram_hashtag_relay")
ADMIN_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}


@dataclass
class Setup:
    stage: str
    request_id: int
    source_id: int | None = None
    target_id: int | None = None


def picker(request_id: int, channel: bool) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="📣 Kanal seç" if channel else "👥 Grup seç",
                request_chat=KeyboardButtonRequestChat(
                    request_id=request_id,
                    chat_is_channel=channel,
                    bot_is_member=True,
                ),
            )
        ]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


async def admin_of(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
        return member.status in ADMIN_STATUSES
    except TelegramAPIError:
        logger.warning("Could not verify admin role chat=%s user=%s", chat_id, user_id)
        return False


async def bot_can_post(bot: Bot, channel_id: int, bot_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel_id, bot_id)
        return (
            member.status == ChatMemberStatus.CREATOR
            or (
                member.status == ChatMemberStatus.ADMINISTRATOR
                and bool(member.can_post_messages)
            )
        )
    except TelegramAPIError:
        logger.warning("Could not verify channel posting rights: %s", channel_id)
        return False


async def run() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN must be configured")
    store = RouteStore(os.getenv("DATABASE_PATH", "/data/bot.sqlite3"))
    sessions: dict[int, Setup] = {}
    bot = Bot(token=token)
    dp = Dispatcher()
    me = await bot.get_me()

    @dp.message()
    async def handle(message: Message) -> None:
        user = message.from_user
        if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
            logger.info(
                "RECEIVED group=%s msg=%s user_bot=%s sender_chat=%s has_text=%s has_caption=%s",
                message.chat.id, message.message_id,
                user.is_bot if user else None,
                message.sender_chat is not None,
                message.text is not None, message.caption is not None,
            )
        if user is None or user.is_bot:
            if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
                logger.info("SKIP_NO_HUMAN_SENDER group=%s msg=%s", message.chat.id, message.message_id)
            return

        is_private = message.chat.type == ChatType.PRIVATE
        text = (message.text or "").strip()
        command = text.split(maxsplit=1)[0].split("@")[0].lower() if text.startswith("/") else ""

        if is_private:
            if command in {"/start", "/help"}:
                await message.answer(
                    "📌 Hashtag Relay\n"
                    "/setup — grup, kanal ve hashtag seç\n"
                    "/cancel — kurulumu iptal et\n"
                    "Grup içindeki /hashtags, /status ve /disable komutları da kullanılabilir.\n"
                    "Botu kaynak gruba ve hedef kanala yönetici olarak ekleyin."
                )
                return
            if command == "/cancel":
                sessions.pop(user.id, None)
                await message.answer("Kurulum iptal edildi.", reply_markup=ReplyKeyboardRemove())
                return
            if command == "/setup":
                req = secrets.randbelow(2**31 - 1) + 1
                sessions[user.id] = Setup(stage="group", request_id=req)
                await message.answer(
                    "Önce kaynak grubu seçin. Seçtiğiniz grupta yönetici olmalısınız.",
                    reply_markup=picker(req, channel=False),
                )
                return

            session = sessions.get(user.id)
            if session is None:
                return

            if message.chat_shared is not None:
                shared = message.chat_shared
                if shared.request_id != session.request_id:
                    return
                chosen = shared.chat_id
                if not await admin_of(bot, chosen, user.id):
                    await message.answer("Bu sohbet için yönetici yetkiniz doğrulanamadı.")
                    return
                try:
                    chat = await bot.get_chat(chosen)
                except TelegramAPIError:
                    await message.answer("Bot seçilen sohbete erişemiyor. Önce botu yönetici ekleyin.")
                    return

                if session.stage == "group":
                    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
                        await message.answer("Yalnızca grup/süpergrup seçilebilir.")
                        return
                    if not await admin_of(bot, chosen, me.id):
                        await message.answer("Botu kaynak gruba yönetici olarak ekleyip tekrar seçin.")
                        return
                    session.source_id = chosen
                    session.stage = "channel"
                    session.request_id = secrets.randbelow(2**31 - 1) + 1
                    await message.answer(
                        "Şimdi hedef kanalı seçin. Kanalda yönetici olmalı, botun da gönderi paylaşma izni olmalı.",
                        reply_markup=picker(session.request_id, channel=True),
                    )
                    return

                if session.stage == "channel":
                    if chat.type != ChatType.CHANNEL or not await bot_can_post(bot, chosen, me.id):
                        await message.answer("Kanal geçersiz veya botun mesaj yayınlama izni yok.")
                        return
                    session.target_id = chosen
                    session.stage = "tags"
                    await message.answer(
                        "Hashtag'leri virgülle ayırın. Örnek: Analiz, Kar, Proje",
                        reply_markup=ReplyKeyboardRemove(),
                    )
                    return

            if session.stage == "tags" and text and not text.startswith("/"):
                try:
                    tags = normalize_tags(text)
                except ValueError as exc:
                    await message.answer(str(exc))
                    return
                if session.source_id is None or session.target_id is None:
                    sessions.pop(user.id, None)
                    await message.answer("Kurulum verisi eksik. /setup ile yeniden başlayın.")
                    return
                # Recheck permissions at commit time, not only at selection time.
                if not (
                    await admin_of(bot, session.source_id, user.id)
                    and await admin_of(bot, session.source_id, me.id)
                    and await admin_of(bot, session.target_id, user.id)
                    and await bot_can_post(bot, session.target_id, me.id)
                ):
                    sessions.pop(user.id, None)
                    await message.answer("Yetki doğrulaması başarısız. /setup ile yeniden deneyin.")
                    return
                store.save(session.source_id, session.target_id, tags, user.id)
                sessions.pop(user.id, None)
                await message.answer(
                    f"✅ Kaydedildi!\nGrup: {session.source_id}\nKanal: {session.target_id}\n"
                    f"Hashtag: {', '.join('#' + tag for tag in tags)}"
                )
            return

        if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            return

        route = store.get(message.chat.id)
        if command in {"/status", "/hashtags", "/disable"}:
            if message.sender_chat is not None or not await admin_of(bot, message.chat.id, user.id):
                await message.answer("Bu komut yalnızca grup yöneticileri içindir.")
                return
            if command == "/status":
                if route is None:
                    await message.answer("Bu grup henüz yapılandırılmadı. Botla özel sohbetten /setup yazın.")
                else:
                    await message.answer(
                        f"Durum: {'Aktif' if route.enabled else 'Kapalı'}\n"
                        f"Kanal: {route.target_id}\n"
                        f"Etiketler: {', '.join('#' + tag for tag in route.tags)}"
                    )
                return
            if route is None:
                await message.answer("Önce özel sohbet üzerinden /setup tamamlayın.")
                return
            if command == "/disable":
                store.disable(message.chat.id, user.id)
                await message.answer("⏸ Bu grup için aktarım durduruldu. Yeniden etkinleştirmek için /setup kullanın.")
                return
            parts = text.split(maxsplit=1)
            if len(parts) != 2:
                await message.answer("Kullanım: /hashtags Analiz,Kar,Proje")
                return
            try:
                tags = normalize_tags(parts[1])
            except ValueError as exc:
                await message.answer(str(exc))
                return
            store.set_tags(message.chat.id, tags, user.id)
            await message.answer("✅ Hashtag'ler güncellendi: " + ", ".join("#" + t for t in tags))
            return

        if route is None or not route.enabled:
            logger.info("SKIP_NO_ACTIVE_ROUTE group=%s msg=%s", message.chat.id, message.message_id)
            return
        if message.sender_chat is not None:
            logger.info("SKIP_ANONYMOUS group=%s msg=%s", message.chat.id, message.message_id)
            return
        if not eligible_content(message.text, message.caption, compile_hashtags(",".join(route.tags))):
            logger.info("SKIP_HASHTAG group=%s msg=%s", message.chat.id, message.message_id)
            return
        if not await admin_of(bot, message.chat.id, user.id):
            logger.info("SKIP_NOT_ADMIN group=%s msg=%s", message.chat.id, message.message_id)
            return
        logger.info("PUBLISH_ATTEMPT group=%s msg=%s target=%s", message.chat.id, message.message_id, route.target_id)
        try:
            await bot.copy_message(
                chat_id=route.target_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            logger.info("Published group=%s message=%s", message.chat.id, message.message_id)
        except TelegramAPIError:
            logger.exception("Failed to publish group=%s message=%s", message.chat.id, message.message_id)

    try:
        logger.info("Bot @%s running with per-group settings", me.username)
        await dp.start_polling(bot, allowed_updates=["message"])
    finally:
        store.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(run())
