# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NormalizedStreamerBotEvent:
    event_source: str = ""
    event_type: str = ""
    user_id: str = ""
    user_name: str = ""
    text: str = ""
    message_id: str = ""
    channel: str = ""
    raw: dict | None = None

    def to_attention_data(self) -> dict[str, Any]:
        return {
            "event_id": self.message_id,
            "messageId": self.message_id,
            "user_id": self.user_id,
            "userId": self.user_id,
            "user_name": self.user_name,
            "displayName": self.user_name,
            "username": self.user_name,
            "login": self.user_name,
            "message": self.text,
            "text": self.text,
            "channel": self.channel,
            "source": self.event_source or "Twitch",
            "event_type": self.event_type or "ChatMessage",
        }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _plain_str(value: Any) -> str:
    """Return only scalar strings. Never turn dicts/lists into chat text."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value).strip()


def _first_plain_str(*values: Any) -> str:
    for value in values:
        s = _plain_str(value)
        if s:
            return s
    return ""


def _first_from_mapping(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key in mapping:
            s = _plain_str(mapping.get(key))
            if s:
                return s
    return ""


USER_NAME_KEYS = (
    "displayName",
    "userName",
    "username",
    "login",
    "name",
    "preferredName",
)

TEXT_KEYS = (
    "message",
    "text",
    "rawInput",
    "input",
    "body",
    "content",
    "messageText",
    "message_text",
    "rawMessage",
    "raw_message",
)


def _message_text_from(value: Any) -> str:
    """Extract real chat text from scalar or nested message objects.

    Streamer.bot can send Twitch chat roughly like this:
        data["message"] = "hello"

    or like this:
        data["message"] = {
            "displayName": "dunkanlive",
            "message": "Моника а ты живая?",
            ...
        }

    This function intentionally does NOT use displayName/login/name as text.
    """
    scalar = _plain_str(value)
    if scalar:
        return scalar

    if isinstance(value, dict):
        for key in TEXT_KEYS:
            if key not in value:
                continue
            nested = value.get(key)
            if nested is value:
                continue
            text = _message_text_from(nested)
            if text:
                return text

        for fragments_key in ("fragments", "parts", "tokens"):
            fragments = value.get(fragments_key)
            if isinstance(fragments, list):
                pieces: list[str] = []
                for item in fragments:
                    if isinstance(item, dict):
                        piece = _first_from_mapping(item, ("text", "value", "content"))
                    else:
                        piece = _plain_str(item)
                    if piece:
                        pieces.append(piece)
                if pieces:
                    return "".join(pieces).strip()

    if isinstance(value, (list, tuple)):
        pieces: list[str] = []
        for item in value:
            piece = _message_text_from(item)
            if piece:
                pieces.append(piece)
        if pieces:
            return " ".join(pieces).strip()

    return ""


def _first_user_name(*values: Any) -> str:
    for value in values:
        if isinstance(value, dict):
            s = _first_from_mapping(value, USER_NAME_KEYS)
            if s:
                return s
        else:
            s = _plain_str(value)
            if s:
                return s
    return ""


def normalize_streamerbot_event(raw: dict) -> NormalizedStreamerBotEvent:
    raw = raw if isinstance(raw, dict) else {}
    event = _as_dict(raw.get("event"))
    data = _as_dict(raw.get("data"))

    user_obj = _as_dict(data.get("user"))
    message_obj = _as_dict(data.get("message"))
    channel_obj = _as_dict(data.get("channel"))

    event_source = _first_plain_str(event.get("source"), raw.get("source"))
    event_type = _first_plain_str(event.get("type"), raw.get("type"))

    user_name = _first_user_name(
        data.get("displayName"),
        data.get("userName"),
        data.get("username"),
        data.get("login"),
        data.get("name"),
        user_obj,
        message_obj,
    )

    user_id = _first_plain_str(
        data.get("userId"),
        data.get("userID"),
        data.get("user_id"),
        user_obj.get("id"),
        message_obj.get("userId"),
        message_obj.get("userID"),
    )

    text = _first_plain_str(
        data.get("text"),
        data.get("rawInput"),
        data.get("input"),
        data.get("body"),
        data.get("content"),
        data.get("messageText"),
        data.get("message_text"),
    )
    if not text:
        text = _message_text_from(data.get("message"))

    # Safety belt: if we somehow extracted the username as message text, refuse
    # to pass that through as chat content.
    if text and user_name and text.casefold() == user_name.casefold():
        nested_text = _message_text_from(message_obj)
        if nested_text and nested_text.casefold() != user_name.casefold():
            text = nested_text
        else:
            for key in TEXT_KEYS:
                candidate = _message_text_from(data.get(key))
                if candidate and candidate.casefold() != user_name.casefold():
                    text = candidate
                    break
            else:
                text = ""

    message_id = _first_plain_str(
        data.get("msgId"),
        data.get("messageId"),
        data.get("messageID"),
        data.get("message_id"),
        message_obj.get("msgId"),
        message_obj.get("messageId"),
        message_obj.get("messageID"),
        message_obj.get("id"),
    )

    channel = _first_plain_str(
        data.get("channelName"),
        data.get("channel_name"),
        data.get("broadcasterName"),
        data.get("broadcaster"),
    )
    if not channel:
        channel = _first_from_mapping(channel_obj, ("name", "login", "displayName", "username", "id"))
    if not channel:
        channel = _plain_str(data.get("channel"))

    return NormalizedStreamerBotEvent(
        event_source=event_source,
        event_type=event_type,
        user_id=user_id,
        user_name=user_name,
        text=text,
        message_id=message_id,
        channel=channel,
        raw=raw,
    )
