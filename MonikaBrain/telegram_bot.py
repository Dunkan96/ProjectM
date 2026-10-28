# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import CREATOR_TELEGRAM_ID, STREAMER_ID, TELEGRAM_BOT_TOKEN, TELEGRAM_PROXY_URL
from monika_text_runtime import MonikaTextRuntime

try:
    if os.name == "nt":
        os.system("chcp 65001 > nul")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


logging.basicConfig(level=logging.INFO, stream=sys.stdout)
log = logging.getLogger("monika.telegram")


session = None
if TELEGRAM_PROXY_URL:
    try:
        from aiohttp_socks import ProxyConnector
        import aiohttp

        connector = ProxyConnector.from_url(TELEGRAM_PROXY_URL)
        aiohttp_session = aiohttp.ClientSession(connector=connector)
        session = AiohttpSession(aiohttp_client=aiohttp_session)
        log.info("Telegram proxy enabled")
    except ImportError:
        log.warning("Для прокси установите aiohttp_socks")


if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is empty. Set it in config.py or environment.")


runtime = MonikaTextRuntime(user_id=STREAMER_ID)
user_sessions: dict[str, dict] = {}
user_locks: dict[str, asyncio.Lock] = {}
pending_messages: dict[str, tuple[Message, float, list[str]]] = {}

bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def get_person_id(message: Message) -> str:
    if message.from_user and message.from_user.id == CREATOR_TELEGRAM_ID:
        return STREAMER_ID
    return str(message.from_user.id if message.from_user else "telegram_user")


def get_display_name(message: Message) -> str:
    if not message.from_user:
        return "telegram_user"
    if message.from_user.username:
        return f"@{message.from_user.username}"
    return message.from_user.full_name or str(message.from_user.id)


def get_role(message: Message) -> str:
    return "creator" if message.from_user and message.from_user.id == CREATOR_TELEGRAM_ID else "viewer"


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    person_id = get_person_id(message)
    role = get_role(message)
    user_sessions[person_id] = runtime.new_session(role=role)

    display_name = get_display_name(message)
    await message.answer(f"Привет, {display_name}. Я Моника. Пиши — будем тестировать мой мозг без голоса и TTS.")


@dp.message(Command(commands=["clear"]))
async def cmd_clear(message: Message) -> None:
    person_id = get_person_id(message)
    role = get_role(message)
    user_sessions[person_id] = runtime.new_session(role=role)
    await message.answer("Окей, локальную историю этого Telegram-диалога очистила.")


@dp.message(Command(commands=["ping"]))
async def cmd_ping(message: Message) -> None:
    await message.answer("Я жива. Telegram-runtime подключен.")


@dp.message()
async def handle_message(message: Message) -> None:
    if not message.text:
        return

    person_id = get_person_id(message)
    display_name = get_display_name(message)
    role = get_role(message)

    session_data = user_sessions.setdefault(person_id, runtime.new_session(role=role))
    handled, command_reply = runtime.handle_private_mode_command(message.text, session_data, role)
    if handled:
        if command_reply:
            await message.answer(command_reply)
        return

    # Merge very fast consecutive Telegram messages from one user into one turn.
    existing = pending_messages.get(person_id)
    if existing:
        root_message, _, buffered = existing
        buffered.append(message.text)
        pending_messages[person_id] = (root_message, time.monotonic(), buffered)
    else:
        pending_messages[person_id] = (message, time.monotonic(), [message.text])
    await asyncio.sleep(0.65)
    latest, ts, buffered = pending_messages.get(person_id, (message, 0.0, [message.text]))
    if latest.message_id != message.message_id or time.monotonic() - ts < 0.6:
        return
    pending_messages.pop(person_id, None)
    merged_text = "\n".join(x for x in buffered if str(x or "").strip())

    lock = user_locks.setdefault(person_id, asyncio.Lock())
    async with lock:
        await bot.send_chat_action(chat_id=message.chat.id, action="typing")

        try:
            reply = runtime.answer(
                user_text=merged_text,
                session=session_data,
                person_id=person_id,
                display_name=display_name,
                role=role,
            )
        except Exception:
            log.exception("Telegram runtime failed")
            reply = "У меня сейчас что-то треснуло в голове. Ошибку записала, но красивую мину делать не буду."

        if str(reply or "").strip():
            await message.answer(reply)


async def main() -> None:
    log.info("Запуск Telegram-бота Моники...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Бот остановлен.")
    finally:
        runtime.close()
        if session:
            try:
                asyncio.run(session.close())
            except Exception:
                pass
