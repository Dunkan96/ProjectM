# -*- coding: utf-8 -*-
"""Social memory layer for Monika.

This module stores social nicknames, running jokes and light grievances per
person. It is a layer above existing tables:
- user_reputation: activity/authority
- relationship_state: affection/trust/irritation/familiarity

It intentionally does not store factual memory about the world. It only gives
Monika social texture for stream dialogue.
"""
from __future__ import annotations

import random
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any


SAFE_FORBIDDEN_PARTS = {
    "ниг", "хач", "жид", "пидор", "педик", "шлюх", "урод", "инвалид",
    "аутист", "даун", "рас", "наци", "гей", "транс", "чур", "чернож",
}

TECHNICAL_ALIAS_PATTERNS = [
    "попугай", "я чуть", "повторила", "повтор", "заново", "вопрос короче",
]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _clean_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^0-9A-Za-zА-Яа-яЁё_\- ]+", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:32] or "гость"


def _is_safe_alias(alias: str) -> bool:
    text = (alias or "").lower().replace("ё", "е")
    if not text or len(text) > 48:
        return False
    if any(part in text for part in SAFE_FORBIDDEN_PARTS):
        return False
    if any(part in text for part in TECHNICAL_ALIAS_PATTERNS):
        return False
    return True


class SocialMemoryCore:
    """Per-user social texture: aliases, bits and playful grievances."""

    def __init__(self, conn: sqlite3.Connection, creator_id: str = "Duncan"):
        self.conn = conn
        self.creator_id = str(creator_id or "Duncan")
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS social_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                alias TEXT NOT NULL,
                tone TEXT NOT NULL DEFAULT 'playful',
                source TEXT NOT NULL DEFAULT 'generated',
                score REAL DEFAULT 1.0,
                use_count INTEGER DEFAULT 0,
                last_used DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, alias)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS social_bits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                bit_type TEXT NOT NULL,
                text TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                use_count INTEGER DEFAULT 0,
                last_used DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, bit_type, text)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS social_grievances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id TEXT NOT NULL,
                text TEXT NOT NULL,
                severity REAL DEFAULT 0.5,
                active INTEGER DEFAULT 1,
                use_count INTEGER DEFAULT 0,
                last_used DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(person_id, text)
            )
            """
        )
        self.conn.commit()

    def _row_to_dict(self, row: Any) -> dict[str, Any]:
        if row is None:
            return {}
        try:
            return dict(row)
        except Exception:
            return {}

    def _get_user_stats(self, person_id: str) -> dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM user_reputation WHERE user_id = ?", (person_id,))
        return self._row_to_dict(cur.fetchone())

    def _get_relationship(self, person_id: str) -> dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM relationship_state WHERE person_id = ?", (person_id,))
        return self._row_to_dict(cur.fetchone())

    def classify_tone(
        self,
        person_id: str,
        relationship_role: str = "viewer",
        relationship_state: dict[str, Any] | None = None,
    ) -> str:
        state = relationship_state or self._get_relationship(person_id)
        role = (relationship_role or "viewer").lower()
        if role == "creator" or person_id == self.creator_id:
            irritation = float(state.get("irritation", 0.0) or 0.0)
            return "teasing" if irritation < 0.65 else "annoyed"
        affection = float(state.get("affection", 0.0) or 0.0)
        irritation = float(state.get("irritation", 0.0) or 0.0)
        familiarity = float(state.get("familiarity", 0.0) or 0.0)
        friction = float(state.get("friction", 0.0) or 0.0)
        if irritation >= 0.65 or friction >= 0.75:
            return "annoyed"
        if affection >= 0.45 and familiarity >= 0.25:
            return "sweet"
        if familiarity >= 0.3:
            return "teasing"
        return "playful"

    def _base_aliases(self, display_name: str, role: str, tone: str) -> list[str]:
        name = _clean_name(display_name)
        lower = name.lower()
        if role == "creator" or lower in {"duncan", "дункан"}:
            if tone == "annoyed":
                return ["главный балда", "Дунканоид", "тестировщик моей психики"]
            return ["Дунканыч", "Дунканоид", "главный балда", "тестировщик моей психики"]

        short = name[:18]
        if tone == "sweet":
            return [f"{short}ик", f"солнечный {short}", f"{short}-лапочка"]
        if tone == "annoyed":
            return [f"шумный {short}", f"{short}-гремлин", f"колючий {short}"]
        if tone == "teasing":
            return [f"{short}ыч", f"{short}-шалун", f"хитрый {short}"]
        return [short, f"{short} из чата", f"чатовый {short}"]

    def ensure_aliases(self, person_id: str, display_name: str, role: str, tone: str) -> list[str]:
        aliases = [a for a in self._base_aliases(display_name, role, tone) if _is_safe_alias(a)]
        cur = self.conn.cursor()
        for alias in aliases[:4]:
            cur.execute(
                """
                INSERT OR IGNORE INTO social_aliases (person_id, alias, tone, source, score)
                VALUES (?, ?, ?, 'generated', 1.0)
                """,
                (person_id, alias, tone),
            )
        self.conn.commit()
        return aliases[:4]

    def _add_bit(self, person_id: str, bit_type: str, text: str, weight: float = 1.0) -> bool:
        text = (text or "").strip()
        if not text or len(text) > 180:
            return False
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO social_bits (person_id, bit_type, text, weight)
            VALUES (?, ?, ?, ?)
            """,
            (person_id, bit_type, text, float(weight)),
        )
        changed = cur.rowcount > 0
        self.conn.commit()
        return changed

    def _add_grievance(self, person_id: str, text: str, severity: float = 0.45) -> bool:
        text = (text or "").strip()
        if not text or len(text) > 180:
            return False
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO social_grievances (person_id, text, severity, active)
            VALUES (?, ?, ?, 1)
            """,
            (person_id, text, float(severity)),
        )
        changed = cur.rowcount > 0
        self.conn.commit()
        return changed

    def observe_interaction(
        self,
        person_id: str,
        display_name: str,
        relationship_role: str,
        user_text: str,
        relationship_state: dict[str, Any] | None = None,
        sentiment: float | None = None,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        person_id = str(person_id or "viewer")
        display_name = _clean_name(display_name or person_id)
        role = relationship_role or "viewer"
        state = relationship_state or self._get_relationship(person_id)
        tone = self.classify_tone(person_id, role, state)
        aliases = self.ensure_aliases(person_id, display_name, role, tone)

        lowered = (user_text or "").lower().replace("ё", "е")
        added_bits: list[str] = []
        added_grievances: list[str] = []

        if role == "creator" or person_id == self.creator_id:
            if any(tok in lowered for tok in ["тест", "проверя", "почини", "фикс", "опять"]):
                text = "Дункан снова тестирует Монику как лабораторную енотиху"
                if self._add_grievance(person_id, text, 0.35):
                    added_grievances.append(text)
            if any(tok in lowered for tok in ["балда", "дурач", "ну ты", "косяк"]):
                text = "Дункан подкидывает Монике подколы и сам нарывается на ответку"
                if self._add_bit(person_id, "running_gag", text, 0.8):
                    added_bits.append(text)
            if any(tok in lowered for tok in ["хогвард", "хогварт"]):
                text = "Хогвардс — проверочный сон Дункана для памяти Моники"
                if self._add_bit(person_id, "inside_joke", text, 0.7):
                    added_bits.append(text)
        else:
            if any(tok in lowered for tok in ["туп", "дура", "затк", "бесишь", "плохая"]):
                text = f"{display_name} грубит Монике и получает холодный тон"
                if self._add_grievance(person_id, text, 0.75):
                    added_grievances.append(text)
            elif any(tok in lowered for tok in ["круто", "мила", "спасибо", "ахаха", "хаха", "люблю"]):
                text = f"{display_name} хорошо заходит в чатовый вайб"
                if self._add_bit(person_id, "warm_contact", text, 0.65):
                    added_bits.append(text)

        return {
            "person_id": person_id,
            "display_name": display_name,
            "role": role,
            "tone": tone,
            "aliases": aliases,
            "added_bits": added_bits,
            "added_grievances": added_grievances,
        }

    def _recent_aliases(self, person_id: str, tone: str | None = None, limit: int = 4) -> list[str]:
        cur = self.conn.cursor()
        if tone:
            cur.execute(
                """
                SELECT alias FROM social_aliases
                WHERE person_id = ? AND tone IN (?, 'playful', 'teasing')
                ORDER BY score DESC, use_count ASC, id ASC
                LIMIT ?
                """,
                (person_id, tone, int(limit)),
            )
        else:
            cur.execute(
                """
                SELECT alias FROM social_aliases
                WHERE person_id = ?
                ORDER BY score DESC, use_count ASC, id ASC
                LIMIT ?
                """,
                (person_id, int(limit)),
            )
        return [str(row[0] if not hasattr(row, "keys") else row["alias"]) for row in cur.fetchall()]

    def _recent_bits(self, person_id: str, limit: int = 3) -> list[str]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT text FROM social_bits
            WHERE person_id = ?
            ORDER BY weight DESC, use_count ASC, id DESC
            LIMIT ?
            """,
            (person_id, int(limit)),
        )
        return [str(row[0] if not hasattr(row, "keys") else row["text"]) for row in cur.fetchall()]

    def _recent_grievances(self, person_id: str, limit: int = 2) -> list[str]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT text FROM social_grievances
            WHERE person_id = ? AND active = 1
            ORDER BY severity DESC, use_count ASC, id DESC
            LIMIT ?
            """,
            (person_id, int(limit)),
        )
        return [str(row[0] if not hasattr(row, "keys") else row["text"]) for row in cur.fetchall()]

    def build_prompt_block(
        self,
        person_id: str,
        display_name: str,
        relationship_role: str,
        relationship_state: dict[str, Any] | None = None,
    ) -> str:
        person_id = str(person_id or "viewer")
        display_name = _clean_name(display_name or person_id)
        role = relationship_role or "viewer"
        state = relationship_state or self._get_relationship(person_id)
        stats = self._get_user_stats(person_id)
        tone = self.classify_tone(person_id, role, state)
        aliases = self._recent_aliases(person_id, tone=tone, limit=4)
        bits = self._recent_bits(person_id, limit=3)
        grievances = self._recent_grievances(person_id, limit=2)
        familiarity = float(state.get("familiarity", 0.0) or 0.0) if state else 0.0
        irritation = float(state.get("irritation", 0.0) or 0.0) if state else 0.0
        affection = float(state.get("affection", 0.0) or 0.0) if state else 0.0
        total_messages = int(stats.get("total_messages", 0) or 0) if stats else 0
        authority = int(stats.get("authority_level", 0) or 0) if stats else 0

        lines = [
            "[СОЦИАЛЬНАЯ ПАМЯТЬ О СОБЕСЕДНИКЕ]",
            f"- Собеседник: {display_name} ({role}).",
            f"- Социальный тон сейчас: {tone}. affection={affection:.2f}, irritation={irritation:.2f}, familiarity={familiarity:.2f}.",
            f"- Активность в базе: сообщений={total_messages}, authority={authority}.",
        ]
        if aliases:
            lines.append("- Уже известные прозвища/обращения: " + ", ".join(aliases[:4]) + ".")
            lines.append("- Если пользователь просит новые клички/прозвища, НЕ повторяй этот набор как ответ; придумай новые варианты.")
        if bits:
            lines.append("- Внутренние шутки/социальные биты: " + " | ".join(bits[:3]) + ".")
        if grievances:
            lines.append("- Шуточные претензии, если уместен banter: " + " | ".join(grievances[:2]) + ".")
        lines.extend([
            "- Прозвища — приправа, не обязанность: не используй их в каждой реплике.",
            "- Едкие прозвища должны быть безопасными: без дискриминации, внешности, болезней и реальных персональных данных.",
            "- Если сцена серьёзная или пользователь просит память/факт, не превращай ответ в обзывалку.",
        ])
        return "\n".join(lines)

    def inspect_person(self, person_id: str) -> dict[str, Any]:
        person_id = str(person_id or self.creator_id)
        return {
            "user_reputation": self._get_user_stats(person_id),
            "relationship_state": self._get_relationship(person_id),
            "aliases": self._recent_aliases(person_id, limit=20),
            "bits": self._recent_bits(person_id, limit=20),
            "grievances": self._recent_grievances(person_id, limit=20),
        }
