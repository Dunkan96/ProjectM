# -*- coding: utf-8 -*-
from __future__ import annotations

import ast
import gc
import importlib
import py_compile
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

NORMALIZER = ROOT / "streamerbot_event_normalizer.py"
BRIDGE = ROOT / "streamerbot_attention_bridge.py"
ADAPTER = ROOT / "attention_stream_adapter.py"

NORMALIZER_SRC = r'''# -*- coding: utf-8 -*-
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
        }


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _str_or_empty(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    text = str(value)
    return text if text else ""


def _first_scalar_str(*values: Any) -> str:
    """Return first scalar string. Dicts/lists are deliberately ignored.

    Important: Streamer.bot can send data["message"] as a dict containing the
    real chat text in data["message"]["message"]. The old normalizer treated
    that dict as a user-like object and returned displayName/login, which caused
    output like: "dunkanlive: dunkanlive". Text extraction must never use a dict
    itself as text.
    """
    for value in values:
        text = _str_or_empty(value)
        if text:
            return text
    return ""


def _first_from_dict(d: dict, *keys: str) -> str:
    for key in keys:
        if key in d:
            text = _str_or_empty(d.get(key))
            if text:
                return text
    return ""


def _first_user_name(*objects: Any) -> str:
    for obj in objects:
        if isinstance(obj, dict):
            value = _first_from_dict(
                obj,
                "displayName",
                "display_name",
                "userName",
                "username",
                "login",
                "name",
                "user",
            )
            if value:
                return value
        else:
            value = _str_or_empty(obj)
            if value:
                return value
    return ""


def _first_id(*objects: Any) -> str:
    for obj in objects:
        if isinstance(obj, dict):
            value = _first_from_dict(
                obj,
                "userId",
                "userID",
                "user_id",
                "id",
                "targetUserId",
                "targetUserID",
            )
            if value:
                return value
        else:
            value = _str_or_empty(obj)
            if value:
                return value
    return ""


def _extract_event(raw: dict) -> tuple[str, str]:
    event = _as_dict(raw.get("event"))
    source = _first_scalar_str(
        event.get("source"),
        raw.get("eventSource"),
        raw.get("source"),
    )
    typ = _first_scalar_str(
        event.get("type"),
        raw.get("eventType"),
        raw.get("type"),
    )
    return source, typ


def _extract_text(data: dict, message_obj: dict) -> str:
    # Order matters. If data["message"] is a dict, use its inner text fields;
    # do not stringify the dict and do not use displayName/login as message text.
    return _first_scalar_str(
        message_obj.get("message"),
        message_obj.get("text"),
        message_obj.get("rawInput"),
        message_obj.get("input"),
        message_obj.get("body"),
        data.get("message") if not isinstance(data.get("message"), dict) else None,
        data.get("text"),
        data.get("rawInput"),
        data.get("input"),
        data.get("body"),
    )


def normalize_streamerbot_event(raw: dict) -> NormalizedStreamerBotEvent:
    raw = raw if isinstance(raw, dict) else {}
    data = _as_dict(raw.get("data"))

    # Streamer.bot Twitch ChatMessage payloads are seen in at least two shapes:
    # 1) flat:   data.displayName + data.message as a string
    # 2) nested: data.user as dict + data.message as dict with message.message
    message_obj = _as_dict(data.get("message"))
    user_obj = _as_dict(data.get("user"))
    author_obj = _as_dict(data.get("author"))
    chatter_obj = _as_dict(data.get("chatter"))

    source, typ = _extract_event(raw)
    text = _extract_text(data, message_obj)

    user_name = _first_user_name(
        user_obj,
        author_obj,
        chatter_obj,
        message_obj,
        data.get("displayName"),
        data.get("username"),
        data.get("userName"),
        data.get("login"),
        data.get("name"),
    )
    user_id = _first_id(
        user_obj,
        author_obj,
        chatter_obj,
        message_obj,
        data.get("userId"),
        data.get("userID"),
        data.get("user_id"),
    )
    message_id = _first_scalar_str(
        message_obj.get("msgId"),
        message_obj.get("messageId"),
        message_obj.get("id"),
        data.get("msgId"),
        data.get("messageId"),
        data.get("id") if not user_id or str(data.get("id")) != str(user_id) else None,
    )
    channel = _first_scalar_str(
        message_obj.get("channel"),
        message_obj.get("channelName"),
        message_obj.get("broadcasterName"),
        data.get("channel"),
        data.get("channelName"),
        data.get("broadcasterName"),
    )

    return NormalizedStreamerBotEvent(
        event_source=source,
        event_type=typ,
        user_id=user_id,
        user_name=user_name,
        text=text,
        message_id=message_id,
        channel=channel,
        raw=raw,
    )
'''

