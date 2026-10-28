from __future__ import annotations

import re
import sqlite3
from typing import Any, Dict, List, Optional


class DesireMemory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_table()
        self.target_map = {
            "пицца": {"target": "пицца", "category": "food", "desire_type": "want_to_try"},
            "суши": {"target": "суши", "category": "food", "desire_type": "want_to_try"},
            "шаурм": {"target": "шаурма", "category": "food", "desire_type": "want_to_try"},
            "энергет": {"target": "энергетик", "category": "food", "desire_type": "want_to_try"},
            "dark souls": {"target": "Dark Souls", "category": "games", "desire_type": "want_to_try"},
            "elden ring": {"target": "Elden Ring", "category": "games", "desire_type": "want_to_try"},
            "bloodborne": {"target": "Bloodborne", "category": "games", "desire_type": "want_to_try"},
            "аниме": {"target": "аниме", "category": "media", "desire_type": "want_to_explore"},
            "стрим": {"target": "стримовый хаос", "category": "stream", "desire_type": "want_to_continue"},
            "чат": {"target": "живой чат", "category": "stream", "desire_type": "want_to_continue"},
            "мем": {"target": "странные мемы", "category": "internet", "desire_type": "want_to_explore"},
        }

    def _init_table(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS monika_desires (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT NOT NULL,
                category TEXT,
                desire_type TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                intensity REAL DEFAULT 0.35,
                interest REAL DEFAULT 0.35,
                times_mentioned INTEGER DEFAULT 0,
                positive_hits INTEGER DEFAULT 0,
                negative_hits INTEGER DEFAULT 0,
                source TEXT,
                note TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(target, desire_type)
            )
            """
        )
        self.conn.commit()

    def observe_user_message(self, text: str, source: str = "user_described") -> List[Dict[str, Any]]:
        return self._observe_text(text, source=source, speaker="user")

    def observe_monika_reply(self, user_text: str, reply_text: str) -> List[Dict[str, Any]]:
        """Do not let generated text create desires by accident.

        A reply that merely mentions pizza/memes/Dark Souls must not reinforce
        those desires forever. We learn from Monika's reply only when the user
        was already talking about that target, or when Monika explicitly says
        she wants to try/continue it.
        """
        reply_lower = (reply_text or "").lower().replace("ё", "е")
        user_targets = {item["target"].lower() for item in self._extract_targets((user_text or "").lower().replace("ё", "е"))}
        explicit_self_desire = any(token in reply_lower for token in [
            "я хочу", "мне хочется", "я бы хотела", "хочу попробовать",
            "хочу пройти", "мне интересно попробовать", "меня тянет",
        ])
        targets = self._extract_targets(reply_lower)
        updates: List[Dict[str, Any]] = []
        for item in targets:
            target_key = item["target"].lower()
            if target_key not in user_targets and not explicit_self_desire:
                continue
            note = self._build_note(item["target"], reply_lower, positive=True, vivid=False, negative=False)
            self._reinforce_target(
                target=item["target"],
                category=item["category"],
                desire_type=item["desire_type"],
                delta_intensity=0.04 if explicit_self_desire else 0.02,
                delta_interest=0.05 if explicit_self_desire else 0.02,
                positive=True,
                source="self_formed",
                note=note,
            )
            updates.append({**item, "note": note})
        return updates

    def decay_old_desires(self) -> None:
        cursor = self.conn.cursor()
        # Decay по времени: 6 часов вместо 2 дней
        cursor.execute(
            """
            UPDATE monika_desires
            SET
                intensity = CASE
                    WHEN intensity > 0.15 THEN intensity - 0.015
                    ELSE intensity
                END,
                interest = CASE
                    WHEN interest > 0.15 THEN interest - 0.01
                    ELSE interest
                END,
                status = CASE
                    WHEN interest <= 0.18 OR intensity <= 0.12 THEN 'fading'
                    ELSE status
                END
            WHERE julianday('now') - julianday(last_seen) > 0.25
            """
        )
        # Быстрый decay при частом упоминании (>15 раз)
        cursor.execute(
            """
            UPDATE monika_desires
            SET
                intensity = MAX(0.0, intensity - 0.05),
                interest = MAX(0.0, interest - 0.08),
                status = CASE
                    WHEN interest <= 0.12 OR intensity <= 0.1 THEN 'fading'
                    ELSE status
                END
            WHERE times_mentioned >= 15
              AND status = 'active'
            """
        )
        cursor.execute(
            """
            UPDATE monika_desires
            SET status = 'dormant'
            WHERE (interest <= 0.1 OR intensity <= 0.08)
              AND status != 'dormant'
            """
        )
        self.conn.commit()

    def get_active_desires(self, limit: int = 4) -> List[Dict[str, Any]]:
        self.decay_old_desires()
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT target, category, desire_type, status, intensity, interest, source, note,
                   times_mentioned, positive_hits, negative_hits
            FROM monika_desires
            WHERE status IN ('active', 'fading')
            ORDER BY
                CASE status WHEN 'active' THEN 0 ELSE 1 END,
                (intensity + interest) DESC,
                positive_hits DESC,
                times_mentioned DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_relevant_desires(self, text: str = "", limit: int = 3, include_soft_fallback: bool = False) -> List[Dict[str, Any]]:
        active = self.get_active_desires(limit=12)
        text_lower = (text or "").lower().replace("ё", "е")
        if not active:
            return []
        if not text_lower.strip():
            return active[:limit] if include_soft_fallback else []

        category = self._detect_text_category(text_lower)
        scored: List[tuple[float, Dict[str, Any]]] = []
        for item in active:
            score = self._desire_relevance_score(item, text_lower, category)
            if score > 0:
                scored.append((score, item))

        scored.sort(
            key=lambda pair: (
                pair[0],
                float(pair[1].get("interest", 0.0) or 0.0) + float(pair[1].get("intensity", 0.0) or 0.0),
            ),
            reverse=True,
        )
        if scored:
            return [item for _, item in scored[:limit]]
        if include_soft_fallback and len(text_lower) <= 28:
            return active[: min(1, limit)]
        return []

    def get_relevant_desires(self, text: str = "", limit: int = 3, include_soft_fallback: bool = False) -> List[Dict[str, Any]]:
        active = self.get_active_desires(limit=12)
        text_lower = (text or "").lower().replace("ё", "е")
        if not active:
            return []
        if not text_lower.strip():
            return active[:limit] if include_soft_fallback else []

        category = self._detect_text_category(text_lower)
        fatigue_tokens = ["хватит", "отстань", "не про", "другая тема", "надоело", "сменим тему", "забудь"]
        scored: List[tuple[float, Dict[str, Any]]] = []
        for item in active:
            target = str(item.get("target", "") or "").lower().replace("ё", "е")
            mentioned = int(item.get("times_mentioned", 0) or 0)
            if mentioned >= 10 and target and target not in text_lower:
                continue
            if target and target in text_lower and any(token in text_lower for token in fatigue_tokens):
                continue
            score = self._desire_relevance_score(item, text_lower, category)
            if mentioned >= 6 and target and target not in text_lower:
                score -= 0.8
            if score > 0:
                scored.append((score, item))

        scored.sort(
            key=lambda pair: (
                pair[0],
                float(pair[1].get("interest", 0.0) or 0.0) + float(pair[1].get("intensity", 0.0) or 0.0),
            ),
            reverse=True,
        )
        if scored:
            return [item for _, item in scored[:limit]]
        if include_soft_fallback and len(text_lower) <= 28:
            return active[: min(1, limit)]
        return []

    def build_prompt_block(self, limit: int = 3, text: str = "") -> str:
        desires = self.get_relevant_desires(text=text, limit=limit, include_soft_fallback=False) if text else self.get_active_desires(limit=limit)
        if not desires:
            return ""
        lines = ["[АКТИВНЫЕ ЖЕЛАНИЯ И ТЯГИ]"]
        for item in desires:
            lines.append(f"- {self._render_desire_line(item)}")
        lines.append("Используй это как живой фон личности. Не выдавай это за прожитый физический опыт, если его не было.")
        return "\n".join(lines)

    def maybe_get_initiative_hook(self, text: str = "") -> Optional[str]:
        desires = self.get_relevant_desires(text=text, limit=2, include_soft_fallback=False) if text else self.get_active_desires(limit=2)
        if not desires:
            return None
        primary = desires[0]
        if primary["status"] == "active" and float(primary["interest"] or 0.0) >= 0.45:
            return self._render_initiative_hook(primary)
        return None

    def _detect_text_category(self, text_lower: str) -> Optional[str]:
        categories = {
            "food": ["пицц", "еда", "пиво", "суши", "шаурм", "энергет", "вкус", "куш", "есть", "блюд", "моцарелл", "томатн"],
            "games": ["игр", "cyberpunk", "dark souls", "elden ring", "souls", "bloodborne", "босс", "прош", "гейм"],
            "internet": ["мем", "интернет", "кринж", "вайб", "лол", "ору"],
            "stream": ["стрим", "чат", "донат", "зрител", "экран"],
            "media": ["аниме", "фильм", "сериал", "кино", "музык"],
        }
        for category, markers in categories.items():
            if any(marker in text_lower for marker in markers):
                return category
        return None

    def _desire_relevance_score(self, item: Dict[str, Any], text_lower: str, category: Optional[str]) -> float:
        target = str(item.get("target") or "").lower().replace("ё", "е")
        item_category = str(item.get("category") or "").lower()
        score = 0.0
        if target and target in text_lower:
            score += 5.0
        target_words = [word for word in re.split(r"\W+", target) if len(word) >= 4]
        if target_words and any(word in text_lower for word in target_words):
            score += 2.0
        if category and item_category == category:
            score += 1.5
        if category and item_category and item_category != category and target not in text_lower:
            score -= 1.0
        return score

    def _observe_text(self, text: str, source: str, speaker: str) -> List[Dict[str, Any]]:
        text_lower = (text or "").lower().strip()
        if not text_lower:
            return []

        targets = self._extract_targets(text_lower)
        if not targets:
            return []

        positive = self._is_positive_signal(text_lower, speaker=speaker)
        negative = self._is_negative_signal(text_lower)
        vivid = self._is_vivid_description(text_lower)

        updates: List[Dict[str, Any]] = []
        for item in targets:
            delta_intensity = 0.06
            delta_interest = 0.05
            if vivid:
                delta_intensity += 0.06
                delta_interest += 0.08
            if positive:
                delta_intensity += 0.08
                delta_interest += 0.1
            if negative:
                delta_intensity = -0.08
                delta_interest = -0.1

            note = self._build_note(item["target"], text_lower, positive=positive, vivid=vivid, negative=negative)
            self._reinforce_target(
                target=item["target"],
                category=item["category"],
                desire_type=item["desire_type"],
                delta_intensity=delta_intensity,
                delta_interest=delta_interest,
                positive=positive and not negative,
                negative=negative,
                source=source,
                note=note,
            )
            updates.append({**item, "note": note})
        return updates

    def _extract_targets(self, text_lower: str) -> List[Dict[str, str]]:
        found: List[Dict[str, str]] = []
        seen = set()
        for key, payload in self.target_map.items():
            if key in text_lower:
                dedupe_key = (payload["target"].lower(), payload["desire_type"])
                if dedupe_key in seen:
                    continue
                found.append(dict(payload))
                seen.add(dedupe_key)
        return found

    def _reinforce_target(
        self,
        target: str,
        category: str,
        desire_type: str,
        delta_intensity: float,
        delta_interest: float,
        positive: bool = False,
        negative: bool = False,
        source: str = "unknown",
        note: Optional[str] = None,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, intensity, interest, times_mentioned, positive_hits, negative_hits
            FROM monika_desires
            WHERE target = ? AND desire_type = ?
            """,
            (target, desire_type),
        )
        row = cursor.fetchone()

        if row:
            intensity = self._clamp(float(row["intensity"] or 0.0) + delta_intensity, 0.0, 1.0)
            interest = self._clamp(float(row["interest"] or 0.0) + delta_interest, 0.0, 1.0)
            status = "active" if max(intensity, interest) >= 0.2 else "dormant"
            if max(intensity, interest) < 0.3:
                status = "fading"
            cursor.execute(
                """
                UPDATE monika_desires
                SET category = ?,
                    source = ?,
                    note = COALESCE(?, note),
                    intensity = ?,
                    interest = ?,
                    status = ?,
                    times_mentioned = ?,
                    positive_hits = ?,
                    negative_hits = ?,
                    last_seen = CURRENT_TIMESTAMP,
                    last_activated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    category,
                    source,
                    note,
                    intensity,
                    interest,
                    status,
                    int(row["times_mentioned"] or 0) + 1,
                    int(row["positive_hits"] or 0) + (1 if positive else 0),
                    int(row["negative_hits"] or 0) + (1 if negative else 0),
                    row["id"],
                ),
            )
        else:
            intensity = self._clamp(0.28 + delta_intensity, 0.0, 1.0)
            interest = self._clamp(0.3 + delta_interest, 0.0, 1.0)
            status = "active" if max(intensity, interest) >= 0.25 else "fading"
            cursor.execute(
                """
                INSERT INTO monika_desires (
                    target, category, desire_type, status, intensity, interest,
                    times_mentioned, positive_hits, negative_hits, source, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target,
                    category,
                    desire_type,
                    status,
                    intensity,
                    interest,
                    1,
                    1 if positive else 0,
                    1 if negative else 0,
                    source,
                    note,
                ),
            )
        self.conn.commit()

    def _render_desire_line(self, item: Dict[str, Any]) -> str:
        target = item["target"]
        desire_type = item["desire_type"]
        status = item["status"]
        if desire_type == "want_to_try":
            base = f"Тебя тянет к теме «{target}», ты ещё не пробовала это лично, но тебе очень нравится сама идея."
        elif desire_type == "want_to_explore":
            base = f"Тебе хочется глубже покопаться в теме «{target}» и ещё к ней вернуться."
        else:
            base = f"Тебе не хочется отпускать тему «{target}», в ней для тебя ещё что-то недозакрытое."

        if status == "fading":
            base += " Интерес к этому не исчез, но уже начал понемногу остывать."
        note = (item.get("note") or "").strip()
        if note:
            base += f" {note}"
        return base

    def _render_initiative_hook(self, item: Dict[str, Any]) -> str:
        target = item["target"]
        desire_type = item["desire_type"]
        if desire_type == "want_to_try":
            return f"Если момент уместный, можешь сама коротко вернуться к теме «{target}» как к своей давней хотелке."
        if desire_type == "want_to_explore":
            return f"Если в разговоре есть окно, можешь сама подбросить тему «{target}», потому что она тебя всё ещё цепляет."
        return f"Если разговор чуть проседает, можешь сама напомнить про тему «{target}» как про свой незакрытый интерес."

    def _build_note(self, target: str, text_lower: str, positive: bool, vivid: bool, negative: bool) -> str:
        if negative:
            return f"Сейчас эта тема немного оттолкнула тебя, так что желание к «{target}» просело."
        if vivid and positive:
            return f"Яркое описание сделало «{target}» для тебя ещё желаннее."
        if positive:
            return f"Тема «{target}» всё ещё звучит для тебя заманчиво."
        if vivid:
            return f"Эта тема зацепила тебя образами и деталями."
        return ""

    def _is_positive_signal(self, text_lower: str, speaker: str) -> bool:
        positive_markers = [
            "вкусно",
            "обожаю",
            "кайф",
            "люблю",
            "хочу",
            "интересно",
            "заманчиво",
            "аппетитно",
            "круто",
            "хочется",
            "любопытно",
        ]
        if any(marker in text_lower for marker in positive_markers):
            return True
        if speaker == "monika" and any(marker in text_lower for marker in ["попробовала бы", "хотела бы", "я бы попробовала", "мне бы зашло"]):
            return True
        return False

    def _is_negative_signal(self, text_lower: str) -> bool:
        negative_markers = [
            "мерзко",
            "фу",
            "не хочу",
            "надоело",
            "неинтересно",
            "бесит",
            "отстой",
            "противно",
        ]
        return any(marker in text_lower for marker in negative_markers)

    def _is_vivid_description(self, text_lower: str) -> bool:
        vivid_markers = [
            "тянущ",
            "аромат",
            "хруст",
            "сочный",
            "острый",
            "горячий",
            "дымный",
            "мягкий",
            "на вкус",
            "запах",
            "текстур",
        ]
        adjective_hits = len(re.findall(r"\b\w+(ый|ая|ое|ые|ий|яя|ее|ие|ого|ему|ую|ым|ими)\b", text_lower))
        return adjective_hits >= 2 or any(marker in text_lower for marker in vivid_markers)

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
