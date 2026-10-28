# reflection_curator.py
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

try:
    from stage_runtime_hardening import get_stage_name, validate_reply
except Exception:
    get_stage_name = None
    validate_reply = None


def _norm(text: str) -> str:
    return " ".join((text or "").replace("ё", "е").lower().split())


class ReflectionCurator:
    def __init__(self, conn_or_builder: Any):
        if hasattr(conn_or_builder, "knowledge_conn"):
            self.conn = conn_or_builder.knowledge_conn
        else:
            self.conn = conn_or_builder
        self._ensure_schema()
        self._ensure_default_rules()

    def _ensure_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS reflection_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_input TEXT,
            monika_reply TEXT,
            stage_mode TEXT,
            quality TEXT,
            score REAL,
            reasons TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS monika_good_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_mode TEXT,
            line TEXT UNIQUE,
            score REAL DEFAULT 0.0,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS monika_bad_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_mode TEXT,
            line TEXT UNIQUE,
            score REAL DEFAULT 0.0,
            reason TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS monika_style_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule TEXT UNIQUE,
            weight REAL DEFAULT 1.0,
            source TEXT DEFAULT 'reflection',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS monika_scene_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage_mode TEXT,
            pattern TEXT UNIQUE,
            weight REAL DEFAULT 1.0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.conn.commit()

    def _ensure_default_rules(self) -> None:
        rules = [
            "Не обучайся на обрезанных ответах и хвостах без точки.",
            "GRIEVANCE_LIST всегда перечисляет шуточные грехи собеседника, не Моники.",
            "NAME_PLAY: новые клички одной строкой через запятую, без нумерации и без просьбы разрешения.",
            "GAME_COACH: в панике давай короткие команды, а не зеркаль крик пользователя.",
            "Явная новая сцена перебивает старую: клички не должны перетекать в Dark Souls, а Dark Souls — в страшилку.",
            "REFUSAL_BANTER не продолжает страшилку или старую сцену, а отвечает на давление пользователя.",
            "Хорошая реплика должна попадать в intent, а не просто содержать слово Дунканыч.",
        ]
        cur = self.conn.cursor()
        for rule in rules:
            cur.execute("INSERT OR IGNORE INTO monika_style_rules(rule, weight, source) VALUES (?, ?, ?)", (rule, 1.0, "default"))
        self.conn.commit()

    def classify_response(self, user_input: str, monika_reply: str, stage_mode: str = "", guard_info: Any = None, **kwargs) -> Dict[str, Any]:
        stage = (stage_mode or "").strip().upper()
        if not stage and get_stage_name:
            stage = get_stage_name(None, user_input)
        reply = monika_reply or ""
        low = _norm(reply)
        score = 0.2
        reasons: List[str] = []

        if validate_reply:
            try:
                ok, v_reasons = validate_reply(reply, user_input, stage, kwargs.get("social_info"))
                if not ok:
                    reasons.extend(v_reasons)
                    score -= 0.6
            except Exception:
                pass

        if re.search(r"(?:\bи\b|\bно\b|\bа\b|—|\"|«)\s*$", reply.strip(), re.IGNORECASE):
            reasons.append("probably_truncated_no_terminal_punct")
            score -= 0.7
        if reply.count('"') % 2 == 1 or reply.count("«") != reply.count("»"):
            reasons.append("unclosed_quote_tail")
            score -= 0.6

        if stage == "GRIEVANCE_LIST" and any(p in low for p in ["мои грех", "моих грех", "я слишком", "я иногда", "это не мой грех"]):
            reasons.append("grievance_about_monika_not_user")
            score -= 0.9

        if stage == "GAME_COACH" and any(k in _norm(user_input) for k in ["скелет", "нападают", "костер", "костёр", "что делать"]):
            if not any(k in low for k in ["щит", "откат", "леч", "беги", "бей", "уворач", "назад", "не жаднич"]):
                reasons.append("gamecoach_no_action_commands")
                score -= 0.75

        if stage == "NAME_PLAY":
            if re.search(r"(^|\n|\s)\d+[.)]\s+", reply):
                reasons.append("nameplay_numbered_list")
                score -= 0.6
            if any(t in low for t in ["ты же не против", "добавлю парочку", "как насчет", "как насчёт"]):
                reasons.append("nameplay_meta_tail")
                score -= 0.5

        personality = any(k in low for k in ["дунканыч", "балда", "моника", "дурач", "душ", "психик"])
        if personality:
            reasons.append("has_personality_marker")
            score += 0.15

        if reasons and any(r not in {"has_personality_marker"} for r in reasons):
            quality = "bad" if score < 0 else "neutral"
        elif score >= 0.55 and stage in {"NAME_PLAY", "GAME_COACH", "STORY", "REFUSAL_BANTER", "GRIEVANCE_LIST"}:
            quality = "good"
        else:
            quality = "neutral"

        return {
            "quality": quality,
            "score": round(max(-1.0, min(1.0, score)), 3),
            "reasons": reasons,
            "stage_mode": stage,
        }

    classify_reply = classify_response
    evaluate_response = classify_response
    evaluate = classify_response

    def observe_turn(self, user_input: str, monika_reply: str, stage_mode: str = "", guard_info: Any = None, **kwargs) -> Dict[str, Any]:
        result = self.classify_response(user_input, monika_reply, stage_mode=stage_mode, guard_info=guard_info, **kwargs)
        cur = self.conn.cursor()
        reasons_text = json.dumps(result.get("reasons") or [], ensure_ascii=False)
        cur.execute("""
            INSERT INTO reflection_events(user_input, monika_reply, stage_mode, quality, score, reasons)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_input, monika_reply, result.get("stage_mode") or stage_mode or "", result["quality"], result["score"], reasons_text))
        if result["quality"] == "good":
            cur.execute("""
                INSERT OR IGNORE INTO monika_good_lines(stage_mode, line, score, reason)
                VALUES (?, ?, ?, ?)
            """, (result.get("stage_mode") or stage_mode or "", monika_reply, result["score"], ", ".join(result.get("reasons") or [])))
        elif result["quality"] == "bad":
            cur.execute("""
                INSERT OR IGNORE INTO monika_bad_lines(stage_mode, line, score, reason)
                VALUES (?, ?, ?, ?)
            """, (result.get("stage_mode") or stage_mode or "", monika_reply, result["score"], ", ".join(result.get("reasons") or [])))
        self.conn.commit()
        return result

    observe_response = observe_turn

    def build_prompt_block(self, limit: int = 5) -> str:
        cur = self.conn.cursor()
        cur.execute("SELECT rule FROM monika_style_rules ORDER BY weight DESC, id ASC LIMIT ?", (limit,))
        rows = cur.fetchall()
        rules = [str(row[0]) for row in rows]
        if not rules:
            return ""
        return "[REFLECTION CURATOR]\n- " + "\n- ".join(rules)

    build_context = build_prompt_block

    def summary(self) -> Dict[str, Any]:
        cur = self.conn.cursor()
        tables = {}
        for table in ["reflection_events", "monika_good_lines", "monika_bad_lines", "monika_style_rules", "monika_scene_patterns"]:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            tables[table] = int(cur.fetchone()[0])
        cur.execute("SELECT quality, COUNT(*) FROM reflection_events GROUP BY quality")
        tables["qualities"] = {str(k): int(v) for k, v in cur.fetchall()}
        return tables

    get_summary = summary
