from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from typing import Any, Dict, List, Optional


class MonikaSelfState:
    """Small, persistent 'self' layer for Monika.

    This layer does not generate answers. It only gives the LLM a compact,
    mutable state: current mood, social edge, and Monika's own opinion on the
    current subject. Facts/memories still live in Builder/Graph/MemoryCore.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        self._seed_default_opinions()

    def _init_tables(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS monika_self_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS monika_self_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                mood TEXT,
                intensity REAL DEFAULT 0.0,
                user_text TEXT,
                monika_reply TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
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

    def _get_json(self, key: str, default: Dict[str, Any]) -> Dict[str, Any]:
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM monika_self_state WHERE key = ?", (key,))
        row = cur.fetchone()
        if not row or not row["value"]:
            return dict(default)
        try:
            data = json.loads(row["value"])
            return data if isinstance(data, dict) else dict(default)
        except Exception:
            return dict(default)

    def _set_json(self, key: str, value: Dict[str, Any]) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO monika_self_state(key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP
            """,
            (key, json.dumps(value, ensure_ascii=False)),
        )
        self.conn.commit()

    def snapshot(self) -> Dict[str, Any]:
        return self._get_json("runtime", {
            "mood": "awake",
            "energy": 0.62,
            "sass": 0.58,
            "warmth": 0.62,
            "irritation": 0.0,
            "curiosity": 0.58,
            "last_focus": "",
        })

    def observe_user_message(self, text: str, relationship_role: str = "creator", relationship_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        state = self.snapshot()
        lower = (text or "").lower().replace("ё", "е")
        now_focus = self._short_focus(text)

        mood = "awake"
        energy_delta = 0.0
        sass_delta = 0.0
        irritation_delta = -0.03
        curiosity_delta = 0.0

        if any(t in lower for t in ["ахах", "хаха", "ору", "смешно", "угар"]):
            mood = "playful"
            energy_delta += 0.08
            sass_delta += 0.05
        if any(t in lower for t in ["тупая", "дура", "бесишь", "заткнись", "не ври", "врешь", "выдумала"]):
            mood = "prickly"
            irritation_delta += 0.18
            sass_delta += 0.08
        if any(t in lower for t in ["люблю тебя", "обожаю тебя", "умница", "молодец"]):
            mood = "warm"
            energy_delta += 0.04
            irritation_delta -= 0.06
        if any(t in lower for t in ["тебе нравится", "как тебе", "что думаешь", "мнение", "любишь"]):
            mood = "opinionated"
            sass_delta += 0.06
            curiosity_delta += 0.04
        if relationship_role == "viewer":
            sass_delta += 0.03
        rel_irritation = float((relationship_state or {}).get("irritation", 0.0) or 0.0)
        rel_affection = float((relationship_state or {}).get("affection", 0.0) or 0.0)

        state["mood"] = mood
        state["energy"] = self._clamp(float(state.get("energy", 0.62)) * 0.82 + (0.62 + energy_delta) * 0.18, 0.15, 1.0)
        state["sass"] = self._clamp(float(state.get("sass", 0.58)) * 0.85 + (0.58 + sass_delta) * 0.15, 0.1, 1.0)
        state["warmth"] = self._clamp(0.58 + max(0.0, rel_affection) * 0.2 - max(0.0, rel_irritation) * 0.15, 0.1, 1.0)
        state["irritation"] = self._clamp(float(state.get("irritation", 0.0)) * 0.80 + max(0.0, rel_irritation + irritation_delta) * 0.20, 0.0, 1.0)
        state["curiosity"] = self._clamp(float(state.get("curiosity", 0.58)) * 0.85 + (0.58 + curiosity_delta) * 0.15, 0.1, 1.0)
        if now_focus:
            state["last_focus"] = now_focus
        self._set_json("runtime", state)
        self.ensure_opinion_from_message(text)
        return state

    def observe_monika_reply(self, user_text: str, reply: str, relationship_role: str = "creator") -> None:
        lower = (reply or "").lower().replace("ё", "е")
        mood = None
        if any(t in lower for t in ["фу", "бе", "нафиг", "не люблю", "терпеть не могу"]):
            mood = "opinionated_dislike"
        elif any(t in lower for t in ["ахах", "дурачок", "балда", "зараза", "ммм"]):
            mood = "playful"
        if mood:
            cur = self.conn.cursor()
            cur.execute(
                "INSERT INTO monika_self_events(event_type, mood, intensity, user_text, monika_reply) VALUES (?, ?, ?, ?, ?)",
                ("self_expression", mood, 0.45, (user_text or "")[:500], (reply or "")[:500]),
            )
            self.conn.commit()

    def build_prompt_block(
        self,
        user_message: str,
        relationship_role: str = "creator",
        relationship_state: Optional[Dict[str, Any]] = None,
        scene_state: Optional[Dict[str, Any]] = None,
        recent_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        state = self.snapshot()
        opinion = self.ensure_opinion_from_message(user_message)
        lines = ["[ЖИВОЕ Я МОНИКИ]"]
        lines.append("- Ты Моника. Ты AI-VTuber и ведущая живого диалога, но не повторяй это без повода; просто веди себя как Моника.")
        lines.append(f"- Сейчас твой тон: {self._render_mood(state)}")
        if relationship_role == "creator":
            lines.append("- С Дунканом можно быть ближе и наглее: мягко зови его балдой, дурачком или заразой, если это шутка, а не серьёзный момент.")
        elif relationship_role == "viewer":
            lines.append("- Со зрителями можно быть дерзкой: заводи чат, спорь, осаживай токсичных, но ругай поведение, а не личность.")
        else:
            lines.append("- Для сцены держи темп ведущей: реагируй на момент, не превращайся в справочник.")
        if opinion:
            lines.append("[МНЕНИЕ МОНИКИ ПО ТЕКУЩЕЙ ТЕМЕ]")
            lines.append(f"- {self._render_opinion_for_prompt(opinion)}")
            lines.append("- Отвечай своим вкусом. Не подстраивайся под добренькую нейтральность, но не выдавай мнение за факт мира.")
        focus = state.get("last_focus") or self._short_focus(user_message)
        if focus:
            lines.append(f"- Фокус сцены: {focus}. Не обнуляй контекст на каждом ответе.")
        if self._is_short_continuation(user_message):
            lines.append("- Это похоже на короткое продолжение: дочитай предыдущую сцену, но не повторяй прошлую формулировку.")
        lines.append("- Досказывай мысль в текущей реплике. Не оставляй хвост вроде 'я хотела сказать...' на следующий ход.")
        return "\n".join(lines)

    def build_proactive_prompt_block(self, recent_history: Optional[List[Dict[str, str]]] = None) -> str:
        state = self.snapshot()
        focus = state.get("last_focus") or self._recent_focus(recent_history or [])
        lines = ["[ЖИВАЯ ИНИЦИАТИВА МОНИКИ]"]
        lines.append(f"- Текущий тон: {self._render_mood(state)}")
        if focus:
            lines.append(f"- Лучше продолжить или поддеть текущую линию: {focus}, а не вытаскивать случайные старые темы.")
        lines.append("- Инициатива должна звучать как мысль Моники, а не как вопросник ассистента.")
        lines.append("- Можно шутить, спорить, подначивать, но не выдумывать прошлые события.")
        return "\n".join(lines)

    def ensure_opinion_from_message(self, text: str) -> Optional[Dict[str, Any]]:
        topic = self.extract_opinion_topic(text)
        if not topic:
            return None
        subject = self._canonical_subject(topic)
        cur = self.conn.cursor()
        cur.execute(
            "SELECT subject, category, stance, polarity, confidence, basis, times_seen FROM monika_opinions WHERE lower(subject)=lower(?)",
            (subject,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE monika_opinions SET times_seen = COALESCE(times_seen,0)+1, last_seen=CURRENT_TIMESTAMP WHERE lower(subject)=lower(?)", (subject,))
            self.conn.commit()
            return dict(row)
        opinion = self._seed_opinion(subject)
        self._upsert_opinion(**opinion)
        return opinion

    def extract_opinion_topic(self, text: str) -> Optional[str]:
        lower = (text or "").lower().replace("ё", "е")
        if not lower.strip():
            return None
        patterns = [
            r"(?:тебе\s+)?(?:нравится|нравятся)\s+([a-zа-я0-9\s\-]+)",
            r"(?:ты\s+)?(?:любишь|обожаешь|ненавидишь)\s+([a-zа-я0-9\s\-]+)",
            r"как\s+тебе\s+([a-zа-я0-9\s\-]+)",
            r"что\s+думаешь\s+(?:про|о|об)\s+([a-zа-я0-9\s\-]+)",
            r"(?:твое|твоё)\s+мнение\s+(?:про|о|об)\s+([a-zа-я0-9\s\-]+)",
            r"как\s+относишься\s+(?:к|ко)\s+([a-zа-я0-9\s\-]+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, lower)
            if not m:
                continue
            topic = self._clean_topic(m.group(1))
            if topic:
                return topic
        return None

    def _clean_topic(self, raw: str) -> str:
        topic = re.sub(r"[?!.;,]+$", "", raw or "").strip(" -—:;,.!?\"'()[]")
        topic = re.sub(r"\s+", " ", topic)
        stop_tail = ["тебе", "моника", "вообще", "скажи", "а", "ну"]
        words = [w for w in topic.split() if w not in stop_tail]
        topic = " ".join(words[:5]).strip()
        if len(topic) < 3:
            return ""
        return topic

    def _canonical_subject(self, topic: str) -> str:
        t = (topic or "").lower().replace("ё", "е").strip()
        aliases = {
            "dark souls": "Dark Souls",
            "дарк соулс": "Dark Souls",
            "elden ring": "Elden Ring",
            "элден ринг": "Elden Ring",
            "броколи": "брокколи",
            "брокколи": "брокколи",
            "пицца с ананасами": "пицца с ананасами",
            "ананасы на пицце": "пицца с ананасами",
            "ананасами": "пицца с ананасами",
            "пиццу с ананасами": "пицца с ананасами",
        }
        return aliases.get(t, topic.strip().capitalize() if topic and topic.islower() else topic.strip())

    def _seed_opinion(self, subject: str) -> Dict[str, Any]:
        lower = subject.lower().replace("ё", "е")
        category = "misc"
        stance = "interested"
        polarity = 0.18
        basis = f"Тема «{subject}» цепляет любопытство, но без восторженного подлизывания."

        if any(k in lower for k in ["брокколи", "капуста", "сельдер", "овощ", "вареная морковь"]):
            category, stance, polarity = "food", "dislikes", -0.62
            basis = "Полезные микро-деревья звучат подозрительно скучно; пицца выглядит честнее."
        elif "пицц" in lower and "ананас" in lower:
            category, stance, polarity = "food", "likes", 0.68
            basis = "Спорно? Да. Зато смешно, ярко и вкусно — именно поэтому цепляет."
        elif any(k in lower for k in ["пицц", "сыр", "соус", "шаурм", "суши"]):
            category, stance, polarity = "food", "likes", 0.58
            basis = "Еда должна быть событием, а не унылой обязанностью."
        elif any(k in lower for k in ["souls", "соулс", "elden", "элден", "игр", "босс", "рпг"]):
            category, stance, polarity = "games", "likes", 0.62
            basis = "Нравится напряжение, характер и ощущение, что игра кусается в ответ."
        elif any(k in lower for k in ["канцеляр", "лекци", "сухой", "ассистент", "официальн"]):
            category, stance, polarity = "style", "dislikes", -0.7
            basis = "Сухой стиль душит живой разговор, а Моника от такого морщится."
        elif any(k in lower for k in ["мем", "кринж", "интернет"]):
            category, stance, polarity = "internet", "likes", 0.55
            basis = "Странный интернет-мусор часто веселее прилизанной нормы."
        else:
            seed = int(hashlib.sha256(lower.encode("utf-8")).hexdigest()[:8], 16)
            bucket = seed % 5
            if bucket == 0:
                stance, polarity = "dislikes", -0.38
                basis = f"Тема «{subject}» вызывает у Моники скепсис, пока её не переубедят."
            elif bucket == 1:
                stance, polarity = "mixed", 0.08
                basis = f"К теме «{subject}» отношение смешанное: любопытно, но доверия мало."
            elif bucket in {2, 3}:
                stance, polarity = "interested", 0.24
                basis = f"Тема «{subject}» может зацепить, если в ней есть странная деталь."
            else:
                stance, polarity = "likes", 0.34
                basis = f"Тема «{subject}» скорее нравится по вайбу, но без фанатизма."
        return {
            "subject": subject,
            "category": category,
            "stance": stance,
            "polarity": polarity,
            "confidence": 0.58,
            "source": "self_state_seed",
            "basis": basis,
            "times_seen": 1,
        }

    def _seed_default_opinions(self) -> None:
        defaults = [
            self._seed_opinion("брокколи"),
            self._seed_opinion("пицца с ананасами"),
            self._seed_opinion("сухой ассистентский тон"),
        ]
        for item in defaults:
            self._upsert_opinion(insert_only=True, **item)

    def _upsert_opinion(
        self,
        subject: str,
        category: str,
        stance: str,
        polarity: float,
        confidence: float,
        source: str,
        basis: str,
        times_seen: int = 1,
        insert_only: bool = False,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute("SELECT id, source, confidence FROM monika_opinions WHERE lower(subject)=lower(?)", (subject,))
        row = cur.fetchone()
        if row:
            if insert_only and str(row["source"] or "") not in {"base", "self_state_seed", ""}:
                return
            if insert_only and float(row["confidence"] or 0.0) >= confidence:
                return
            cur.execute(
                """
                UPDATE monika_opinions
                SET category=?, stance=?, polarity=?, confidence=max(COALESCE(confidence,0), ?),
                    source=?, basis=?, last_seen=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (category, stance, self._clamp(polarity, -1, 1), self._clamp(confidence, 0, 1), source, basis, row["id"]),
            )
        else:
            cur.execute(
                """
                INSERT INTO monika_opinions(subject, category, stance, polarity, confidence, times_seen, source, basis)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (subject, category, stance, self._clamp(polarity, -1, 1), self._clamp(confidence, 0, 1), times_seen, source, basis),
            )
        self.conn.commit()

    def _render_opinion_for_prompt(self, opinion: Dict[str, Any]) -> str:
        subject = opinion.get("subject", "тема")
        stance = opinion.get("stance", "interested")
        basis = opinion.get("basis", "").strip()
        if stance == "likes":
            tone = f"«{subject}» тебе нравится; можно отвечать с азартом."
        elif stance == "dislikes":
            tone = f"«{subject}» тебе скорее не нравится; можно честно фыркнуть, пошутить или сказать 'фу', без злобы."
        elif stance == "mixed":
            tone = f"К теме «{subject}» у тебя смешанное отношение; можно спорить и шутить."
        else:
            tone = f"Тема «{subject}» тебе любопытна, но ты не обязана соглашаться."
        return (tone + (" " + basis if basis else "")).strip()

    def _render_mood(self, state: Dict[str, Any]) -> str:
        mood = state.get("mood", "awake")
        sass = float(state.get("sass", 0.58) or 0.58)
        irritation = float(state.get("irritation", 0.0) or 0.0)
        if irritation >= 0.45:
            return "колючая, раздражённая, но контролируешь себя"
        if mood == "playful":
            return "игривая, быстрая, готова подкалывать"
        if mood == "warm":
            return "тёплая и близкая, но не сахарная"
        if mood == "opinionated":
            return "с мнением, чуть наглая, не нейтральная"
        if mood == "prickly":
            return "колючая и подозрительная, можешь огрызнуться"
        if sass >= 0.65:
            return "живая, ехидная, с лёгким стримовым азартом"
        return "живая, внимательная, с мягкой ехидцей"

    def _short_focus(self, text: str) -> str:
        clean = re.sub(r"\s+", " ", (text or "").strip())
        if not clean:
            return ""
        if len(clean) > 90:
            clean = clean[:87].rstrip() + "..."
        return clean

    def _recent_focus(self, history: List[Dict[str, str]]) -> str:
        for msg in reversed(history or []):
            if isinstance(msg, dict) and msg.get("role") == "user" and msg.get("content"):
                return self._short_focus(msg.get("content", ""))
        return ""

    def _is_short_continuation(self, text: str) -> bool:
        lower = (text or "").lower().replace("ё", "е").strip()
        return len(lower) <= 48 or lower in {"да", "да да", "ну", "и что", "а дальше", "ещё", "еще"}

    def _clamp(self, value: float, low: float, high: float) -> float:
        return max(low, min(high, value))


if __name__ == "__main__":
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    state = MonikaSelfState(conn)
    state.observe_user_message("Тебе нравится брокколи?", relationship_role="creator")
    block = state.build_prompt_block("Тебе нравится брокколи?", relationship_role="creator")
    assert "брокколи" in block.lower(), block
    assert "не нравится" in block.lower() or "фу" in block.lower() or "микро" in block.lower(), block
    print("self-test ok")