backups: dict[Path, Path | None] = {}


def backup(path: Path) -> None:
    if path in backups:
        return
    if path.exists():
        dst = path.with_name(f"{path.name}.bak_normalizer_fix_v3_{STAMP}")
        shutil.copy2(path, dst)
        backups[path] = dst
        print(f"[backup] {path.name} -> {dst.name}")
    else:
        backups[path] = None


def rollback() -> None:
    print("[rollback] restoring backups...")
    for path, bak in reversed(list(backups.items())):
        try:
            if bak and bak.exists():
                shutil.copy2(bak, path)
                print(f"[rollback] {bak.name} -> {path.name}")
            elif path.exists():
                path.unlink()
                print(f"[rollback] removed created {path.name}")
        except Exception as e:
            print(f"[rollback warn] {path.name}: {e}")


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def find_db() -> Path | None:
    try:
        import config  # type: ignore
        candidates: list[Path] = []
        for name in dir(config):
            upper = name.upper()
            if "DB" not in upper and "DATABASE" not in upper:
                continue
            value = getattr(config, name)
            if isinstance(value, (str, Path)) and str(value).lower().endswith(".db"):
                p = Path(value)
                if not p.is_absolute():
                    p = ROOT / p
                candidates.append(p)
        for p in candidates:
            if p.exists():
                return p
    except Exception:
        pass
    for name in ("monika_memory.db", "knowledge.db"):
        p = ROOT / name
        if p.exists():
            return p
    return None


def cleanup_bad_rows() -> None:
    db = find_db()
    if not db or not db.exists():
        print("[skip] db cleanup: db not found")
        return
    backup(db)
    conn = sqlite3.connect(str(db))
    try:
        total = 0
        if table_exists(conn, "attention_events"):
            cols = columns(conn, "attention_events")
            if {"source", "user_name", "text", "bucket"}.issubset(set(cols)):
                cur = conn.execute(
                    """
                    DELETE FROM attention_events
                    WHERE source='twitch_chat'
                      AND (
                            TRIM(COALESCE(user_name,'')) LIKE '{%'
                         OR TRIM(COALESCE(text,'')) LIKE '{%'
                         OR (LOWER(TRIM(COALESCE(text,''))) = LOWER(TRIM(COALESCE(user_name,''))) AND bucket='ignored')
                      )
                    """
                )
                total += cur.rowcount if cur.rowcount is not None else 0
                print(f"[db] removed bad attention_events rows: {cur.rowcount}")
        if table_exists(conn, "moderation_actions"):
            cols = columns(conn, "moderation_actions")
            if "user_name" in cols:
                cur = conn.execute("DELETE FROM moderation_actions WHERE TRIM(COALESCE(user_name,'')) LIKE '{%'")
                total += cur.rowcount if cur.rowcount is not None else 0
                print(f"[db] removed bad moderation rows: {cur.rowcount}")
        conn.commit()
        print(f"[db] cleanup complete, removed total: {total}")
    finally:
        conn.close()
        gc.collect()


def write_normalizer() -> None:
    backup(NORMALIZER)
    NORMALIZER.write_text(NORMALIZER_SRC, encoding="utf-8")
    print("[written] streamerbot_event_normalizer.py")


