import re
import time
from collections import defaultdict
from typing import Optional

from config import PRIORITIES
from stimulus import Stimulus


class StreamRouter:
    """
    Minimal stream event router.
    Accepts voice/chat/donation/screen events and decides their priority and freshness.
    """

    def __init__(self):
        self.last_event_time_by_source = defaultdict(float)
        self.last_screen_comment = 0.0
        self.last_donation_time = 0.0
        self.last_chat_batch_time = 0.0

    def build_stimulus(
        self,
        source: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> Optional[Stimulus]:
        metadata = metadata or {}
        content = (content or "").strip()
        if not content:
            return None

        normalized_source = source.lower().strip()
        now = time.time()

        if normalized_source == "voice":
            priority = PRIORITIES["streamer_voice"]
            stimulus = Stimulus(priority=priority, source="voice", content=content, metadata=metadata)
        elif normalized_source in {"streamer_text", "text_input"}:
            priority = PRIORITIES["streamer_text"]
            stimulus = Stimulus(priority=priority, source="text_input", content=content, metadata=metadata)
        elif normalized_source == "donation":
            priority = PRIORITIES["stream_event"]
            stimulus = Stimulus(priority=priority, source="donation", content=self._format_donation(content, metadata), metadata=metadata)
            self.last_donation_time = now
        elif normalized_source == "screen":
            if now - self.last_screen_comment < 6.0:
                return None
            priority = PRIORITIES["interesting_topic"]
            stimulus = Stimulus(priority=priority, source="screen", content=self._format_screen_event(content), metadata=metadata)
            self.last_screen_comment = now
        elif normalized_source == "chat":
            priority = self._classify_chat_priority(content)
            username = metadata.get("username", "viewer")
            stimulus = Stimulus(
                priority=priority,
                source="chat",
                content=self._format_chat(username, content),
                metadata=metadata,
            )
        else:
            stimulus = Stimulus(priority=PRIORITIES["general_chat"], source=normalized_source, content=content, metadata=metadata)

        self.last_event_time_by_source[normalized_source] = now
        return stimulus

    def should_accept(self, stimulus: Stimulus, signals) -> bool:
        if stimulus is None:
            return False

        if stimulus.source == "screen" and signals.human_speaking:
            return False

        if stimulus.source == "chat" and time.time() - self.last_donation_time < 4.0:
            return False

        return True

    def _classify_chat_priority(self, text: str) -> int:
        text_lower = text.lower()
        if any(marker in text_lower for marker in ["моника", "@моника", "monika", "ответь", "как думаешь"]):
            return PRIORITIES["direct_question"]
        if any(marker in text_lower for marker in ["тупая", "дура", "ботиха", "бездушная"]):
            return PRIORITIES["hater_attack"]
        if any(marker in text_lower for marker in ["мем", "жесть", "ору", "кринж", "dark souls", "elden ring"]):
            return PRIORITIES["interesting_topic"]
        return PRIORITIES["general_chat"]

    def _format_chat(self, username: str, text: str) -> str:
        return f"Сообщение из чата от {username}: {text}\nОтветь как стримерша: коротко, живо, без длинной лекции."

    def _format_donation(self, text: str, metadata: dict) -> str:
        username = metadata.get("username", "зритель")
        amount = metadata.get("amount", "")
        amount_part = f" на {amount}" if amount else ""
        return (
            f"Пришёл донат от {username}{amount_part}: {text}\n"
            "Сначала коротко и живо отреагируй на донат. Обязательно произнеси ник {username} и сумму {amount} если она есть. "
            "Потом при желании ответь по сути в 1-2 предложениях."
        )

    def _format_screen_event(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return (
            f"Событие на экране: {cleaned}\n"
            "Коротко прокомментируй увиденное как живая VTuber, если момент реально заслуживает реакции."
        )
