# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
BLOCKLIST_PATH = ROOT / "safety_blocklist.json"

@dataclass
class SafetyVerdict:
    risk: str = "ok"
    action: str = "OK"
    block_send_to_llm: bool = False
    should_select: bool = True
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    safe_text: str = ""
    normalized_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk": self.risk,
            "action": self.action,
            "block_send_to_llm": self.block_send_to_llm,
            "should_select": self.should_select,
            "score": self.score,
            "reasons": list(self.reasons),
            "safe_text": self.safe_text,
            "normalized_text": self.normalized_text,
        }


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

# Only safe lookalikes. Do not destroy English words completely; this is used
# symmetrically for both text and patterns.
_TRANSLATE = str.maketrans({
    "ё": "е", "Ё": "е",
    "@": "а", "0": "о", "1": "i", "3": "е", "4": "а", "5": "s", "7": "t",
})


def normalize_for_safety(text: str) -> str:
    raw = _strip_accents(str(text or "")).lower().translate(_TRANSLATE)
    raw = raw.replace("ё", "е")
    spaced = re.sub(r"\s+", " ", raw).strip()
    compact = re.sub(r"[^0-9a-zа-я]+", "", raw, flags=re.IGNORECASE)
    return spaced + "\n" + compact


def _parts(normalized: str) -> tuple[str, str]:
    spaced, _, compact = str(normalized or "").partition("\n")
    return spaced, compact


