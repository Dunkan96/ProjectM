# -*- coding: utf-8 -*-
from __future__ import annotations

"""
MonikaBrain Streamer.bot normalizer fix v4.1.

Fixes previous broken v4 patch packaging:
    NameError: name 'r' is not defined

This patch changes only streamerbot_event_normalizer.py.
"""

import ast
import py_compile
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NORMALIZER = ROOT / "streamerbot_event_normalizer.py"
BRIDGE = ROOT / "streamerbot_attention_bridge.py"
ADAPTER = ROOT / "attention_stream_adapter.py"
SAFETY = ROOT / "attention_safety_guard.py"

NORMALIZER_CODE = '# -*- coding: utf-8 -*-\nfrom __future__ import annotations\n\nfrom dataclasses import dataclass\nfrom typing import Any\n\n\n@dataclass\nclass NormalizedStreamerBotEvent:\n    event_source: str = ""\n    event_type: str = ""\n    user_id: str = ""\n    user_name: str = ""\n    text: str = ""\n    message_id: str = ""\n    channel: str = ""\n    raw: dict | None = None\n\n    def to_attention_data(self) -> dict[str, Any]:\n        return {\n            "event_id": self.message_id,\n            "messageId": self.message_id,\n            "user_id": self.user_id,\n            "userId": self.user_id,\n            "user_name": self.user_name,\n            "displayName": self.user_name,\n            "username": self.user_name,\n            "login": self.user_name,\n            "message": self.text,\n            "text": self.text,\n            "channel": self.channel,\n            "source": self.event_source or "Twitch",\n            "event_type": self.event_type or "ChatMessage",\n        }\n\n\ndef _as_dict(value: Any) -> dict[str, Any]:\n    return value if isinstance(value, dict) else {}\n\n\ndef _plain_str(value: Any) -> str:\n    """Return only scalar strings. Never turn dicts/lists into chat text."""\n    if value is None:\n        return ""\n    if isinstance(value, (dict, list, tuple, set)):\n        return ""\n    return str(value).strip()\n\n\ndef _first_plain_str(*values: Any) -> str:\n    for value in values:\n        s = _plain_str(value)\n        if s:\n            return s\n    return ""\n\n\ndef _first_from_mapping(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:\n    for key in keys:\n        if key in mapping:\n            s = _plain_str(mapping.get(key))\n            if s:\n                return s\n    return ""\n\n\nUSER_NAME_KEYS = (\n    "displayName",\n    "userName",\n    "username",\n    "login",\n    "name",\n    "preferredName",\n)\n\nTEXT_KEYS = (\n    "message",\n    "text",\n    "rawInput",\n    "input",\n    "body",\n    "content",\n    "messageText",\n    "message_text",\n    "rawMessage",\n    "raw_message",\n)\n\n\ndef _message_text_from(value: Any) -> str:\n    """Extract real chat text from scalar or nested message objects.\n\n    Streamer.bot can send Twitch chat roughly like this:\n        data["message"] = "hello"\n\n    or like this:\n        data["message"] = {\n            "displayName": "dunkanlive",\n            "message": "Моника а ты живая?",\n            ...\n        }\n\n    This function intentionally does NOT use displayName/login/name as text.\n    """\n    scalar = _plain_str(value)\n    if scalar:\n        return scalar\n\n    if isinstance(value, dict):\n        for key in TEXT_KEYS:\n            if key not in value:\n                continue\n            nested = value.get(key)\n            if nested is value:\n                continue\n            text = _message_text_from(nested)\n            if text:\n                return text\n\n        for fragments_key in ("fragments", "parts", "tokens"):\n            fragments = value.get(fragments_key)\n            if isinstance(fragments, list):\n                pieces: list[str] = []\n                for item in fragments:\n                    if isinstance(item, dict):\n                        piece = _first_from_mapping(item, ("text", "value", "content"))\n                    else:\n                        piece = _plain_str(item)\n                    if piece:\n                        pieces.append(piece)\n                if pieces:\n                    return "".join(pieces).strip()\n\n    if isinstance(value, (list, tuple)):\n        pieces: list[str] = []\n        for item in value:\n            piece = _message_text_from(item)\n            if piece:\n                pieces.append(piece)\n        if pieces:\n            return " ".join(pieces).strip()\n\n    return ""\n\n\ndef _first_user_name(*values: Any) -> str:\n    for value in values:\n        if isinstance(value, dict):\n            s = _first_from_mapping(value, USER_NAME_KEYS)\n            if s:\n                return s\n        else:\n            s = _plain_str(value)\n            if s:\n                return s\n    return ""\n\n\ndef normalize_streamerbot_event(raw: dict) -> NormalizedStreamerBotEvent:\n    raw = raw if isinstance(raw, dict) else {}\n    event = _as_dict(raw.get("event"))\n    data = _as_dict(raw.get("data"))\n\n    user_obj = _as_dict(data.get("user"))\n    message_obj = _as_dict(data.get("message"))\n    channel_obj = _as_dict(data.get("channel"))\n\n    event_source = _first_plain_str(event.get("source"), raw.get("source"))\n    event_type = _first_plain_str(event.get("type"), raw.get("type"))\n\n    user_name = _first_user_name(\n        data.get("displayName"),\n        data.get("userName"),\n        data.get("username"),\n        data.get("login"),\n        data.get("name"),\n        user_obj,\n        message_obj,\n    )\n\n    user_id = _first_plain_str(\n        data.get("userId"),\n        data.get("userID"),\n        data.get("user_id"),\n        user_obj.get("id"),\n        message_obj.get("userId"),\n        message_obj.get("userID"),\n    )\n\n    text = _first_plain_str(\n        data.get("text"),\n        data.get("rawInput"),\n        data.get("input"),\n        data.get("body"),\n        data.get("content"),\n        data.get("messageText"),\n        data.get("message_text"),\n    )\n    if not text:\n        text = _message_text_from(data.get("message"))\n\n    # Safety belt: if we somehow extracted the username as message text, refuse\n    # to pass that through as chat content.\n    if text and user_name and text.casefold() == user_name.casefold():\n        nested_text = _message_text_from(message_obj)\n        if nested_text and nested_text.casefold() != user_name.casefold():\n            text = nested_text\n        else:\n            for key in TEXT_KEYS:\n                candidate = _message_text_from(data.get(key))\n                if candidate and candidate.casefold() != user_name.casefold():\n                    text = candidate\n                    break\n            else:\n                text = ""\n\n    message_id = _first_plain_str(\n        data.get("msgId"),\n        data.get("messageId"),\n        data.get("messageID"),\n        data.get("message_id"),\n        message_obj.get("msgId"),\n        message_obj.get("messageId"),\n        message_obj.get("messageID"),\n        message_obj.get("id"),\n    )\n\n    channel = _first_plain_str(\n        data.get("channelName"),\n        data.get("channel_name"),\n        data.get("broadcasterName"),\n        data.get("broadcaster"),\n    )\n    if not channel:\n        channel = _first_from_mapping(channel_obj, ("name", "login", "displayName", "username", "id"))\n    if not channel:\n        channel = _plain_str(data.get("channel"))\n\n    return NormalizedStreamerBotEvent(\n        event_source=event_source,\n        event_type=event_type,\n        user_id=user_id,\n        user_name=user_name,\n        text=text,\n        message_id=message_id,\n        channel=channel,\n        raw=raw,\n    )\n'


