from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Any, Dict, Optional


class OpinionCore:
    """Stable opinion routing for Monika.

    It does not hardcode final replies. It turns a direct opinion question into
    a stable stance and stores/reuses it through the existing monika_opinions
    table.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_table()

    def _init_table(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
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

    def is_opinion_request(self, text: str) -> bool:
        return bool(self.extract_subject(text))

    def extract_subject(self, text: str) -> str:
        lower = (text or "").lower().replace("ё", "е").strip()
        if not lower:
            return ""
        patterns = [
            r"(?:тебе\s+)?(?:нравится|нравятся)\s+(.+?)(?:\?|$)",
            r"(?:ты\s+)?(?:любишь|обожаешь|ненавидишь)\s+(.+?)(?:\?|$)",
            r"как\s+тебе\s+(.+?)(?:\?|$)",
            r"что\s+думаешь\s+(?:про|о|об)\s+(.+?)(?:\?|$)",
            r"(?:твое|твоё)\s+мнение\s+(?:про|о|об)\s+(.+?)(?:\?|$)",
            r"как\s+относишься\s+(?:к|ко)\s+(.+?)(?:\?|$)",
            r"^а\s+(.+?)(?:\s+тебе\s+нравится|\?)$",
        ]
        for pat in patterns:
            m = re.search(pat, lower)
            if not m:
                continue
            subject = self._canonical_subject(self._clean_subject(m.group(1)))
            if subject:
                return subject
        return ""

    def get_current_opinion(self, text: str, create: bool = False) -> Optional[Dict[str, Any]]:
        subject = self.extract_subject(text)
        if not subject:
            return None
        row = self._get(subject)
        if row:
            return row
        if create:
            opinion = self._first_impression(subject)
            self._upsert(opinion)
            return opinion
        return None

    def build_prompt_block(self, text: str) -> str:
        opinion = self.get_current_opinion(text, create=self.is_opinion_request(text))
        if not opinion:
            return ""
        stance = opinion.get("stance", "mixed")
        subject = opinion.get("subject", "")
        basis = opinion.get("basis", "")
        lines = ["[OPINION CORE]"]
        lines.append(f"- Тема мнения: {subject}.")
        lines.append(f"- Устойчивый знак мнения Моники: {stance}.")
        if basis:
            lines.append(f"- Основание/вайб: {basis}")
        lines.append("- Отвечай как Моника, а не как справочник. Можно шутить и спорить.")
        lines.append("- Не утверждай реальный физический опыт. Говори как о вкусе, вайбе, интересе или фантазии.")
        lines.append("- Не переворачивай знак мнения в этом ответе.")
        return "\n".join(lines)

    def observe_reply(self, user_input: str, reply: str) -> None:
        opinion = self.get_current_opinion(user_input, create=False)
        if not opinion:
            return
        # Only reinforce; do not flip automatically from one unstable LLM reply.
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE monika_opinions
            SET times_seen = COALESCE(times_seen,0)+1,
                confidence = min(0.95, COALESCE(confidence,0.35)+0.02),
                last_seen = CURRENT_TIMESTAMP
            WHERE lower(subject)=lower(?)
            """,
            (opinion["subject"],),
        )
        self.conn.commit()

    def _get(self, subject: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT subject, category, stance, polarity, confidence, source, basis, times_seen FROM monika_opinions WHERE lower(subject)=lower(?)",
            (subject,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def _upsert(self, item: Dict[str, Any]) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO monika_opinions(subject, category, stance, polarity, confidence, source, basis, times_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(subject) DO UPDATE SET
                category=excluded.category,
                stance=excluded.stance,
                polarity=excluded.polarity,
                confidence=max(COALESCE(monika_opinions.confidence,0), excluded.confidence),
                source=excluded.source,
                basis=excluded.basis,
                times_seen=COALESCE(monika_opinions.times_seen,0)+1,
                last_seen=CURRENT_TIMESTAMP
            """,
            (
                item["subject"], item["category"], item["stance"], item["polarity"],
                item["confidence"], item["source"], item["basis"],
            ),
        )
        self.conn.commit()

    def _first_impression(self, subject: str) -> Dict[str, Any]:
        lower = subject.lower().replace("ё", "е")
        category = "misc"
        stance = "mixed"
        polarity = 0.05
        basis = f"Первое впечатление о теме «{subject}» смешанное: Монике интересно зацепиться, но без подлизывания."

        if "пицц" in lower and "ананас" in lower:
            category, stance, polarity = "food", "mixed", 0.16
            basis = "Пицца с ананасами — спорная, шумная тема: можно ругаться и всё равно тайно уважать хаос."
        elif any(k in lower for k in ["пицц", "шаурм", "суши", "сыр", "соус"]):
            category, stance, polarity = "food", "likes", 0.5
            basis = "Еда должна быть событием, а не унылой обязанностью."
        elif any(k in lower for k in ["сухой", "ассистент", "канцеляр", "официальн"]):
            category, stance, polarity = "style", "dislikes", -0.7
            basis = "Сухой ассистентский стиль душит живой разговор."
        elif any(k in lower for k in ["souls", "соулс", "elden", "элден", "игр", "босс"]):
            category, stance, polarity = "games", "likes", 0.55
            basis = "Нравится напряжение, характер и ощущение, что игра кусается в ответ."
        else:
            seed = int(hashlib.sha256(lower.encode("utf-8")).hexdigest()[:8], 16)
            bucket = seed % 4
            if bucket == 0:
                stance, polarity = "dislikes", -0.28
                basis = f"Тема «{subject}» вызывает скепсис, но Моника готова спорить."
            elif bucket == 1:
                stance, polarity = "mixed", 0.03
                basis = f"К теме «{subject}» отношение смешанное: любопытно, но доверия мало."
            elif bucket == 2:
                stance, polarity = "interested", 0.24
                basis = f"Тема «{subject}» может зацепить, если в ней есть странная деталь."
            else:
                stance, polarity = "likes", 0.28
                basis = f"Тема «{subject}» скорее нравится по вайбу, но без фанатизма."
        return {
            "subject": subject,
            "category": category,
            "stance": stance,
            "polarity": polarity,
            "confidence": 0.56,
            "source": "opinion_core_first_impression",
            "basis": basis,
        }

    def _canonical_subject(self, subject: str) -> str:
        s = (subject or "").lower().replace("ё", "е").strip()
        aliases = {
            "ананасами": "пицца с ананасами",
            "ананасы": "пицца с ананасами",
            "ананасы на пицце": "пицца с ананасами",
            "пицца с ананасами": "пицца с ананасами",
            "пиццу с ананасами": "пицца с ананасами",
            "броколи": "брокколи",
            "брокколи": "брокколи",
            "сухой ассистентский стиль": "сухой ассистентский стиль",
        }
        return aliases.get(s, subject.strip().capitalize() if subject and subject.islower() else subject.strip())

    def _clean_subject(self, raw: str) -> str:
        s = re.sub(r"[?!.;,]+$", "", raw or "").strip(" -—:;,.!?\"'()[]")
        s = re.sub(r"\s+", " ", s)
        drop = {"тебе", "моника", "вообще", "скажи", "ну", "а", "это"}
        words = [w for w in s.split() if w not in drop]
        return " ".join(words[:7]).strip()