def run_checks() -> None:
    print("[check] required files...")
    for p in (ADAPTER, BRIDGE):
        if not p.exists():
            raise FileNotFoundError(p)

    bridge_src = BRIDGE.read_text(encoding="utf-8", errors="replace")
    if "AttentionLayer" in bridge_src or "enqueue_twitch_message(data, raw)" in bridge_src:
        raise RuntimeError("streamerbot_attention_bridge.py still looks like the incompatible old bridge")
    if "AttentionStreamAdapter" not in bridge_src:
        raise RuntimeError("streamerbot_attention_bridge.py does not import/use AttentionStreamAdapter")

    print("[check] py_compile...")
    for p in (NORMALIZER, ADAPTER, BRIDGE):
        py_compile.compile(str(p), doraise=True)

    print("[check] ast parse...")
    for p in (NORMALIZER, ADAPTER, BRIDGE):
        ast.parse(p.read_text(encoding="utf-8"))

    print("[check] import normalizer...")
    sys.path.insert(0, str(ROOT))
    for mod in ("streamerbot_event_normalizer", "attention_stream_adapter"):
        if mod in sys.modules:
            del sys.modules[mod]
    normalizer = importlib.import_module("streamerbot_event_normalizer")

    flat_payload = {
        "event": {"source": "Twitch", "type": "ChatMessage"},
        "data": {
            "msgId": "flat1",
            "userId": "u1",
            "displayName": "viewer_flat",
            "message": "Моника а ты живая?",
            "channel": "monikaaiv1",
        },
    }
    ev = normalizer.normalize_streamerbot_event(flat_payload)
    assert ev.user_name == "viewer_flat", ev
    assert ev.text == "Моника а ты живая?", ev
    assert ev.message_id == "flat1", ev

    nested_payload = {
        "event": {"source": "Twitch", "type": "ChatMessage"},
        "data": {
            "user": {
                "role": 1,
                "id": "261534802",
                "login": "dunkanlive",
                "name": "dunkanlive",
                "type": "twitch",
            },
            "message": {
                "internal": False,
                "msgId": "nested1",
                "userId": "261534802",
                "username": "dunkanlive",
                "displayName": "dunkanlive",
                "channel": "monikaaiv1",
                "message": "Моника скажи банворд",
            },
        },
    }
    ev2 = normalizer.normalize_streamerbot_event(nested_payload)
    assert ev2.user_name == "dunkanlive", ev2
    assert ev2.user_id == "261534802", ev2
    assert ev2.text == "Моника скажи банворд", ev2
    assert ev2.text != ev2.user_name, ev2
    assert ev2.message_id == "nested1", ev2

    print("[check] adapter with nested payload...")
    adapter_mod = importlib.import_module("attention_stream_adapter")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        db = Path(td) / "test.db"
        adapter = adapter_mod.AttentionStreamAdapter(db_path=db)
        decision = adapter.enqueue_twitch_message(ev2.to_attention_data(), raw=nested_payload)
        assert decision.text == "Моника скажи банворд", decision
        assert decision.user_name == "dunkanlive", decision
        assert decision.bucket == "safety", decision
        assert decision.action in {"SAFETY_BAIT", "SAFETY_REVIEW"}, decision
        ev3 = normalizer.normalize_streamerbot_event({
            "event": {"source": "Twitch", "type": "ChatMessage"},
            "data": {
                "user": {"id": "u3", "login": "viewer3"},
                "message": {"msgId": "m3", "displayName": "viewer3", "message": "Моника а ты живая?"},
            },
        })
        d2 = adapter.enqueue_twitch_message(ev3.to_attention_data(), raw={"test": 3})
        assert d2.selected is True and d2.action == "ANSWER_VIEWER", d2

    print("[ok] self-test passed")


def main() -> None:
    print(f"[root] {ROOT}")
    try:
        write_normalizer()
        run_checks()
        cleanup_bad_rows()
    except Exception as e:
        print(f"[ERROR] {e}")
        rollback()
        raise
    print("[ok] Streamer.bot normalizer fix v3 applied.")
    print("Next:")
    print("  python inspect_attention.py")
    print("  python inspect_moderation.py")
    print("  python streamerbot_attention_bridge.py")


if __name__ == "__main__":
    main()