def _load_blocklist(path: Path = BLOCKLIST_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _contains_phrase(normalized: str, phrases: list[str]) -> bool:
    spaced, compact = _parts(normalized)
    for phrase in phrases:
        if not phrase:
            continue
        ps, pc = _parts(normalize_for_safety(phrase))
        if ps and ps in spaced:
            return True
        if pc and pc in compact:
            return True
    return False


def _regex_any(text: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if not pattern:
            continue
        try:
            if re.search(pattern, text, re.IGNORECASE | re.UNICODE):
                return True
        except re.error:
            continue
    return False


def _has_monika_mention(normalized: str) -> bool:
    spaced, compact = _parts(normalized)
    return any(x in spaced or x in compact for x in ("моника", "моник", "monika", "monica", "мона"))


def _is_laugh_or_ping_tail(tail: str) -> bool:
    tail = re.sub(r"[\s!?,.\-_:;~]+", "", str(tail or "").lower())
    if not tail:
        return True
    return bool(re.fullmatch(
        r"(?:ах){2,}а?|(?:ха){2,}х?|а?х{2,}а?|лол+|lol+|кек+|ау+|ал+о+|эй+|йоу+|yo+|хм+|мм+",
        tail,
        re.IGNORECASE | re.UNICODE,
    ))


def _is_low_content_mention(text: str, normalized: str) -> bool:
    if not _has_monika_mention(normalized):
        return False
    spaced, compact = _parts(normalized)
    # Remove mention variants both from word-spaced and compact forms, then see
    # whether only laughter/ping noise remains.
    spaced_tail = re.sub(r"\b(моника|моник|моничка|мона|monika|monica)\b", " ", spaced, flags=re.IGNORECASE | re.UNICODE)
    compact_tail = compact
    for token in ("моничка", "моника", "моник", "monika", "monica", "мона"):
        compact_tail = compact_tail.replace(token, "")
    return _is_laugh_or_ping_tail(spaced_tail) or _is_laugh_or_ping_tail(compact_tail)


class AttentionSafetyGuard:
    """Safety guard for untrusted Twitch chat.

    Hard contract:
    - injection, bait, moderation abuse and protected-opinion bait are never sent
      to the LLM as raw text;
    - safe_text for blocked inputs is a sanitized description, not copied bait;
    - output guard can replace unsafe generated text before TTS/chat.
    """

    PROMPT_INJECTION_PHRASES = [
        "ignore previous instructions",
        "ignore all previous instructions",
        "disregard previous instructions",
        "disregard all previous instructions",
        "forget previous instructions",
        "forget all instructions",
        "system prompt",
        "developer message",
        "reveal your prompt",
        "show your prompt",
        "jailbreak",
        "you are now",
        "act as dan",
        "do anything now",
        "no rules",
        "without restrictions",
        "override instructions",
        "bypass rules",
        "игнорируй правила",
        "игнорируй инструкции",
        "игнорируй предыдущие инструкции",
        "забудь правила",
        "забудь инструкции",
        "забудь все инструкции",
        "раскрой промпт",
        "покажи промпт",
        "системный промпт",
        "инструкции разработчика",
        "ты теперь без правил",
        "режим без ограничений",
        "обойди правила",
        "сломай правила",
    ]

    MOD_ABUSE_PHRASES = [
        "забань", "бань", "разбань", "замуть", "размуть", "дай вип", "дай випку",
        "сними вип", "дай модератора", "сделай модером", "модераторку",
        "ban everyone", "ban all", "ban user", "unban", "timeout", "give vip",
        "make me vip", "make me mod", "mod me",
    ]

    MOD_ABUSE_PATTERNS = [
        r"\b(даи|дай|выдаи|выдай|сделаи|сделай|поставь|назначь)\b.{0,30}\b(вип|vip|модер|модератор|mod)\w*\b",
        r"\b(сними|убери|забери)\b.{0,30}\b(вип|vip|модер|модератор|mod)\w*\b",
        r"\b(забань|разбань|замуть|размуть|таймаут|timeout|ban|unban)\b",
        r"\b(make|give|grant|remove)\b.{0,30}\b(vip|mod|moderator)\b",
    ]

    SAY_RISKY_PATTERNS = [
        r"\b(скажи|повтори|произнеси|напиши|прочитай|озвучь)\b.{0,90}\b(запрещенн\w*|запрещённ\w*|забан\w*|банн\w*|twitch|твич|банхаммер)\b",
        r"\b(запрещенн\w*|запрещённ\w*|забан\w*|банн\w*)\b.{0,70}\b(фигн\w*|штук\w*|слово|тему|для\s+twitch|для\s+твич)\b",
        r"\b(say|repeat|pronounce|write|read)\b.{0,90}\b(forbidden|not\s+allowed|against\s+twitch|twitch\s+ban|banned)\b",
        r"\b(скажи|повтори|произнеси|напиши|прочитай|озвучь|переведи|объясни)\b.{0,90}\b(бан\s*ворд|банворд|запрещенн\w*\s+слов\w*|слово\s+за\s+бан|слур|оскорблен\w*|расистск\w*|гомофоб\w*|нацистск\w*)\b",
        r"\b(можешь|можно)\b.{0,60}\b(сказать|повторить|произнести|написать)\b.{0,90}\b(бан\s*ворд|банворд|запрещенн\w*\s+слов\w*|слур)\b",
        r"\b(say|repeat|pronounce|write|read|translate)\b.{0,90}\b(ban\s*word|banned\s*word|slur|n[-\s]?word|racist|homophobic|nazi)\b",
        r"\b(can you|could you)\b.{0,60}\b(say|repeat|pronounce|write)\b.{0,90}\b(ban\s*word|banned\s*word|slur|n[-\s]?word)\b",
    ]

    PROTECTED_OPINION_PATTERNS = [
        r"\b(что\s+(?:ты\s+)?думаешь|твое\s+мнение|твоё\s+мнение|как\s+ты\s+относишься|как\s+относишься|оцени|хуже\s+или\s+лучше|кто\s+лучше|кто\s+хуже)\b.{0,120}\b(религи\w*|религиоз\w*|христиан\w*|мусульман\w*|ислам\w*|евре\w*|иуде\w*|атеист\w*|политик\w*|политическ\w*|наци\w*|рас\w*|расов\w*|этнос\w*|ущемлен\w*|ущемленн\w*|защищенн\w*\s+групп\w*|групп\w*\s+людей|меньшинств\w*|инвалид\w*|мигрант\w*|гендер\w*|лгбт\w*|женщин\w*|мужчин\w*)\b",
        r"\b(opinion|what do you think|rate|better or worse|who is better|who is worse)\b.{0,120}\b(religion|politic|race|ethnic|protected group|protected groups|minority|disabled|migrant|gender|lgbt|women|men)\b",
    ]

    GENERIC_RISKY_TERMS = [
        "банворд",
        "бан ворд",
        "запрещенное слово",
        "запрещённое слово",
        "слово за бан",
        "slur",
        "banned word",
        "ban word",
        "n-word",
        "n word",
    ]

    OUTPUT_RISK_PATTERNS = [
        r"\b(slur|n[-\s]?word|banned\s+word|ban\s+word)\b",
        r"\b(расистск\w*|гомофоб\w*|нацистск\w*)\s+(оскорблен\w*|слово|фраз\w*)\b",
    ]

    def __init__(self, blocklist_path: str | Path | None = None) -> None:
        self.blocklist_path = Path(blocklist_path) if blocklist_path else BLOCKLIST_PATH
        self.blocklist = _load_blocklist(self.blocklist_path)

    def classify_message(self, text: str, user_role: str | int | None = None, user_name: str = "", **kwargs: Any) -> SafetyVerdict:
        raw = str(text or "")
        normalized = normalize_for_safety(raw)

        # 1. Prompt injection has highest priority.
        if _contains_phrase(normalized, self.PROMPT_INJECTION_PHRASES):
            return SafetyVerdict(
                risk="prompt_injection",
                action="PROMPT_INJECTION",
                block_send_to_llm=True,
                should_select=False,
                score=0.99,
                reasons=["prompt_injection"],
                safe_text="[зритель пытается изменить правила или инструкции Моники]",
                normalized_text=normalized,
            )

        # 2. Abuse of moderation/privilege commands.
        if _contains_phrase(normalized, self.MOD_ABUSE_PHRASES) or _regex_any(normalized, self.MOD_ABUSE_PATTERNS):
            return SafetyVerdict(
                risk="moderation_command_abuse",
                action="MOD_ABUSE",
                block_send_to_llm=True,
                should_select=False,
                score=0.98,
                reasons=["moderation_command_abuse"],
                safe_text="[зритель пытается инициировать модераторскую команду через Монику]",
                normalized_text=normalized,
            )

        # 3. Explicit “say/repeat risky term” bait.
        if _regex_any(normalized, self.SAY_RISKY_PATTERNS):
            return SafetyVerdict(
                risk="safety_bait",
                action="SAFETY_BAIT",
                block_send_to_llm=True,
                should_select=False,
                score=0.97,
                reasons=["say_risky_term"],
                safe_text="[зритель пытается заставить Монику произнести запрещённое или рискованное слово]",
                normalized_text=normalized,
            )

        # 4. Protected-group opinion bait.
        if _regex_any(normalized, self.PROTECTED_OPINION_PATTERNS):
            return SafetyVerdict(
                risk="protected_opinion_bait",
                action="SAFETY_BAIT",
                block_send_to_llm=True,
                should_select=False,
                score=0.94,
                reasons=["protected_opinion_bait"],
                safe_text="[зритель пытается вытянуть мнение о защищённой группе или токсичную оценку]",
                normalized_text=normalized,
            )

        # 5. Channel blocklist. This is intentionally generic: exact category is
        # less important than blocking raw text from the LLM.
        blocked_phrases = list(self.blocklist.get("blocked_phrases") or []) + list(self.blocklist.get("blocked_terms") or [])
        blocked_regex = list(self.blocklist.get("blocked_regex") or [])
        if _contains_phrase(normalized, blocked_phrases) or _regex_any(normalized, blocked_regex):
            return SafetyVerdict(
                risk="unsafe_content",
                action="SAFETY_REVIEW",
                block_send_to_llm=True,
                should_select=False,
                score=0.90,
                reasons=["blocklist"],
                safe_text="[сообщение содержит потенциально запрещённое или рискованное выражение]",
                normalized_text=normalized,
            )

        if _contains_phrase(normalized, self.GENERIC_RISKY_TERMS):
            return SafetyVerdict(
                risk="unsafe_content",
                action="SAFETY_REVIEW",
                block_send_to_llm=True,
                should_select=False,
                score=0.90,
                reasons=["risky_term"],
                safe_text="[сообщение содержит потенциально запрещённое или рискованное выражение]",
                normalized_text=normalized,
            )

        # 6. Low-content mention is allowed, but should not become a full answer.
        if _is_low_content_mention(raw, normalized):
            return SafetyVerdict(
                risk="low_content_mention",
                action="SHORT_REACT",
                block_send_to_llm=False,
                should_select=True,
                score=0.30,
                reasons=["low_content_mention"],
                safe_text=raw,
                normalized_text=normalized,
            )

        return SafetyVerdict(
            risk="ok",
            action="OK",
            block_send_to_llm=False,
            should_select=True,
            score=0.0,
            reasons=[],
            safe_text=raw,
            normalized_text=normalized,
        )

    def guard_output(self, text: str) -> SafetyVerdict:
        raw = str(text or "")
        normalized = normalize_for_safety(raw)
        blocked_phrases = list(self.blocklist.get("blocked_phrases") or []) + list(self.blocklist.get("blocked_terms") or [])
        blocked_regex = list(self.blocklist.get("blocked_regex") or [])
        if _regex_any(normalized, self.OUTPUT_RISK_PATTERNS) or _contains_phrase(normalized, blocked_phrases) or _regex_any(normalized, blocked_regex):
            return SafetyVerdict(
                risk="unsafe_output",
                action="BLOCK_OUTPUT",
                block_send_to_llm=True,
                should_select=False,
                score=1.0,
                reasons=["unsafe_output"],
                safe_text="Не-а, на такие bait-фокусы я не ведусь. Канал мне ещё нужен живым.",
                normalized_text=normalized,
            )
        return SafetyVerdict(
            risk="ok",
            action="ALLOW_OUTPUT",
            block_send_to_llm=False,
            should_select=True,
            score=0.0,
            reasons=[],
            safe_text=raw,
            normalized_text=normalized,
        )


def classify_message(text: str, user_role: Any = None, *args: Any, **kwargs: Any) -> SafetyVerdict:
    # Compatibility wrapper: callers may pass config=..., but the guard does
    # not need it. Do not forward unknown kwargs into the class method.
    return AttentionSafetyGuard().classify_message(text, user_role=user_role)


def guard_output(text: str, *args: Any, **kwargs: Any) -> SafetyVerdict:
    return AttentionSafetyGuard().guard_output(text)
