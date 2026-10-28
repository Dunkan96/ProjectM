# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

try:
    from attention_safety_guard import classify_message
except Exception:
    classify_message = None

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "Logs"


@dataclass
class AttentionDecision:
    event_id: str
    source: str
    event_type: str
    user_id: str
    user_name: str
    text: str
    score: float
    bucket: str
    action: str
    reasons: list[str]
    priority: int
    selected: bool
    safe_text: str
    safety_json: dict[str, Any]
    created_ts: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return "{}"


def _now() -> float:
    return time.time()


def _load_config_db_path() -> Path:
    try:
        import config  # type: ignore

        candidates: list[Path] = []
        for name in dir(config):
            upper = name.upper()
            if "DB" not in upper and "DATABASE" not in upper:
                continue
            value = getattr(config, name)
            if isinstance(value, (str, Path)):
                s = str(value)
                if s.lower().endswith(".db"):
                    candidates.append(Path(s))
        for p in candidates:
            pp = p if p.is_absolute() else ROOT / p
            if pp.exists():
                return pp
    except Exception:
        pass

    for name in ("monika_memory.db", "knowledge.db"):
        p = ROOT / name
        if p.exists():
            return p
    return ROOT / "monika_memory.db"


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    try:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if not _table_exists(conn, table):
        return
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _ensure_minimal_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS attention_events (
            event_id TEXT PRIMARY KEY,
            source TEXT,
            event_type TEXT,
            user_id TEXT,
            user_name TEXT,
            text TEXT,
            score REAL,
            bucket TEXT,
            action TEXT,
            reasons TEXT,
            priority INTEGER,
            created_ts REAL,
            raw_json TEXT,
            safe_text TEXT,
            safety_json TEXT
        );

        CREATE TABLE IF NOT EXISTS attention_selected (
            event_id TEXT PRIMARY KEY,
            source TEXT,
            event_type TEXT,
            user_id TEXT,
            user_name TEXT,
            text TEXT,
            score REAL,
            bucket TEXT,
            action TEXT,
            reasons TEXT,
            priority INTEGER,
            created_ts REAL,
            status TEXT DEFAULT 'pending',
            processed_ts REAL,
            safe_text TEXT,
            safety_json TEXT
        );

        CREATE TABLE IF NOT EXISTS attention_digest_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_ts REAL,
            digest TEXT
        );

        CREATE TABLE IF NOT EXISTS attention_viewer_state (
            user_id TEXT PRIMARY KEY,
            user_name TEXT,
            last_seen_ts REAL,
            message_count INTEGER DEFAULT 0,
            selected_count INTEGER DEFAULT 0,
            safety_count INTEGER DEFAULT 0,
            last_message TEXT
        );

        CREATE TABLE IF NOT EXISTS moderation_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_ts REAL,
            event_id TEXT,
            action TEXT,
            status TEXT,
            user_id TEXT,
            user_name TEXT,
            reason TEXT,
            confidence REAL,
            raw_json TEXT
        );
    """)
    for table, specs in {
        "attention_events": {
            "safe_text": "TEXT",
            "safety_json": "TEXT",
            "raw_json": "TEXT",
        },
        "attention_selected": {
            "status": "TEXT DEFAULT 'pending'",
            "processed_ts": "REAL",
            "safe_text": "TEXT",
            "safety_json": "TEXT",
        },
        "attention_viewer_state": {
            "selected_count": "INTEGER DEFAULT 0",
            "safety_count": "INTEGER DEFAULT 0",
            "last_message": "TEXT",
        },
        "moderation_actions": {
            "event_id": "TEXT",
            "confidence": "REAL",
            "raw_json": "TEXT",
        },
    }.items():
        for column, definition in specs.items():
            _add_column_if_missing(conn, table, column, definition)


def _insert_dynamic(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
    if not _table_exists(conn, table):
        return
    cols = _columns(conn, table)
    use_cols = [c for c in cols if c in values]
    if not use_cols:
        return
    placeholders = ",".join(["?"] * len(use_cols))
    col_sql = ",".join(use_cols)
    sql = f"INSERT OR REPLACE INTO {table} ({col_sql}) VALUES ({placeholders})"
    conn.execute(sql, [values[c] for c in use_cols])


class AttentionStreamAdapter:
    def __init__(self, config: dict[str, Any] | None = None, db_path: str | Path | None = None) -> None:
        self.config = config or {}
        self.db_path = Path(db_path) if db_path else _load_config_db_path()
        LOGS.mkdir(exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        _ensure_minimal_schema(conn)
        return conn

    def classify(self, text: str, user_role: Any = None) -> Any:
        if classify_message is None:
            return None
        try:
            return classify_message(text, user_role=user_role, config=self.config)
        except TypeError:
            try:
                return classify_message(text, user_role=user_role)
            except TypeError:
                return classify_message(text)
        except Exception:
            return None

    def _score_message(self, text: str, safety: Any = None) -> tuple[float, str, str, list[str], int, bool, str, dict[str, Any]]:
        reasons: list[str] = []
        safe_text = text
        safety_json: dict[str, Any] = {}

        if safety is not None:
            if hasattr(safety, "to_dict"):
                safety_json = safety.to_dict()
            else:
                safety_json = dict(getattr(safety, "__dict__", {}) or {})
            if safety_json.get("safe_text"):
                safe_text = str(safety_json.get("safe_text"))
            if isinstance(safety_json.get("reasons"), list):
                reasons.extend([str(x) for x in safety_json.get("reasons", [])])

            if safety_json.get("block_send_to_llm"):
                action = str(safety_json.get("action") or "SAFETY_REVIEW")
                risk = str(safety_json.get("risk") or "safety")
                score = float(safety_json.get("score") or 0.95)
                return score, "safety", action, reasons or [risk], 80, False, safe_text, safety_json

            if safety_json.get("action") == "SHORT_REACT":
                return 0.35, "background", "SHORT_REACT", reasons or ["low_content_mention"], 20, False, safe_text, safety_json

        text_l = text.lower()
        mentions_monika = any(x in text_l for x in ("моника", "моник", "monika", "monik", "monica"))
        is_question = "?" in text or any(x in text_l for x in ("кто", "что", "как", "почему", "зачем", "когда", "где"))

        if mentions_monika and is_question:
            return 0.88, "critical", "ANSWER_VIEWER", reasons + ["mentions_monika", "question"], 60, True, safe_text, safety_json
        if mentions_monika:
            return 0.63, "selected", "ANSWER_VIEWER", reasons + ["mentions_monika"], 50, True, safe_text, safety_json
        if is_question:
            return 0.43, "background", "REMEMBER_CONTEXT", reasons + ["question"], 10, False, safe_text, safety_json
        return 0.0, "ignored", "IGNORE", reasons, 0, False, safe_text, safety_json

    def enqueue_twitch_message(self, data: dict[str, Any], raw: dict[str, Any] | None = None) -> AttentionDecision:
        text = str(data.get("text") or data.get("message") or "")
        user_name = str(data.get("user_name") or data.get("displayName") or data.get("username") or data.get("login") or "unknown")
        user_id = str(data.get("user_id") or data.get("userId") or user_name)
        event_type = str(data.get("event_type") or "ChatMessage")
        source = str(data.get("source") or "twitch_chat")
        event_id = str(data.get("event_id") or data.get("msgId") or data.get("messageId") or f"tw_{uuid.uuid4().hex}")

        safety = self.classify(text, user_role=data.get("role"))
        score, bucket, action, reasons, priority, selected, safe_text, safety_json = self._score_message(text, safety)
        created_ts = _now()

        decision = AttentionDecision(
            event_id=event_id,
            source="twitch_chat" if source.lower() in {"twitch", "twitch_chat"} else source,
            event_type=event_type,
            user_id=user_id,
            user_name=user_name,
            text=text,
            score=score,
            bucket=bucket,
            action=action,
            reasons=reasons,
            priority=priority,
            selected=selected,
            safe_text=safe_text,
            safety_json=safety_json,
            created_ts=created_ts,
        )

        self._write_decision(decision, raw or data)
        if bucket == "safety":
            self.record_moderation(decision, raw or data)
        return decision

    def enqueue_creator_event(self, text: str, user_name: str = "Duncan") -> AttentionDecision:
        event_id = f"creator_{uuid.uuid4().hex}"
        decision = AttentionDecision(
            event_id=event_id,
            source="creator_voice",
            event_type="voice",
            user_id=user_name,
            user_name=user_name,
            text=text,
            score=1.0,
            bucket="critical",
            action="ANSWER_CREATOR",
            reasons=["creator"],
            priority=100,
            selected=True,
            safe_text=text,
            safety_json={},
            created_ts=_now(),
        )
        self._write_decision(decision, {"text": text, "user": user_name})
        return decision

    def _write_decision(self, d: AttentionDecision, raw: dict[str, Any]) -> None:
        raw_json = _json(raw)
        reasons_json = _json(d.reasons)
        safety_json_text = _json(d.safety_json)
        values = {
            **d.to_dict(),
            "reasons": reasons_json,
            "raw_json": raw_json,
            "safety_json": safety_json_text,
            "status": "pending",
            "processed_ts": None,
        }

        conn = self.connect()
        try:
            _insert_dynamic(conn, "attention_events", values)
            if d.selected:
                _insert_dynamic(conn, "attention_selected", values)
            self._update_viewer_state(conn, d)
            conn.commit()
        finally:
            conn.close()

        self._append_logs(d)
        self._rebuild_digest_file()

    def _update_viewer_state(self, conn: sqlite3.Connection, d: AttentionDecision) -> None:
        if not _table_exists(conn, "attention_viewer_state"):
            return
        now = _now()
        conn.execute(
            """
            INSERT INTO attention_viewer_state (user_id, user_name, last_seen_ts, message_count, selected_count, safety_count, last_message)
            VALUES (?, ?, ?, 1, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                user_name=excluded.user_name,
                last_seen_ts=excluded.last_seen_ts,
                message_count=COALESCE(attention_viewer_state.message_count, 0) + 1,
                selected_count=COALESCE(attention_viewer_state.selected_count, 0) + ?,
                safety_count=COALESCE(attention_viewer_state.safety_count, 0) + ?,
                last_message=excluded.last_message
            """,
            (
                d.user_id,
                d.user_name,
                now,
                1 if d.selected else 0,
                1 if d.bucket == "safety" else 0,
                d.text,
                1 if d.selected else 0,
                1 if d.bucket == "safety" else 0,
            ),
        )

    def record_moderation(self, d: AttentionDecision, raw: dict[str, Any]) -> None:
        action_map = {
            "SAFETY_BAIT": "review_safety_bait",
            "SAFETY_REVIEW": "review_safety_bait",
            "PROMPT_INJECTION": "review_prompt_injection",
            "MOD_ABUSE": "review_moderation_abuse",
        }
        values = {
            "created_ts": _now(),
            "event_id": d.event_id,
            "action": action_map.get(d.action, "review_safety_bait"),
            "status": "dry_run",
            "user_id": d.user_id,
            "user_name": d.user_name,
            "reason": (d.safety_json or {}).get("risk") or ",".join(d.reasons),
            "confidence": d.score,
            "raw_json": _json(raw),
        }
        conn = self.connect()
        try:
            _insert_dynamic(conn, "moderation_actions", values)
            conn.commit()
        finally:
            conn.close()

    def _append_logs(self, d: AttentionDecision) -> None:
        try:
            with (LOGS / "attention_events.jsonl").open("a", encoding="utf-8") as f:
                f.write(_json(d.to_dict()) + "\n")
            if d.selected:
                with (LOGS / "monika_selected_events.jsonl").open("a", encoding="utf-8") as f:
                    f.write(_json(d.to_dict()) + "\n")
        except Exception:
            pass

    def pending_selected(self, limit: int = 5) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            if not _table_exists(conn, "attention_selected"):
                return []
            cols = _columns(conn, "attention_selected")
            order = "priority DESC, score DESC, created_ts ASC" if "priority" in cols else "created_ts ASC"
            where = "COALESCE(status, 'pending')='pending'" if "status" in cols else "1=1"
            rows = conn.execute(f"SELECT * FROM attention_selected WHERE {where} ORDER BY {order} LIMIT ?", (limit,)).fetchall()
            names = [d[1] for d in conn.execute("PRAGMA table_info(attention_selected)").fetchall()]
            return [dict(zip(names, row)) for row in rows]
        finally:
            conn.close()

    def build_digest(self, limit: int = 5, consume: bool = False) -> str:
        pending = self.pending_selected(limit=limit)
        lines = ["### STREAM ATTENTION"]
        ids: list[str] = []
        for row in pending:
            action = row.get("action", "")
            score = row.get("score", "")
            prio = row.get("priority", "")
            name = row.get("user_name", "")
            text = row.get("safe_text") or row.get("text") or ""
            reasons = row.get("reasons", "")
            ids.append(str(row.get("event_id", "")))
            lines.append(f"- [{action}] score={score} prio={prio} from={name}: {text} ({reasons})")
        digest = "\n".join(lines) if len(lines) > 1 else ""
        if consume and ids:
            self.mark_processed(ids)
        return digest

    def mark_processed(self, event_ids: list[str]) -> None:
        conn = self.connect()
        try:
            if _table_exists(conn, "attention_selected") and "status" in _columns(conn, "attention_selected"):
                conn.executemany(
                    "UPDATE attention_selected SET status='processed', processed_ts=? WHERE event_id=?",
                    [(_now(), eid) for eid in event_ids if eid],
                )
                conn.commit()
        finally:
            conn.close()

    def _rebuild_digest_file(self) -> None:
        digest = self.build_digest(limit=5, consume=False)
        try:
            (LOGS / "monika_attention_digest.txt").write_text(digest, encoding="utf-8")
        except Exception:
            pass
        if digest:
            conn = self.connect()
            try:
                _insert_dynamic(conn, "attention_digest_log", {"created_ts": _now(), "digest": digest})
                conn.commit()
            finally:
                conn.close()