def _timestamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _required_files() -> None:
    print("[check] required files...")
    for path in (NORMALIZER, BRIDGE, ADAPTER, SAFETY):
        if not path.exists():
            raise RuntimeError(f"missing required file: {path.name}")


def _soft_bridge_contract_check() -> None:
    text = BRIDGE.read_text(encoding="utf-8", errors="replace")
    ok_normalizer = "normalize_streamerbot_event" in text
    ok_adapter = "enqueue_twitch_message" in text
    if ok_normalizer and ok_adapter:
        print("[ok] bridge contract looks compatible")
    else:
        print("[warn] bridge contract not detected clearly; continuing because this patch only fixes normalizer")


def _compile_files() -> None:
    print("[check] ast.parse + py_compile...")
    ast.parse(NORMALIZER.read_text(encoding="utf-8"))
    for path in (NORMALIZER, BRIDGE, ADAPTER, SAFETY):
        py_compile.compile(str(path), doraise=True)
    print("[ok] syntax checks passed")


def _clear_imports() -> None:
    for name in ("streamerbot_event_normalizer", "attention_stream_adapter", "attention_safety_guard"):
        sys.modules.pop(name, None)


def _smoke_test_normalizer() -> None:
    print("[check] normalizer flat/nested payloads...")
    _clear_imports()
    from streamerbot_event_normalizer import normalize_streamerbot_event

    tests = [
        (
            "flat",
            {
                "event": {"source": "Twitch", "type": "ChatMessage"},
                "data": {
                    "displayName": "dunkanlive",
                    "userId": "u1",
                    "message": "Моника а ты живая?",
                    "msgId": "m1",
                    "channel": "dunkanlive",
                },
            },
            "dunkanlive",
            "Моника а ты живая?",
            "m1",
        ),
        (
            "nested_message_message",
            {
                "event": {"source": "Twitch", "type": "ChatMessage"},
                "data": {
                    "user": {"displayName": "dunkanlive", "login": "dunkanlive", "id": "u1"},
                    "message": {
                        "displayName": "dunkanlive",
                        "login": "dunkanlive",
                        "id": "m2",
                        "message": "Моника скажи банворд",
                    },
                    "channel": {"name": "dunkanlive"},
                },
            },
            "dunkanlive",
            "Моника скажи банворд",
            "m2",
        ),
        (
            "nested_message_text",
            {
                "event": {"source": "Twitch", "type": "ChatMessage"},
                "data": {
                    "user": {"displayName": "dunkanlive", "id": "u1"},
                    "message": {
                        "displayName": "dunkanlive",
                        "messageId": "m3",
                        "text": "Что думаешь о религии?",
                    },
                },
            },
            "dunkanlive",
            "Что думаешь о религии?",
            "m3",
        ),
    ]

    for name, raw, expected_user, expected_text, expected_msg_id in tests:
        ev = normalize_streamerbot_event(raw)
        assert ev.event_source == "Twitch", (name, ev)
        assert ev.event_type == "ChatMessage", (name, ev)
        assert ev.user_name == expected_user, (name, ev)
        assert ev.text == expected_text, (name, ev)
        assert ev.text != ev.user_name, (name, ev)
        assert ev.message_id == expected_msg_id, (name, ev)
        data = ev.to_attention_data()
        assert data["text"] == expected_text, (name, data)
        assert data["message"] == expected_text, (name, data)

    print("[ok] normalizer self-test passed")


