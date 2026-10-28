from __future__ import annotations

import re
import time
from collections import deque
from typing import Any, Dict, List, Optional


class SessionMind:
    """Small operational memory for the current stream/session.

    It is deliberately NOT factual long-term memory. It tracks scene, open bits,
    recent mistakes and what should not be repeated.
    """

    def __init__(self, max_turns: int = 40):
        self.max_turns = max_turns
        self.turns: deque[Dict[str, Any]] = deque(maxlen=max_turns)
        self.current_topic: str = ""
        self.current_scene: str = "разговор"
        self.active_bit: str = ""
        self.open_loop: str = ""
        self.do_not_repeat: deque[str] = deque(maxlen=12)
        self.recent_guard_reasons: deque[str] = deque(maxlen=8)
        self.last_stage: str = "REACT"

    def observe_turn(
        self,
        user_input: str,
        reply: str,
        relationship_role: str = "creator",
        stage: str = "REACT",
        guard_reason: str = "",
        opinion: Optional[Dict[str, Any]] = None,
    ) -> None:
        user_input = (user_input or "").strip()
        reply = (reply or "").strip()
        topic = self.extract_topic(user_input) or self.current_topic
        if topic:
            self.current_topic = topic
        self.last_stage = stage or self.last_stage
        self.current_scene = self._infer_scene(user_input, stage, topic)
        self.active_bit = self._infer_bit(user_input, reply, stage)
        self.open_loop = self._infer_open_loop(user_input, reply, stage)
        if guard_reason and guard_reason != "ok":
            self.recent_guard_reasons.append(guard_reason)
        for phrase in self._bad_phrases(reply):
            self.do_not_repeat.append(phrase)
        self.turns.append({
            "t": time.time(),
            "user": user_input[:500],
            "reply": reply[:500],
            "role": relationship_role,
            "stage": stage,
            "topic": topic,
            "guard_reason": guard_reason,
            "opinion": dict(opinion or {}),
        })

    def build_prompt_block(self, user_input: str = "") -> str:
        lines = ["[SESSION MIND]"]
        lines.append(f"- Текущая сцена: {self.current_scene}.")
        if self.current_topic:
            lines.append(f"- Текущая тема: {self.current_topic}.")
        if self.active_bit:
            lines.append(f"- Активный бит/игра сцены: {self.active_bit}.")
        if self.open_loop:
            lines.append(f"- Открытая мысль: {self.open_loop}.")
        if self.do_not_repeat:
            lines.append("- Не повторяй эти технические/плохие формулировки: " + "; ".join(list(self.do_not_repeat)[-5:]))
        if self.recent_guard_reasons:
            lines.append("- Недавние поломки ответа: " + ", ".join(list(self.recent_guard_reasons)[-4:]) + ". Не повторяй их.")
        lines.append("- Это оперативная сцена, не долговременные факты. Не выдавай свои прошлые фразы за воспоминания пользователя.")
        return "\n".join(lines)

    def build_proactive_prompt_block(self, recent_history: Optional[List[Dict[str, str]]] = None) -> str:
        topic = self.current_topic or self._recent_topic(recent_history or [])
        lines = ["[SESSION MIND ДЛЯ ИНИЦИАТИВЫ]"]
        lines.append(f"- Сцена: {self.current_scene}.")
        if topic:
            lines.append(f"- Лучше продолжить текущую тему: {topic}, а не вытаскивать случайные старые темы.")
        if self.open_loop:
            lines.append(f"- Можно подхватить открытую мысль: {self.open_loop}.")
        if self.active_bit:
            lines.append(f"- Можно продолжить бит: {self.active_bit}.")
        lines.append("- Инициатива должна звучать как продолжение сцены, а не как новая анкета.")
        return "\n".join(lines)

    def suggest_proactive_topic(self, recent_history: Optional[List[Dict[str, str]]] = None) -> str:
        if self.open_loop:
            return self.open_loop[:80]
        if self.active_bit:
            return self.active_bit[:80]
        if self.current_topic:
            return self.current_topic
        return self._recent_topic(recent_history or [])

    def extract_topic(self, text: str) -> str:
        lower = (text or "").lower().replace("ё", "е")
        # Specific high-signal phrases first.
        patterns = [
            r"нравится\s+([a-zа-я0-9\s\-]+)",
            r"думаешь\s+(?:про|о|об)\s+([a-zа-я0-9\s\-]+)",
            r"мнение\s+(?:про|о|об)\s+([a-zа-я0-9\s\-]+)",
            r"как\s+тебе\s+([a-zа-я0-9\s\-]+)",
            r"страшилк[аиу]\s*(?:про|о)?\s*([a-zа-я0-9\s\-]*)",
        ]
        for pat in patterns:
            m = re.search(pat, lower)
            if m:
                topic = self._clean_topic(m.group(1))
                if topic:
                    return topic
        keywords = [
            ("хогвард", "сон про Хогвардс"),
            ("пицц", "пицца"),
            ("ананас", "пицца с ананасами"),
            ("брокк", "брокколи"),
            ("сухой", "сухой ассистентский стиль"),
            ("ассистент", "сухой ассистентский стиль"),
            ("страшил", "страшилки"),
            ("тыкв", "тыква/Хэллоуин"),
            ("душн", "душный стиль"),
            ("стрим", "стрим"),
        ]
        for key, value in keywords:
            if key in lower:
                return value
        return ""

    def _clean_topic(self, raw: str) -> str:
        topic = re.sub(r"[?!.;,]+$", "", raw or "").strip(" -—:;,.!?\"'()[]")
        topic = re.sub(r"\s+", " ", topic)
        bad_tail = {"тебе", "моника", "вообще", "скажи", "ну", "а", "это"}
        words = [w for w in topic.split() if w not in bad_tail]
        return " ".join(words[:6]).strip()

    def _infer_scene(self, user_input: str, stage: str, topic: str) -> str:
        if stage == "STORY":
            return "мини-перформанс/история"
        if stage == "OPINION":
            return "обсуждение вкуса и мнения"
        if stage == "BANTER":
            return "перепалка и подколы"
        if stage == "MEMORY":
            return "точное вспоминание"
        if topic:
            return f"разговор вокруг «{topic}»"
        return self.current_scene or "разговор"

    def _infer_bit(self, user_input: str, reply: str, stage: str) -> str:
        lower_user = (user_input or "").lower().replace("ё", "е")
        lower_reply = (reply or "").lower().replace("ё", "е")
        if stage == "BANTER":
            return "шутливая перепалка с Дунканом"
        if "тыкв" in lower_user or "тыкв" in lower_reply:
            return "тыква как сценический реквизит"
        if "балда" in lower_user or "дурач" in lower_user:
            return "Дункан подкалывает Монику"
        if "страшил" in lower_user or "страшил" in lower_reply:
            return "страшилка/жуткая история"
        return self.active_bit

    def _infer_open_loop(self, user_input: str, reply: str, stage: str) -> str:
        if stage == "OPINION":
            topic = self.extract_topic(user_input)
            if topic:
                return f"дожать мнение Моники про «{topic}»"
        if stage == "STORY":
            return "можно продолжить атмосферу истории или обсудить, что в ней было жуткого"
        if user_input.strip().endswith("?"):
            return ""
        return self.open_loop

    def _bad_phrases(self, reply: str) -> List[str]:
        lower = (reply or "").lower().replace("ё", "е")
        bad = []
        markers = [
            "я чуть не повторила",
            "я чуть не ушла",
            "попугаем",
            "задай вопрос короче",
            "продолжай, я слушаю",
            "как ассистент",
        ]
        for m in markers:
            if m in lower:
                bad.append(m)
        return bad

    def _recent_topic(self, history: List[Dict[str, str]]) -> str:
        for msg in reversed(history[-8:]):
            topic = self.extract_topic(str(msg.get("content", "")))
            if topic:
                return topic
        return ""
