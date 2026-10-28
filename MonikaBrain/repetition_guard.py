from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+",
    flags=re.UNICODE,
)


@dataclass
class RepetitionAssessment:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    banned_hits: list[str] = field(default_factory=list)
    similar_to: str = ""
    similarity: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reasons": self.reasons,
            "constraints": self.constraints,
            "banned_hits": self.banned_hits,
            "similar_to": self.similar_to,
            "similarity": round(self.similarity, 3),
        }


class RepetitionGuard:
    """Session-level guard against phrase loops and user-banned wording.

    This is intentionally not a template layer. It only tells the generator what
    cannot be repeated, then verifies the candidate before it reaches chat/TTS.
    """

    def __init__(self, similarity_threshold: float = 0.82) -> None:
        self.similarity_threshold = similarity_threshold

    def update_session_from_user(self, session: dict, user_text: str) -> None:
        text = str(user_text or "")
        lowered = text.lower().replace("ё", "е")
        banned = session.setdefault("banned_reply_phrases", [])

        if any(marker in lowered for marker in ("не произноси", "не повторяй", "хватит повторять", "хватит этих фраз")):
            for phrase in self._extract_quoted_phrases(text):
                self._remember_banned_phrase(banned, phrase)

            tail = re.split(r"не произноси|не повторяй|хватит повторять|хватит этих фраз", lowered, maxsplit=1)
            if len(tail) > 1 and not self._extract_quoted_phrases(text):
                cleaned_tail = re.sub(r"[\"'«»]", " ", tail[-1]).strip(" .:;,-")
                if 10 <= len(cleaned_tail) <= 180:
                    self._remember_banned_phrase(banned, cleaned_tail)

        if any(marker in lowered for marker in ("хватит этих смайликов", "без смайликов", "без эмодзи", "без emoji")):
            session["no_emoji"] = True
        if any(marker in lowered for marker in ("можно смайлики", "можно эмодзи", "эмодзи можно", "смайлики можно")):
            session["no_emoji"] = False

        session["banned_reply_phrases"] = banned[-40:]

    def prompt_block(self, session: dict, recent_assistant: list[str] | None = None) -> str:
        banned = [p for p in session.get("banned_reply_phrases", []) if p]
        no_emoji = bool(session.get("no_emoji"))
        recent = [r for r in (recent_assistant or []) if r][-4:]
        if not banned and not no_emoji and not recent:
            return ""

        lines = [
            "[REPETITION GUARD]",
            "- Do not reuse the same wording, same sentence skeleton, or same emotional filler from recent Monika replies.",
            "- If the previous answer stalled, continue with a concrete new action/detail instead of promising to start.",
        ]
        if banned:
            lines.append("- User explicitly banned these exact phrases; never output them:")
            lines.extend(f"  * {phrase}" for phrase in banned[-10:])
        if no_emoji:
            lines.append("- User requested no emoji/smiley spam; answer without emoji.")
        if recent:
            lines.append("- Recent Monika replies to avoid echoing:")
            lines.extend(f"  * {reply[:220]}" for reply in recent)
        return "\n".join(lines)

    def assess(self, reply: str, history: list[dict] | None, session: dict) -> RepetitionAssessment:
        text = str(reply or "").strip()
        reasons: list[str] = []
        constraints: list[str] = []
        banned_hits: list[str] = []

        banned = [str(p) for p in session.get("banned_reply_phrases", []) if str(p).strip()]
        text_norm = self._norm(text)
        for phrase in banned:
            if self._norm(phrase) and self._norm(phrase) in text_norm:
                banned_hits.append(phrase)

        if banned_hits:
            reasons.append("banned_phrase")
            constraints.append("Do not use any phrase the user explicitly banned. Replace it with a new concrete action or reaction.")

        if bool(session.get("no_emoji")) and _EMOJI_RE.search(text):
            reasons.append("emoji_after_user_ban")
            constraints.append("The user asked for no emoji. Remove all emoji and answer in plain text.")

        recent = self._recent_assistant(history, limit=10)
        max_ratio = 0.0
        similar_to = ""
        for old in recent:
            ratio = self._similarity(text, old)
            if ratio > max_ratio:
                max_ratio = ratio
                similar_to = old
            if ratio >= self.similarity_threshold and len(self._norm(old)) > 18:
                reasons.append("similar_to_recent_reply")
                constraints.append("The answer is too similar to a recent Monika reply. Change the structure, verbs, imagery, and ending.")
                break

        repeated_segment = self._shared_long_segment(text, recent)
        if repeated_segment:
            reasons.append("repeated_segment")
            constraints.append(f"Do not reuse this repeated segment or its structure: {repeated_segment[:120]}")

        if len(re.findall(r"\.{2,}", text)) >= 3:
            reasons.append("ellipsis_loop")
            constraints.append("Stop using hesitant ellipsis as filler. Make a concrete next move.")

        return RepetitionAssessment(
            ok=not reasons,
            reasons=list(dict.fromkeys(reasons)),
            constraints=list(dict.fromkeys(constraints)),
            banned_hits=banned_hits,
            similar_to=similar_to,
            similarity=max_ratio,
        )

    def sanitize(self, reply: str, session: dict) -> str:
        text = str(reply or "")
        for phrase in session.get("banned_reply_phrases", []) or []:
            if not phrase:
                continue
            text = re.sub(re.escape(str(phrase)), "", text, flags=re.IGNORECASE)
        if bool(session.get("no_emoji")):
            text = _EMOJI_RE.sub("", text)
        text = re.sub(r"\s{2,}", " ", text).strip(" \n\t")
        return text

    def _extract_quoted_phrases(self, text: str) -> list[str]:
        phrases = re.findall(r"[\"«](.*?)[\"»]", text)
        phrases += re.findall(r"'([^']+)'", text)
        return [p.strip(" .:;,-") for p in phrases if len(p.strip()) >= 8]

    def _remember_banned_phrase(self, banned: list, phrase: str) -> None:
        phrase = str(phrase or "").strip(" .:;,-")
        if len(phrase) < 8:
            return
        norm = self._norm(phrase)
        if not any(self._norm(x) == norm for x in banned):
            banned.append(phrase)

    def _recent_assistant(self, history: list[dict] | None, limit: int = 8) -> list[str]:
        result: list[str] = []
        for msg in reversed(history or []):
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("content"):
                result.append(str(msg.get("content")))
            if len(result) >= limit:
                break
        return list(reversed(result))

    def _norm(self, text: str) -> str:
        text = str(text or "").lower().replace("ё", "е")
        text = _EMOJI_RE.sub("", text)
        text = re.sub(r"[^a-zа-я0-9]+", " ", text, flags=re.IGNORECASE).strip()
        return re.sub(r"\s+", " ", text)

    def _similarity(self, a: str, b: str) -> float:
        na = self._norm(a)
        nb = self._norm(b)
        if not na or not nb:
            return 0.0
        if min(len(na), len(nb)) < 16:
            return 0.0
        return SequenceMatcher(None, na, nb).ratio()

    def _shared_long_segment(self, text: str, recent: list[str]) -> str:
        pieces = [
            p.strip(" .,!?:;—-")
            for p in re.split(r"[.!?\n]+", text)
            if len(p.strip()) >= 28
        ]
        for piece in pieces:
            piece_norm = self._norm(piece)
            if len(piece_norm) < 28:
                continue
            for old in recent:
                if piece_norm and piece_norm in self._norm(old):
                    return piece
        return ""