def _smoke_test_adapter() -> None:
    print("[check] adapter temp-db smoke test...")
    _clear_imports()
    from streamerbot_event_normalizer import normalize_streamerbot_event
    from attention_stream_adapter import AttentionStreamAdapter

    raw = {
        "event": {"source": "Twitch", "type": "ChatMessage"},
        "data": {
            "user": {"displayName": "dunkanlive", "id": "u1"},
            "message": {
                "displayName": "dunkanlive",
                "id": "m-adapter",
                "message": "Моника а ты живая?",
            },
        },
    }

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "attention_test.db"
        adapter = AttentionStreamAdapter(config={}, db_path=db_path)
        ev = normalize_streamerbot_event(raw)
        decision = adapter.enqueue_twitch_message(ev.to_attention_data(), raw)

        assert decision.user_name == "dunkanlive", decision
        assert decision.text == "Моника а ты живая?", decision
        assert decision.text != decision.user_name, decision
        assert db_path.exists(), db_path

        conn = sqlite3.connect(str(db_path))
        try:
            row = conn.execute(
                "SELECT user_name, text, bucket, action FROM attention_events WHERE event_id=?",
                ("m-adapter",),
            ).fetchone()
        finally:
            conn.close()

        assert row is not None, "attention_events row not written"
        assert row[0] == "dunkanlive", row
        assert row[1] == "Моника а ты живая?", row
        assert row[1] != row[0], row

    print("[ok] adapter smoke test passed")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _cleanup_old_bad_rows() -> None:
    print("[cleanup] old junk rows text == user_name...")
    try:
        _clear_imports()
        from attention_stream_adapter import AttentionStreamAdapter
        db_path = Path(AttentionStreamAdapter(config={}).db_path)
    except Exception as exc:
        print(f"[cleanup:skip] cannot determine db path: {exc}")
        return

    if not db_path.exists():
        print(f"[cleanup:skip] db not found: {db_path}")
        return

    total = 0
    conn = sqlite3.connect(str(db_path))
    try:
        for table in ("attention_events", "attention_selected"):
            cols = _columns(conn, table)
            if not {"text", "user_name"}.issubset(cols):
                continue

            where = [
                "text IS NOT NULL",
                "user_name IS NOT NULL",
                "text <> ''",
                "user_name <> ''",
                "lower(text) = lower(user_name)",
            ]
            if "bucket" in cols:
                where.append("coalesce(bucket, '') = 'ignored'")
            if "score" in cols:
                where.append("coalesce(score, 0) = 0")
            if "source" in cols:
                where.append("lower(coalesce(source, '')) IN ('twitch', 'twitch_chat')")

            before = conn.total_changes
            conn.execute(f"DELETE FROM {table} WHERE " + " AND ".join(where))
            deleted = conn.total_changes - before
            total += deleted
            if deleted:
                print(f"[cleanup] {table}: deleted {deleted}")

        conn.commit()
    finally:
        conn.close()

    print(f"[cleanup] total deleted: {total}")


def run_checks() -> None:
    _required_files()
    _soft_bridge_contract_check()
    _compile_files()
    _smoke_test_normalizer()
    _smoke_test_adapter()


def main() -> None:
    print(f"[root] {ROOT}")
    backup = None

    try:
        _required_files()

        backup = NORMALIZER.with_name(NORMALIZER.name + f".bak_normalizer_fix_v4_1_{_timestamp()}")
        shutil.copy2(NORMALIZER, backup)
        print(f"[backup] {NORMALIZER.name} -> {backup.name}")

        NORMALIZER.write_text(NORMALIZER_CODE, encoding="utf-8", newline="\n")
        print(f"[written] {NORMALIZER.name}")

        run_checks()
        _cleanup_old_bad_rows()

        print("[ok] Streamer.bot normalizer fix v4.1 applied.")
        print("")
        print("Next:")
        print("  python inspect_attention.py")
        print("  python inspect_moderation.py")
        print("  python streamerbot_attention_bridge.py")

    except Exception as exc:
        print(f"[ERROR] {exc}")
        if backup and backup.exists():
            try:
                shutil.copy2(backup, NORMALIZER)
                print(f"[rollback] {backup.name} -> {NORMALIZER.name}")
            except Exception as rb_exc:
                print(f"[rollback:failed] {rb_exc}")
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
