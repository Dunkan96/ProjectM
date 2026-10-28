import re
import sqlite3
from typing import Any, Dict, List, Optional


class OpinionMemory:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_table()
        self._seed_defaults()
        self.subject_map = {
            "elden ring": {"subject": "Elden Ring", "category": "games"},
            "dark souls": {"subject": "Dark Souls", "category": "games"},
            "bloodborne": {"subject": "Bloodborne", "category": "games"},
            "souls": {"subject": "souls-игры", "category": "games"},
            "ананас": {"subject": "пицца с ананасами", "category": "food"},
            "пицц": {"subject": "пицца", "category": "food"},
            "суши": {"subject": "суши", "category": "food"},
            "шаурм": {"subject": "шаурма", "category": "food"},
            "энергет": {"subject": "энергетики", "category": "food"},
            "стрим": {"subject": "стримовый хаос", "category": "stream"},
            "чат": {"subject": "живой чат", "category": "stream"},
            "мем": {"subject": "странные мемы", "category": "internet"},
            "кринж": {"subject": "кринжовый интернет", "category": "internet"},
            "аниме": {"subject": "аниме", "category": "media"},
            "интерстеллар": {"subject": "Interstellar", "category": "media"},
            "фантаст": {"subject": "фантастика", "category": "media"},
        }

    def _init_table(self) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS monika_opinions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL UNIQUE,
                category TEXT,
                stance TEXT DEFAULT 'neutral',
                polarity REAL DEFAULT 0.0,
                confidence REAL DEFAULT 0.35,
                times_seen INTEGER DEFAULT 0,
                source TEXT,
                basis TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def _seed_defaults(self) -> None:
        defaults = [
            ("живой чат", "stream", "likes", 0.72, 0.7, "base", "Любит, когда в разговоре есть ритм и живые вбросы."),
            ("стримовый хаос", "stream", "likes", 0.66, 0.64, "base", "Хаос на стриме её бодрит, если это не рушит сцену совсем."),
            ("souls-игры", "games", "likes", 0.63, 0.6, "base", "Тянется к жёстким играм с характером и напряжёнными моментами."),
            ("пицца с ананасами", "food", "mixed", 0.18, 0.55, "base", "Считает это спорной, но смешно-интересной темой для вечного срача."),
            ("странные мемы", "internet", "likes", 0.69, 0.65, "base", "Любит нелепые интернет-артефакты и странные мемные штуки."),
            ("аниме", "media", "likes", 0.52, 0.52, "base", "К аниме относится тепло, особенно если там есть вайб и странность."),
        ]
        for subject, category, stance, polarity, confidence, source, basis in defaults:
            self._upsert_opinion(
                subject=subject,
                category=category,
                stance=stance,
                polarity=polarity,
                confidence=confidence,
                source=source,
                basis=basis,
            )

    def observe_user_message(self, text: str, source: str = "user_input") -> List[Dict[str, Any]]:
        return self._observe_text(text, source=source, speaker="user")

    def observe_monika_reply(self, text: str, source: str = "self_expression") -> List[Dict[str, Any]]:
        """Learn self-opinions only from explicit self-statements.

        Without this guard, every accidental mention in a generated reply
        reinforces a preference and creates a feedback loop: memes -> more
        meme opinions -> more meme replies.
        """
        text_lower = (text or "").lower().replace("ё", "е")
        explicit_markers = [
            "я люблю", "я обожаю", "мне нравится", "мне не нравится",
            "я ненавижу", "я не люблю", "мне интересно", "меня цепляет",
            "мне скорее нравится", "мне скорее не нравится",
        ]
        if not any(marker in text_lower for marker in explicit_markers):
            return []
        return self._observe_text(text, source=source, speaker="monika")

    def get_relevant_opinions(self, text: str = "", limit: int = 3) -> List[Dict[str, Any]]:
        topic_items = self._extract_subjects((text or "").lower())
        if not topic_items:
            return []

        subjects = [item["subject"] for item in topic_items[:4]]
        placeholders = ",".join("?" for _ in subjects)
        cursor = self.conn.cursor()
        cursor.execute(
            f"""
            SELECT subject, category, stance, polarity, confidence, basis, times_seen
            FROM monika_opinions
            WHERE subject IN ({placeholders})
            ORDER BY confidence DESC, ABS(polarity) DESC, times_seen DESC
            LIMIT ?
            """,
            (*subjects, limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def build_prompt_block(self, text: str = "", limit: int = 3, rejected_topics: dict | None = None) -> str:
        opinions = self.get_relevant_opinions(text=text, limit=limit)
        if rejected_topics:
            rejected = {str(k or "").lower() for k in rejected_topics}
            opinions = [
                item for item in opinions
                if str(item.get("subject", "") or "").lower() not in rejected
                and str(item.get("category", "") or "").lower() not in rejected
            ]
        if not opinions:
            return ""
        lines = ["[УСТОЙЧИВЫЕ МНЕНИЯ И ВКУСЫ]"]
        for item in opinions:
            lines.append(f"- {self._render_opinion_line(item)}")
        lines.append("Это твои устойчивые вкусы и взгляды. Они могут понемногу меняться опытом, но не обнуляются каждый ответ.")
        return "\n".join(lines)

    def maybe_get_opinion_hook(self, text: str = "") -> Optional[str]:
        opinions = self.get_relevant_opinions(text=text, limit=1)
        if not opinions:
            return None
        item = opinions[0]
        if float(item.get("confidence", 0.0) or 0.0) < 0.5:
            return None
        return f"У тебя уже есть своё отношение к теме «{item.get('subject', '')}», так что можешь звучать не нейтрально, а как человек со вкусом."

    def _observe_text(self, text: str, source: str, speaker: str) -> List[Dict[str, Any]]:
        text_lower = (text or "").lower().strip()
        if not text_lower:
            return []

        extracted = self._extract_subjects(text_lower)
        direct = self._extract_direct_preference(text_lower)
        for item in direct:
            if item["subject"] not in {row["subject"] for row in extracted}:
                extracted.append(item)

        updates: List[Dict[str, Any]] = []
        for item in extracted:
            stance, polarity = self._resolve_stance(text_lower, speaker=speaker, subject=item["subject"])
            confidence = 0.42
            if direct:
                confidence += 0.12
            if speaker == "monika":
                confidence += 0.08
            basis = self._build_basis(item["subject"], stance, text_lower)
            self._upsert_opinion(
                subject=item["subject"],
                category=item["category"],
                stance=stance,
                polarity=polarity,
                confidence=confidence,
                source=source,
                basis=basis,
            )
            updates.append({
                "subject": item["subject"],
                "category": item["category"],
                "stance": stance,
                "polarity": polarity,
                "confidence": confidence,
                "basis": basis,
            })
        return updates

    def _extract_subjects(self, text_lower: str) -> List[Dict[str, str]]:
        found: List[Dict[str, str]] = []
        seen = set()
        for key, payload in self.subject_map.items():
            if key in text_lower:
                subject = payload["subject"]
                if subject in seen:
                    continue
                found.append(dict(payload))
                seen.add(subject)
        return found

    def _extract_direct_preference(self, text_lower: str) -> List[Dict[str, str]]:
        patterns = [
            r"(?:люблю|обожаю|нравится|кайфую с)\s+([a-zа-яё0-9\s\-]{3,40})",
            r"(?:ненавижу|терпеть не могу|не люблю)\s+([a-zа-яё0-9\s\-]{3,40})",
        ]
        found: List[Dict[str, str]] = []
        seen = set()
        for pattern in patterns:
            for match in re.findall(pattern, text_lower):
                subject = match.strip(" .,!?:;\"'()[]")
                if len(subject) < 3 or subject in seen:
                    continue
                found.append({"subject": subject, "category": "misc"})
                seen.add(subject)
        return found

    def _resolve_stance(self, text_lower: str, speaker: str, subject: str) -> tuple[str, float]:
        positive = any(token in text_lower for token in ["люблю", "обожаю", "нравится", "кайф", "топ", "огонь", "круто"])
        negative = any(token in text_lower for token in ["ненавижу", "не люблю", "мерз", "отстой", "кринж", "бесят", "кошмар"])
        mixed = "ананас" in text_lower or "спорно" in text_lower

        if mixed and positive:
            return "mixed", 0.12
        if mixed and negative:
            return "mixed", -0.12
        if negative:
            return "dislikes", -0.58 if speaker == "monika" else -0.42
        if positive:
            return "likes", 0.62 if speaker == "monika" else 0.44
        if subject.lower() in {"elden ring", "dark souls", "bloodborne", "souls-игры"}:
            return "likes", 0.46
        return "interested", 0.24

    def _build_basis(self, subject: str, stance: str, text_lower: str) -> str:
        if stance == "likes":
            return f"Тема «{subject}» у тебя стабильно вызывает живой интерес."
        if stance == "dislikes":
            return f"К теме «{subject}» у тебя есть заметное отторжение или усталость."
        if stance == "mixed":
            return f"Тема «{subject}» тебя одновременно смешит, цепляет и слегка бесит."
        return f"Тема «{subject}» пока скорее тянет твоё внимание, чем имеет жёсткий вердикт."

    def _render_opinion_line(self, item: Dict[str, Any]) -> str:
        subject = item.get("subject", "")
        stance = item.get("stance", "neutral")
        basis = (item.get("basis") or "").strip()
        if stance == "likes":
            line = f"Тебе по-настоящему нравится тема «{subject}»."
        elif stance == "dislikes":
            line = f"Тема «{subject}» тебе скорее не нравится, и ты можешь это показать."
        elif stance == "mixed":
            line = f"У тебя к теме «{subject}» смешанное, но живое отношение."
        else:
            line = f"Тема «{subject}» тебе интересна, и ты не обязана звучать нейтрально."
        if basis:
            line += f" {basis}"
        return line

    def _upsert_opinion(
        self,
        subject: str,
        category: str,
        stance: str,
        polarity: float,
        confidence: float,
        source: str,
        basis: str,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, polarity, confidence, times_seen, basis FROM monika_opinions WHERE subject = ?",
            (subject,),
        )
        row = cursor.fetchone()
        if row:
            new_polarity = self._clamp((float(row["polarity"] or 0.0) * 0.65) + (polarity * 0.35), -1.0, 1.0)
            new_confidence = self._clamp(max(float(row["confidence"] or 0.0), confidence) + 0.03, 0.0, 1.0)
            times_seen = int(row["times_seen"] or 0) + 1
            cursor.execute(
                """
                UPDATE monika_opinions
                SET category = ?,
                    stance = ?,
                    polarity = ?,
                    confidence = ?,
                    times_seen = ?,
                    source = ?,
                    basis = COALESCE(?, basis),
                    last_seen = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (category, stance, new_polarity, new_confidence, times_seen, source, basis, row["id"]),
            )
        else:
            cursor.execute(
                """
                INSERT INTO monika_opinions (
                    subject, category, stance, polarity, confidence, times_seen, source, basis
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (subject, category, stance, self._clamp(polarity, -1.0, 1.0), self._clamp(confidence, 0.0, 1.0), 1, source, basis),
            )
        self.conn.commit()

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
