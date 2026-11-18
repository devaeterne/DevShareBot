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
from bot.sender_policy import is_anonymous_group_post
from bot.requests import parse_request
from bot.request_schedule import now_local, in_window, parse_hours, describe_hours
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
    kind: str = "publish"


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
        anonymous_group_post = is_anonymous_group_post(message)
        if (user is None or user.is_bot) and not anonymous_group_post:
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
                    "/setuptalep — kaynak grup ve hedef talep grubu seç\n"
                    "/cancel — kurulumu iptal et\n"
                    "Grup komutları: /hashtags /status /disable /talep açık /talep kapalı\n"
                    "/taleplimit 1 /talepsaat 09:00-18:00 /talepstatus.\n"
                    "Botu kaynak gruba ve hedef kanala yönetici olarak ekleyin."
                )
                return
            if command == "/cancel":
                sessions.pop(user.id, None)
                await message.answer("Kurulum iptal edildi.", reply_markup=ReplyKeyboardRemove())
                return
            if command in {"/setup", "/setuptalep"}:
                req = secrets.randbelow(2**31 - 1) + 1
                kind = "request" if command == "/setuptalep" else "publish"
                sessions[user.id] = Setup(stage="group", request_id=req, kind=kind)
                await message.answer(
                    "Talep gönderecek kaynak grubu seçin." if kind == "request"
                    else "Önce kaynak grubu seçin. Seçtiğiniz grupta yönetici olmalısınız.",
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
                    session.stage = "request_target" if session.kind == "request" else "channel"
                    session.request_id = secrets.randbelow(2**31 - 1) + 1
                    await message.answer(
                        "Taleplerin ulaşacağı ikinci grubu seçin. Bot her iki grupta da yönetici olmalı."
                        if session.kind == "request"
                        else "Şimdi hedef kanalı seçin. Kanalda yönetici olmalı, botun da gönderi paylaşma izni olmalı.",
                        reply_markup=picker(session.request_id, channel=session.kind != "request"),
                    )
                    return

                if session.stage == "request_target":
                    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
                        await message.answer("Talep hedefi bir grup veya süpergrup olmalıdır.")
                        return
                    if chosen == session.source_id:
                        await message.answer("Kaynak ve hedef gruplar farklı olmalıdır.")
                        return
                    if not await admin_of(bot, chosen, me.id):
                        await message.answer("Botu hedef gruba yönetici olarak ekleyin.")
                        return
                    if session.source_id is None or not (
                        await admin_of(bot, session.source_id, user.id)
                        and await admin_of(bot, session.source_id, me.id)
                        and await admin_of(bot, chosen, user.id)
                        and await admin_of(bot, chosen, me.id)
                    ):
                        await message.answer("Grup yönetici yetkileri yeniden doğrulanamadı. /setuptalep ile tekrar deneyin.")
                        sessions.pop(user.id, None)
                        return
                    store.save_request(session.source_id, chosen, user.id)
                    sessions.pop(user.id, None)
                    await message.answer(
                        f"✅ Talep yönlendirmesi kaydedildi!\n"
                        f"Kaynak grup: {session.source_id}\n"
                        f"Talep grubu: {chosen}\n"
                        "Üyeler artık #Talep XAUUSD gibi mesajlar gönderebilir.",
                        reply_markup=ReplyKeyboardRemove(),
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
        request_route = store.get_request(message.chat.id)
        if command in {"/status", "/hashtags", "/disable", "/talepstatus", "/talepkapat", "/talep", "/taleplimit", "/talepsaat"}:
            if anonymous_group_post or message.sender_chat is not None or user is None or not await admin_of(bot, message.chat.id, user.id):
                await message.answer("Bu komut yalnızca grup yöneticileri içindir.")
                return
            if command == "/talepstatus":
                await message.answer(
                    "Talep yönlendirmesi tanımlı değil. Özel sohbetten /setuptalep kullanın."
                    if request_route is None
                    else f"Talep: {'Açık' if request_route.enabled else 'Kapalı'}\n"
                         f"Hedef grup: {request_route.target_id}\n"
                         f"Günlük kişi limiti: {request_route.daily_limit}\n"
                         f"Talep saatleri (Türkiye): {describe_hours(request_route.start_minute, request_route.end_minute)}"
                )
                return
            if command in {"/talep", "/taleplimit", "/talepsaat"}:
                if request_route is None:
                    await message.answer("Önce özel sohbetten /setuptalep ile hedef grubu seçin.")
                    return
                arg = text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) == 2 else ""
                if command == "/talep":
                    if arg.casefold() in {"açık", "acik"}:
                        store.set_request_enabled(message.chat.id, True, user.id)
                        await message.answer("✅ Talep alımı açıldı.")
                    elif arg.casefold() in {"kapalı", "kapali"}:
                        store.set_request_enabled(message.chat.id, False, user.id)
                        await message.answer("⏸ Talep alımı kapatıldı.")
                    else:
                        await message.answer("Kullanım: /talep açık veya /talep kapalı")
                    return
                if command == "/taleplimit":
                    try:
                        if not arg.isascii() or not arg.isdecimal():
                            raise ValueError()
                        limit = int(arg)
                        store.set_request_limit(message.chat.id, limit, user.id)
                    except ValueError:
                        await message.answer("Kullanım: /taleplimit 1 (1-20)")
                        return
                    await message.answer(f"✅ Kişi başı günlük limit: {limit}")
                    return
                if command == "/talepsaat":
                    try:
                        start, end = parse_hours(arg)
                        store.set_request_hours(message.chat.id, start, end, user.id)
                    except ValueError as exc:
                        await message.answer(str(exc))
                        return
                    await message.answer(
                        f"✅ Talep saatleri: {describe_hours(start, end)} (Türkiye saati)"
                    )
                    return
            if command == "/talepkapat":
                if request_route is None:
                    await message.answer("Bu grup için talep yönlendirmesi tanımlı değil.")
                else:
                    store.set_request_enabled(message.chat.id, False, user.id)
                    await message.answer("⏸ Talep yönlendirmesi durduruldu. Açmak için /talep açık kullanın.")
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

        # Requests are handled independently of owner/admin channel publishing.
        # A request is accepted only after successful delivery to the target group.
        is_request, request_payload = parse_request(message.text)
        if is_request:
            # Anonymous group-admin messages do not provide a verifiable user ID,
            # and therefore cannot consume a per-user daily quota.
            if message.sender_chat is not None or user is None or user.is_bot:
                logger.info("REQUEST_SKIP_UNIDENTIFIABLE_SENDER group=%s msg=%s", message.chat.id, message.message_id)
                await message.reply("Talep için kişisel hesabınızla mesaj gönderin.")
                return
            if request_route is None:
                logger.info("REQUEST_SKIP_NO_ROUTE group=%s msg=%s", message.chat.id, message.message_id)
                return
            if not request_route.enabled:
                await message.reply("⏸ Talep alımı şu anda kapalı.")
                return
            current = now_local()
            if not in_window(request_route.start_minute, request_route.end_minute, current):
                await message.reply(
                    "⏰ Talep saatleri: "
                    + describe_hours(request_route.start_minute, request_route.end_minute)
                    + " (Türkiye saati)."
                )
                return
            if not request_payload:
                await message.reply("Talep oluşturmak için örnek: #Talep XAUUSD")
                return
            claim = store.claim_request(
                message.chat.id, user.id, current.date().isoformat(), message.message_id
            )
            if claim == "limit":
                await message.reply(
                    f"⏳ Günlük {request_route.daily_limit} talep hakkınızı kullandınız. "
                    "Yarın Türkiye saatiyle 00:00'da yenilenir."
                )
                return
            if claim == "disabled":
                await message.reply("⏸ Talep alımı şu anda kapalı.")
                return
            if claim == "duplicate":
                logger.info("REQUEST_DUPLICATE group=%s msg=%s", message.chat.id, message.message_id)
                return
            try:
                await bot.copy_message(
                    chat_id=request_route.target_id,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id,
                )
            except TelegramAPIError:
                store.finish_request(message.chat.id, message.message_id, delivered=False)
                logger.exception("REQUEST_DELIVERY_FAILED group=%s msg=%s", message.chat.id, message.message_id)
                await message.reply("Talebiniz şu anda iletilemedi. Günlük hakkınız kullanılmadı.")
                return
            store.finish_request(message.chat.id, message.message_id, delivered=True)
            logger.info(
                "REQUEST_DELIVERED source=%s target=%s msg=%s",
                message.chat.id, request_route.target_id, message.message_id
            )
            try:
                await message.reply("✅ Talebiniz alınmıştır.")
            except TelegramAPIError:
                logger.exception("REQUEST_ACK_FAILED group=%s msg=%s", message.chat.id, message.message_id)
            return

        if route is None or not route.enabled:
            logger.info("SKIP_NO_ACTIVE_ROUTE group=%s msg=%s", message.chat.id, message.message_id)
            return
        if message.sender_chat is not None and not anonymous_group_post:
            logger.info("SKIP_OTHER_CHAT_SENDER group=%s msg=%s", message.chat.id, message.message_id)
            return
        if not eligible_content(message.text, message.caption, compile_hashtags(",".join(route.tags))):
            logger.info("SKIP_HASHTAG group=%s msg=%s", message.chat.id, message.message_id)
            return
        if anonymous_group_post:
            # Telegram hides the real user ID for anonymous admins. Only trust
            # messages attributed to the exact same group (not a linked channel).
            logger.info("ANONYMOUS_GROUP_POST_ALLOWED group=%s msg=%s", message.chat.id, message.message_id)
        elif user is None or not await admin_of(bot, message.chat.id, user.id):
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
