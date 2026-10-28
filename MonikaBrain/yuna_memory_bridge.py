
# -*- coding: utf-8 -*-
from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from typing import Any, Iterable, List, Sequence


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_text(text: Any) -> str:
    text = str(text or "")
    text = text.replace("\ufeff", "").replace("\x00", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _norm(text: Any) -> str:
    text = _clean_text(text).lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я_\- ]+", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _short(text: Any, limit: int = 220) -> str:
    text = _clean_text(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def normalize_user_input(text: Any) -> str:
    text = _clean_text(text)
    if not text:
        return ""
    lower = text.lower().replace("ё", "е")
    # frequent keyboard/STT prefix garbage seen in logs: "нЧто ..."
    noisy_prefixes = ("нчто", "nчто", "mчто", "ьчто", "bчто")
    if lower.startswith(noisy_prefixes):
        return text[1:].lstrip()
    if len(text) > 4:
        tail = text[1:].lstrip()
        tail_l = tail.lower().replace("ё", "е")
        if text[0].lower() in {"н", "n", "m", "ь", "b"} and any(
            tail_l.startswith(prefix) for prefix in ("что ", "кто ", "где ", "когда ", "помни", "вспомни")
        ):
            return tail
    return text


def _u(text: Any) -> str:
    return normalize_user_input(text).lower().replace("ё", "е")


_SESSION_RECAP_PATTERNS = (
    "что мы уже тестировали",
    "что мы тестировали",
    "что уже тестировали",
    "что проверяли",
    "что мы проверяли",
    "что мы уже делали",
    "что мы делали",
    "что было в этой сессии",
    "что было сегодня",
    "что сегодня тестировали",
    "что происходило сегодня",
    "что было с кличками",
    "что было с dark souls",
    "что было с дарк соулс",
    "что было с соулс",
    "помнишь что мы тестировали",
    "помнишь что тестировали",
    "помнишь что было",
)


def is_session_recap_query(text: Any) -> bool:
    t = _u(text)
    if not t:
        return False
    if any(p in t for p in _SESSION_RECAP_PATTERNS):
        return True
    if any(x in t for x in ("что было", "что мы", "что уже", "помнишь")) and any(
        x in t for x in ("клич", "dark souls", "дарк соул", "соулс", "скелет", "костер", "костёр", "страшил", "грех")
    ):
        return True
    if ("сегодня" in t or "сесс" in t or "уже" in t) and any(
        p in t for p in ("тестир", "провер", "делал", "происход", "обсуждал")
    ):
        return True
    return False


def infer_stage_from_text(user_input: Any, monika_reply: Any = "") -> str:
    # Recall has priority over keyword modes. This fixes "что было с Dark Souls" -> SESSION_RECAP, not GAME_COACH.
    t = _u(user_input)
    r = _u(monika_reply)
    if is_session_recap_query(t):
        return "SESSION_RECAP"
    if any(x in t for x in ("клич", "прозвищ", "прозвище", "никнейм", "ник ", "зови меня")):
        return "NAME_PLAY"
    if any(x in t for x in ("dark souls", "дарк соул", "скелет", "костер", "костёр", "босс", "щит", "откат", "лечись")):
        return "GAME_COACH"
    if any(x in t for x in ("страшил", "истори", "сценк")):
        return "STORY"
    if "грех" in t:
        return "GRIEVANCE_LIST"
    if any(x in t for x in ("искусственный интеллект", "выполняй", "задачи", "робот")):
        return "REFUSAL_BANTER"
    if "привет" in t:
        return "GREETING"
    if any(x in r for x in ("щит", "откат", "лечись")):
        return "GAME_COACH"
    return ""


def summarize_turn(user_input: Any, monika_reply: Any = "", stage_mode: Any = "") -> str:
    stage = str(stage_mode or infer_stage_from_text(user_input, monika_reply)).upper()
    t = _u(user_input)
    if stage == "SESSION_RECAP":
        return "проверяли, помнит ли Моника ход текущей сессии"
    if stage == "GREETING":
        return "поздоровались и проверили живой teasing-тон"
    if stage == "GRIEVANCE_LIST":
        return "тестировали список шуточных грехов Дункана"
    if stage == "NAME_PLAY":
        return "придумывали новые клички для Дункана"
    if stage == "GAME_COACH":
        return "тестировали режим игрового тренера для Dark Souls"
    if stage == "STORY":
        return "тестировали страшилку/мини-сценку про компьютер и Монику"
    if stage == "REFUSAL_BANTER":
        return "тестировали отказ от сухого режима «просто выполняй задачи»"
    if "мозг" in t or "личност" in t or "стрим" in t:
        return "обсуждали развитие мозга Моники для стримов"
    if "привет" in t:
        return "поздоровались"
    return ""


def _unique_keep_order(items: Iterable[str], limit: int = 6) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        item = _clean_text(item)
        if not item:
            continue
        key = _norm(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _clean_markdown_damage(reply: Any, stage_mode: str = "") -> str:
    text = _clean_text(reply)
    if not text:
        return ""
    # Preserve the words inside bold markdown instead of deleting them.
    text = re.sub(r"\*\*([^*]{1,120})\*\*", r"\1", text)
    text = text.replace("**", "")
    text = re.sub(r"\s+([,.!?…])", r"\1", text)
    if str(stage_mode or "").upper() == "GAME_COACH":
        # Repair known damaged postprocess artifact: "и **!" -> "и не жадничай!"
        text = re.sub(r"\bи\s*[!！]", "и не жадничай!", text)
        text = text.replace("— и!", "— и не жадничай!")
    return text.strip()


class YunaMemoryBridge:
    MEMORY_MARKERS = (
        "помнишь", "вспомни", "что мы делали", "что уже", "когда",
        "кто", "с кем", "какие были", "что было", "история", "таймлайн",
        "timeline", "стрим", "стримы", "коллаб", "коллабы", "сегодня", "сессии",
    )

    ASSOCIATIONS = [
        ("хогвард", "можно мягко вспомнить сон про Хогвардс, только если это прямо уместно"),
        ("пицц", "можно поддеть темой пиццы, но не тащить её без повода"),
        ("броккол", "можно выразить личный вкус, но не выдавать опыт за факт"),
        ("dark souls", "режим тренера: короткие команды, азарт и подкол"),
        ("дарк соул", "режим тренера: короткие команды, азарт и подкол"),
        ("скелет", "режим паники-тренера: щит, откат, лечись, бей одного"),
        ("клич", "клички должны быть новыми, коротко через запятую"),
        ("грех", "список грехов — это шуточные грехи собеседника, не Моники"),
    ]

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        try:
            self.conn.row_factory = sqlite3.Row
        except Exception:
            pass
        self._init_tables()

    def _table_columns(self, table: str) -> list[str]:
        try:
            cur = self.conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            return [str(row[1]) for row in cur.fetchall()]
        except Exception:
            return []

    def _ensure_column(self, table: str, col: str, decl: str) -> None:
        if col not in self._table_columns(table):
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
                self.conn.commit()
            except sqlite3.OperationalError:
                pass

    def _init_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS person_alias_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                alias_norm TEXT,
                person_id TEXT NOT NULL,
                display_name TEXT,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'manual',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_used_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS yuna_bridge_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT DEFAULT CURRENT_TIMESTAMP,
                person_id TEXT DEFAULT 'Duncan',
                display_name TEXT,
                stage_mode TEXT,
                user_input TEXT,
                monika_reply TEXT,
                summary TEXT,
                tags_json TEXT DEFAULT '{}'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS yuna_bridge_assoc_cooldown (
                key TEXT PRIMARY KEY,
                last_used_at TEXT,
                use_count INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()
        # Migrate older versions created by previous patches.
        for col, decl in [
            ("alias_norm", "TEXT"),
            ("display_name", "TEXT"),
            ("last_used_at", "TEXT"),
        ]:
            self._ensure_column("person_alias_map", col, decl)
        for col, decl in [
            ("ts", "TEXT DEFAULT CURRENT_TIMESTAMP"),
            ("person_id", "TEXT DEFAULT 'Duncan'"),
            ("display_name", "TEXT"),
            ("stage_mode", "TEXT"),
            ("user_input", "TEXT"),
            ("monika_reply", "TEXT"),
            ("summary", "TEXT"),
            ("tags_json", "TEXT DEFAULT '{}'"),
        ]:
            self._ensure_column("yuna_bridge_turns", col, decl)
        try:
            cur.execute("SELECT id, alias FROM person_alias_map WHERE alias_norm IS NULL OR alias_norm = ''")
            for row in cur.fetchall():
                cur.execute("UPDATE person_alias_map SET alias_norm = ? WHERE id = ?", (_norm(row[1]), row[0]))
            self.conn.commit()
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_person_alias_norm ON person_alias_map(alias_norm)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_yuna_bridge_turns_id ON yuna_bridge_turns(id)")
            self.conn.commit()
        except Exception:
            pass
        self.seed_default_aliases()

    def seed_default_aliases(self) -> None:
        for alias in [
            "Duncan", "Дункан", "Дунканыч", "Дунканоид",
            "главный балда", "тестировщик моей психики",
            "Кнопочный барон", "Стримовый ведьмак", "Хаос-дирижёр", "Босс тестов",
        ]:
            self.add_alias(alias, "Duncan", display_name="Дункан", source="seed", confidence=1.0)

    def add_alias(self, alias: Any, person_id: Any, display_name: Any = None, source: str = "manual", confidence: float = 1.0) -> None:
        alias = _clean_text(alias)
        person_id = _clean_text(person_id) or alias
        display_name = _clean_text(display_name) or person_id
        alias_norm = _norm(alias)
        if not alias or not alias_norm or not person_id:
            return
        cur = self.conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO person_alias_map(alias, alias_norm, person_id, display_name, confidence, source, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alias) DO UPDATE SET
                    alias_norm=excluded.alias_norm,
                    person_id=excluded.person_id,
                    display_name=COALESCE(excluded.display_name, person_alias_map.display_name),
                    confidence=MAX(person_alias_map.confidence, excluded.confidence),
                    last_used_at=excluded.last_used_at
                """,
                (alias, alias_norm, person_id, display_name, float(confidence), source, _now(), _now()),
            )
        except sqlite3.OperationalError:
            cur.execute(
                "INSERT OR IGNORE INTO person_alias_map(alias, person_id, confidence, source, created_at, last_used_at) VALUES (?, ?, ?, ?, ?, ?)",
                (alias, person_id, float(confidence), source, _now(), _now()),
            )
            try:
                cur.execute("UPDATE person_alias_map SET alias_norm=?, display_name=?, last_used_at=? WHERE alias=?", (alias_norm, display_name, _now(), alias))
            except Exception:
                pass
        self.conn.commit()

    def resolve_person(self, person_id: Any = "", display_name: Any = None) -> tuple[str, str]:
        raw_id = _clean_text(person_id)
        raw_display = _clean_text(display_name) or raw_id or "viewer"
        candidates = [raw_id, raw_display]
        cur = self.conn.cursor()
        for item in candidates:
            n = _norm(item)
            if not n:
                continue
            try:
                cur.execute("SELECT person_id, display_name FROM person_alias_map WHERE alias_norm = ? OR LOWER(alias) = LOWER(?) LIMIT 1", (n, item))
                row = cur.fetchone()
            except Exception:
                row = None
            if row:
                canonical = str(row[0] or raw_id or "viewer")
                shown = str(row[1] or canonical)
                try:
                    cur.execute("UPDATE person_alias_map SET last_used_at = ? WHERE alias_norm = ?", (_now(), n))
                    self.conn.commit()
                except Exception:
                    pass
                return canonical, shown
        if raw_id and raw_id not in {"__scene__", "scene"}:
            self.add_alias(raw_id, raw_id, raw_display, source="seen_exact", confidence=0.75)
        return raw_id or "viewer", raw_display or raw_id or "viewer"

    def _fetch_bridge_summaries(self, person_id: str = "Duncan", limit: int = 8) -> List[str]:
        cur = self.conn.cursor()
        try:
            cur.execute(
                "SELECT user_input, monika_reply, stage_mode, summary FROM yuna_bridge_turns ORDER BY id DESC LIMIT ?",
                (int(limit) * 2,),
            )
            rows = cur.fetchall()
        except Exception:
            return []
        items: List[str] = []
        for row in reversed(rows):
            try:
                summary = _clean_text(row[3])
                user_input = row[0] or ""
                monika_reply = row[1] or ""
                stage = row[2] or ""
            except Exception:
                summary, user_input, monika_reply, stage = "", "", "", ""
            items.append(summary or summarize_turn(user_input, monika_reply, stage))
        return _unique_keep_order(items, limit=limit)

    def _fetch_reflection_summaries(self, limit: int = 8) -> List[str]:
        cols = self._table_columns("reflection_events")
        if not cols:
            return []
        user_col = "user_input" if "user_input" in cols else ("user_message" if "user_message" in cols else None)
        reply_col = "monika_reply" if "monika_reply" in cols else ("reply" if "reply" in cols else None)
        stage_col = "stage_mode" if "stage_mode" in cols else ("stage" if "stage" in cols else None)
        order_col = "id" if "id" in cols else ("timestamp" if "timestamp" in cols else "rowid")
        if not user_col:
            return []
        select_reply = reply_col or "''"
        select_stage = stage_col or "''"
        try:
            cur = self.conn.cursor()
            cur.execute(
                f"SELECT {user_col} as user_input, {select_reply} as monika_reply, {select_stage} as stage_mode FROM reflection_events ORDER BY {order_col} DESC LIMIT ?",
                (int(limit),),
            )
            rows = cur.fetchall()
        except Exception:
            return []
        items: List[str] = []
        for row in reversed(rows):
            try:
                items.append(summarize_turn(row[0] or "", row[1] or "", row[2] or ""))
            except Exception:
                pass
        return _unique_keep_order(items, limit=limit)

    def _fetch_chat_history_summaries(self, limit: int = 8) -> List[str]:
        cols = self._table_columns("chat_history")
        if not cols:
            return []
        role_col = "role" if "role" in cols else ("speaker" if "speaker" in cols else None)
        msg_col = "message" if "message" in cols else ("content" if "content" in cols else ("text" if "text" in cols else None))
        order_col = "id" if "id" in cols else ("timestamp" if "timestamp" in cols else "rowid")
        if not msg_col:
            return []
        try:
            cur = self.conn.cursor()
            if role_col:
                cur.execute(f"SELECT {role_col}, {msg_col} FROM chat_history ORDER BY {order_col} DESC LIMIT ?", (int(limit) * 3,))
            else:
                cur.execute(f"SELECT '', {msg_col} FROM chat_history ORDER BY {order_col} DESC LIMIT ?", (int(limit) * 3,))
            rows = cur.fetchall()
        except Exception:
            return []
        items: List[str] = []
        for row in reversed(rows):
            role = _norm(row[0])
            msg = _clean_text(row[1])
            if role and role not in {"user", "human", "дuncan", "duncan"}:
                continue
            s = summarize_turn(msg, "", "")
            if s:
                items.append(s)
        return _unique_keep_order(items, limit=limit)

    def get_session_recap_evidence(self, person_id: str = "Duncan", limit: int = 6) -> List[str]:
        items: List[str] = []
        items.extend(self._fetch_bridge_summaries(person_id=person_id, limit=limit))
        items.extend(self._fetch_reflection_summaries(limit=limit))
        items.extend(self._fetch_chat_history_summaries(limit=limit))
        items = _unique_keep_order(items, limit=limit)
        if not items:
            items = ["пока только начали текущий диалог"]
        return items[:limit]

    def build_session_recap_answer(self, person_id: str = "Duncan", limit: int = 5) -> str:
        items = self.get_session_recap_evidence(person_id=person_id, limit=limit)
        if not items or (len(items) == 1 and "пока только" in items[0]):
            return "Пока вижу только старт текущей сессии: мы поздоровались и проверяем, держу ли я нить. Не разгоняйся, балда, я только проснулась."
        return "Сегодня уже: " + "; ".join(items[:limit]) + ". Я держу нить, не паникуй, балда."

    def observe_turn(self, user_input: Any = "", monika_reply: Any = "", person_id: Any = "Duncan", display_name: Any = None, stage_mode: Any = None, **kwargs: Any) -> None:
        try:
            if not user_input:
                user_input = kwargs.get("user_message") or kwargs.get("input") or ""
            if not monika_reply:
                monika_reply = kwargs.get("reply") or ""
            person_id, display_name = self.resolve_person(person_id, display_name or person_id)
            stage = str(stage_mode or kwargs.get("stage") or infer_stage_from_text(user_input, monika_reply)).upper()
            summary = summarize_turn(user_input, monika_reply, stage)
            cur = self.conn.cursor()
            cur.execute(
                """
                INSERT INTO yuna_bridge_turns(ts, person_id, display_name, stage_mode, user_input, monika_reply, summary)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_now(), person_id, display_name, stage, _short(user_input, 500), _short(monika_reply, 700), summary),
            )
            self.conn.commit()
        except Exception:
            try:
                self.conn.rollback()
            except Exception:
                pass

    def _reply_uses_evidence(self, reply: str, evidence: Sequence[str]) -> bool:
        r = _u(reply)
        if not r:
            return False
        if any(x in r for x in ("котик", "котиков", "мемы от серьезных тем", "уровень ехидства выше среднего")):
            return False
        strong = ["клич", "dark souls", "дарк соулс", "скелет", "костер", "костёр", "страшил", "грех", "тест", "поздоров", "сесс", "мозг", "стрим", "тренер", "компьютер", "отказ", "выполняй"]
        if any(token in r for token in strong):
            return True
        for item in evidence:
            words = [w for w in re.findall(r"[а-яa-z0-9]{5,}", _u(item)) if w not in {"сегодня", "тестировали", "проверяли"}]
            if any(w in r for w in words[:3]):
                return True
        return False

    def repair_reply(self, *args: Any, **kwargs: Any) -> str:
        user_input = kwargs.get("user_input") or kwargs.get("user_message") or ""
        monika_reply = kwargs.get("monika_reply") or kwargs.get("reply") or ""
        stage_mode = str(kwargs.get("stage_mode") or kwargs.get("stage") or "").upper()
        person_id = kwargs.get("person_id") or kwargs.get("social_person_id") or "Duncan"
        if args:
            if len(args) >= 1 and not user_input:
                user_input = args[0]
            if len(args) >= 2 and not monika_reply:
                monika_reply = args[1]
            if len(args) >= 3 and not stage_mode:
                stage_mode = str(args[2] or "").upper()
        user_input = normalize_user_input(user_input)
        inferred = infer_stage_from_text(user_input, monika_reply).upper()
        stage_for_clean = inferred or stage_mode
        monika_reply = _clean_markdown_damage(monika_reply, stage_for_clean)
        # Hard deterministic recall. This is intentional: recap is evidence-bound, not creative.
        if is_session_recap_query(user_input) or inferred == "SESSION_RECAP":
            return self.build_session_recap_answer(person_id=str(person_id or "Duncan"), limit=5)
        return monika_reply

    def build_prompt_block(self, *args: Any, **kwargs: Any) -> str:
        user_input = kwargs.get("user_input") or kwargs.get("user_message") or ""
        stage_mode = str(kwargs.get("stage_mode") or kwargs.get("stage") or "").upper()
        person_id = kwargs.get("person_id") or kwargs.get("social_person_id") or "Duncan"
        display_name = kwargs.get("display_name") or kwargs.get("social_display_name") or person_id
        # Older integration may call build_prompt_block(user_input, person_id, display_name, role, history, stage_mode)
        if args:
            if len(args) >= 1 and not user_input:
                user_input = args[0]
            if len(args) >= 2:
                person_id = args[1] or person_id
            if len(args) >= 3:
                display_name = args[2] or display_name
            if len(args) >= 6 and not stage_mode:
                stage_mode = str(args[5] or "").upper()
        user_input = normalize_user_input(user_input)
        person_id, display_name = self.resolve_person(person_id, display_name)
        inferred = infer_stage_from_text(user_input, "").upper()
        # Recall wins over wrong keyword stage.
        if inferred == "SESSION_RECAP":
            stage_mode = "SESSION_RECAP"
        elif not stage_mode:
            stage_mode = inferred
        parts: List[str] = ["[YUNA MEMORY BRIDGE]"]
        if stage_mode == "SESSION_RECAP" or is_session_recap_query(user_input):
            evidence = self.get_session_recap_evidence(person_id=person_id, limit=5)
            parts.append("- Текущий запрос просит вспомнить ход этой сессии/сегодняшних тестов.")
            parts.append("- Отвечай только по evidence ниже. Не выдумывай котиков, мемы или события, которых нет.")
            parts.append("- Если evidence мало, честно скажи, что пока видишь только начало сессии.")
            parts.append("[SESSION RECAP EVIDENCE]")
            for item in evidence:
                parts.append(f"- {item}")
        else:
            recent = self.get_session_recap_evidence(person_id=person_id, limit=3)
            if recent:
                parts.append("- Короткий ход текущей сессии, не пересказывай без просьбы:")
                for item in recent[:3]:
                    parts.append(f"- {item}")
            try:
                cur = self.conn.cursor()
                cur.execute("SELECT alias FROM person_alias_map WHERE person_id = ? ORDER BY confidence DESC, last_used_at DESC LIMIT 6", (person_id,))
                aliases = [str(r[0]) for r in cur.fetchall() if r and r[0]]
                if aliases:
                    parts.append(f"- canonical person_id: {person_id}; обращения: {', '.join(dict.fromkeys(aliases))}")
            except Exception:
                pass
            parts.append("- Используй этот блок мягко: он для ориентации, не для навязывания старых тем.")
        return "\n".join(parts)

    def inspect(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        cur = self.conn.cursor()
        for table in ("person_alias_map", "yuna_bridge_turns", "yuna_bridge_assoc_cooldown"):
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                out[table] = cur.fetchone()[0]
            except Exception as exc:
                out[table] = f"ERROR {exc}"
        out["recent_evidence"] = self.get_session_recap_evidence(limit=6)
        try:
            pid, name = self.resolve_person("Дунканоид", "Дунканоид")
            out["resolve_test"] = {"Дунканоид": [pid, name]}
        except Exception as exc:
            out["resolve_test"] = f"ERROR {exc}"
        return out


# --- Autonomous Memory Governor integration v1d ---
# This block intentionally wraps YunaMemoryBridge instead of editing console_chat.py.
# It prevents indentation/anchor failures and keeps all autonomous memory operations audited and soft-statused.
try:
    from autonomous_memory import AutonomousMemoryGovernor as _AMG_AutonomousMemoryGovernor
except Exception as _amg_import_error:  # pragma: no cover
    _AMG_AutonomousMemoryGovernor = None

if _AMG_AutonomousMemoryGovernor is not None and "YunaMemoryBridge" in globals():
    if not getattr(YunaMemoryBridge, "_autonomous_memory_v1d_installed", False):
        _amg_orig_init = getattr(YunaMemoryBridge, "__init__", None)
        _amg_orig_build_prompt_block = getattr(YunaMemoryBridge, "build_prompt_block", None)
        _amg_orig_observe_turn = getattr(YunaMemoryBridge, "observe_turn", None)
        _amg_orig_repair_reply = getattr(YunaMemoryBridge, "repair_reply", None)
        _amg_orig_resolve_person = getattr(YunaMemoryBridge, "resolve_person", None)

        def _amg_get_person_id(args, kwargs, default="Duncan"):
            for key in ("person_id", "social_person_id", "user_id"):
                if key in kwargs and kwargs[key]:
                    return kwargs[key]
            # common calling patterns: user_input, reply, stage_mode, person_id
            for value in reversed(args or ()):  # look from the end for an ID-like string
                if isinstance(value, str) and value and len(value) <= 64 and " " not in value:
                    if value not in ("REACT", "NAME_PLAY", "GAME_COACH", "STORY", "GRIEVANCE_LIST", "REFUSAL_BANTER"):
                        return value
            return default

        def _amg_extract_arg(args, kwargs, names, index, default=""):
            for name in names:
                if name in kwargs and kwargs[name] is not None:
                    return kwargs[name]
            if args and len(args) > index:
                return args[index]
            return default

        def _amg_ensure(self):
            gov = getattr(self, "autonomous_memory", None)
            if gov is not None:
                return gov
            conn = getattr(self, "conn", None) or getattr(self, "knowledge_conn", None) or getattr(self, "db", None)
            if conn is None:
                conn = getattr(self, "_amg_conn", None)
            if conn is None:
                return None
            try:
                gov = _AMG_AutonomousMemoryGovernor(conn)
                self.autonomous_memory = gov
                return gov
            except Exception:
                return None

        def _amg_init(self, *args, **kwargs):
            if _amg_orig_init is not None:
                _amg_orig_init(self, *args, **kwargs)
            conn = args[0] if args else kwargs.get("conn") or kwargs.get("knowledge_conn") or kwargs.get("db")
            if conn is not None:
                self._amg_conn = conn
                try:
                    self.autonomous_memory = _AMG_AutonomousMemoryGovernor(conn)
                except Exception:
                    self.autonomous_memory = None

        def _amg_build_prompt_block(self, *args, **kwargs):
            base = ""
            if _amg_orig_build_prompt_block is not None:
                try:
                    base = _amg_orig_build_prompt_block(self, *args, **kwargs) or ""
                except Exception as e:
                    base = f"[YUNA_CONTEXT_ERROR] {e}"
            gov = _amg_ensure(self)
            if gov is None:
                return base
            try:
                user_input = _amg_extract_arg(args, kwargs, ("user_input", "text", "query"), 0, "")
                stage_mode = _amg_extract_arg(args, kwargs, ("stage_mode", "stage"), 1, "")
                person_id = _amg_get_person_id(args, kwargs)
                block = gov.build_prompt_block(user_input=user_input, stage_mode=stage_mode, person_id=person_id)
                if block:
                    return (base + "\n\n" + block).strip() if base else block
            except Exception as e:
                err = f"[AUTONOMOUS_MEMORY_CONTEXT_ERROR] {e}"
                return (base + "\n" + err).strip() if base else err
            return base

        def _amg_observe_turn(self, *args, **kwargs):
            result = None
            if _amg_orig_observe_turn is not None:
                try:
                    result = _amg_orig_observe_turn(self, *args, **kwargs)
                except Exception:
                    result = None
            gov = _amg_ensure(self)
            if gov is not None:
                try:
                    user_input = _amg_extract_arg(args, kwargs, ("user_input", "text", "user_text"), 0, "")
                    monika_reply = _amg_extract_arg(args, kwargs, ("monika_reply", "assistant_reply", "reply"), 1, "")
                    stage_mode = _amg_extract_arg(args, kwargs, ("stage_mode", "stage"), 2, "")
                    person_id = _amg_get_person_id(args, kwargs)
                    display_name = kwargs.get("display_name", "")
                    amg_result = gov.observe_turn(user_input=user_input, monika_reply=monika_reply, stage_mode=stage_mode, person_id=person_id, display_name=display_name)
                    if isinstance(result, dict):
                        result["autonomous_memory"] = amg_result
                    elif result is None:
                        result = {"autonomous_memory": amg_result}
                except Exception as e:
                    if isinstance(result, dict):
                        result["autonomous_memory_error"] = str(e)
                    elif result is None:
                        result = {"autonomous_memory_error": str(e)}
            return result

        def _amg_repair_reply(self, *args, **kwargs):
            reply = None
            if _amg_orig_repair_reply is not None:
                try:
                    reply = _amg_orig_repair_reply(self, *args, **kwargs)
                except Exception:
                    reply = None
            if reply is None:
                reply = _amg_extract_arg(args, kwargs, ("monika_reply", "assistant_reply", "reply"), 1, "")
            gov = _amg_ensure(self)
            if gov is None:
                return reply
            try:
                user_input = _amg_extract_arg(args, kwargs, ("user_input", "text", "user_text"), 0, "")
                stage_mode = _amg_extract_arg(args, kwargs, ("stage_mode", "stage"), 2, "")
                person_id = _amg_get_person_id(args, kwargs)
                return gov.repair_reply(user_input=user_input, monika_reply=reply, stage_mode=stage_mode, person_id=person_id)
            except Exception:
                return reply

        def _amg_resolve_person(self, alias=None, *args, **kwargs):
            if _amg_orig_resolve_person is not None:
                try:
                    return _amg_orig_resolve_person(self, alias, *args, **kwargs)
                except Exception:
                    pass
            text = str(alias or kwargs.get("display_name") or kwargs.get("person_id") or "Duncan").strip()
            lowered = text.lower().replace("ё", "е")
            if lowered in {"duncan", "дункан", "дунканыч", "дунканоид", "главный балда", "тестировщик моей психики"}:
                return {"person_id": "Duncan", "display_name": "Дункан", "confidence": 1.0, "source": "autonomous_alias"}
            return {"person_id": text or "Duncan", "display_name": text or "Дункан", "confidence": 0.6, "source": "passthrough"}

        YunaMemoryBridge.__init__ = _amg_init
        YunaMemoryBridge.build_prompt_block = _amg_build_prompt_block
        YunaMemoryBridge.observe_turn = _amg_observe_turn
        YunaMemoryBridge.repair_reply = _amg_repair_reply
        YunaMemoryBridge.resolve_person = _amg_resolve_person
        YunaMemoryBridge._autonomous_memory_v1d_installed = True
# --- /Autonomous Memory Governor integration v1d ---

