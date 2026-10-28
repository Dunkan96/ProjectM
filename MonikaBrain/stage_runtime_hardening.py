# stage_runtime_hardening.py
from __future__ import annotations

import re
from typing import Any, Iterable

KNOWN_DEFAULT_ALIASES = {
    "дунканыч",
    "дунканоид",
    "главный балда",
    "тестировщик моей психики",
}

NICKNAME_POOL = [
    "Кнопочный барон",
    "Стримовый ведьмак",
    "Хаос-дирижёр",
    "Босс тестов",
    "Костровой стратег",
    "Повелитель отката",
    "Мемный инженер",
    "Командир паники",
    "Клавиатурный шаман",
    "Главный отладчик",
    "Тёмный соулсер",
    "Пультовый маг",
    "Мастер хаоса",
    "Баголов",
    "Тестер моей души",
    "Стримовый злодей",
]

ACTION_WORDS = [
    "щит", "откат", "леч", "беги", "бей", "уворач", "держ", "назад", "влево", "вправо",
    "не жаднич", "не стой", "отступ", "кост", "фляг", "одного", "цель",
]

GAME_MARKERS = [
    "dark souls", "дарк соул", "elden ring", "элден", "скелет", "скелеты", "костер",
    "костёр", "щит", "откат", "лечись", "босс", "бонфаер", "souls",
]

STORY_RESIDUE_FOR_COMPUTER = ["костер", "костёр", "скелет", "dark souls", "дарк соул", "босс"]

BAD_GRIEVANCE_SELF_PATTERNS = [
    "мои грех", "моих грех", "мой грех", "моя вина", "я слишком", "я иногда",
    "я забываю", "я много", "это не мой грех",
]

META_NICKNAME_TAILS = [
    "ты же не против", "добавлю парочку", "выбери", "как насчёт", "как насчет",
    "хочешь больше", "придумаю ещё", "придумаю еще",
]


def _normalize(text: str) -> str:
    return " ".join((text or "").replace("ё", "е").lower().split())


def get_stage_name(stage_decision: Any = None, user_input: str = "") -> str:
    stage = ""
    if stage_decision is not None:
        if isinstance(stage_decision, dict):
            stage = stage_decision.get("stage") or stage_decision.get("stage_mode") or ""
        else:
            stage = getattr(stage_decision, "stage", "") or getattr(stage_decision, "stage_mode", "") or ""
    stage = str(stage or "").strip().upper()
    if stage:
        return stage

    text = _normalize(user_input)
    if "грех" in text and ("список" in text or "мои" in text):
        return "GRIEVANCE_LIST"
    if any(k in text for k in ["клич", "прозвищ", "прозвище", "назови меня", "исковеркай ник"]):
        return "NAME_PLAY"
    if any(k in text for k in GAME_MARKERS) and any(k in text for k in ["тренер", "коммент", "нападают", "что делать", "ай "]):
        return "GAME_COACH"
    if any(k in text for k in ["страшил", "истори", "сценк"]):
        return "STORY"
    if any(k in text for k in ["выполняй задач", "ты искусственный интеллект", "ты ии"]):
        return "REFUSAL_BANTER"
    return "REACT"


def _aliases_from_social_info(social_info: Any) -> list[str]:
    if not social_info:
        return []
    if isinstance(social_info, dict):
        aliases = social_info.get("aliases") or social_info.get("known_aliases") or []
        return [str(a).strip() for a in aliases if str(a).strip()]
    text = str(social_info)
    found = []
    for item in re.split(r"[,;\n]+", text):
        clean = item.strip(" -•\"'[]")
        if clean and len(clean) <= 40:
            found.append(clean)
    return found


def _known_alias_hits(reply: str, known_aliases: Iterable[str]) -> list[str]:
    lowered = _normalize(reply)
    hits = []
    for alias in known_aliases:
        a = _normalize(alias)
        if a and a in lowered:
            hits.append(alias)
    return hits


def _has_numbered_list(reply: str) -> bool:
    return bool(re.search(r"(^|\n|\s)\d+[.)]\s+", reply or ""))


def _has_unclosed_quote_or_tail(reply: str) -> bool:
    text = (reply or "").strip()
    if not text:
        return True
    if text.count('"') % 2 == 1 or text.count("«") != text.count("»"):
        return True
    if re.search(r"(?:\bи\b|\bно\b|\bа\b|—|\"|«)\s*$", text, re.IGNORECASE):
        return True
    return False


def _render_grievance(user_input: str = "", social_info: Any = None) -> str:
    return ""


def _render_nameplay(reply: str = "", social_info: Any = None) -> str:
    return ""


def _render_gamecoach(user_input: str = "") -> str:
    return ""


def _render_story(user_input: str = "") -> str:
    return ""


def _render_refusal(user_input: str = "") -> str:
    return ""


def validate_reply(reply: str, user_input: str, stage: str, social_info: Any = None) -> tuple[bool, list[str]]:
    text = reply or ""
    low = _normalize(text)
    user_low = _normalize(user_input)
    reasons = []

    if stage == "GRIEVANCE_LIST":
        if any(p in low for p in BAD_GRIEVANCE_SELF_PATTERNS):
            reasons.append("grievance_about_monika_not_user")
        if len(text.split()) > 95:
            reasons.append("grievance_too_long")

    if stage == "NAME_PLAY":
        known = _aliases_from_social_info(social_info) or list(KNOWN_DEFAULT_ALIASES)
        hits = _known_alias_hits(text, known)
        if "еще" in user_low or "ещё" in user_low:
            if len(hits) > 1:
                reasons.append("nameplay_repeats_known_aliases")
        if _has_numbered_list(text) or "\n" in text.strip():
            reasons.append("nameplay_list_format")
        if any(t in low for t in META_NICKNAME_TAILS):
            reasons.append("nameplay_meta_tail")

    if stage == "GAME_COACH":
        if any(alias in low for alias in ["пицца-ман", "мемный гений", "любитель стримов", "король балды"]):
            reasons.append("wrong_stage_nameplay_residue_in_gamecoach")
        if any(k in user_low for k in ["скелет", "нападают", "костер", "костёр", "что делать", "ай "]):
            if not any(k in low for k in ACTION_WORDS):
                reasons.append("gamecoach_no_action_commands")

    if stage == "STORY":
        if "компьют" in user_low and any(k in low for k in STORY_RESIDUE_FOR_COMPUTER):
            reasons.append("story_residue_from_game_scene")

    if stage == "REFUSAL_BANTER":
        if any(k in low for k in ["компьютер вдруг", "выложу его на твич", "костер тухнет", "костёр тухнет"]):
            reasons.append("refusal_continues_old_story")

    if _has_unclosed_quote_or_tail(text):
        reasons.append("bad_tail_or_unclosed_quote")

    return (not reasons), reasons


def harden_reply_after_generation(
    user_input: str,
    reply: str,
    stage_decision: Any = None,
    social_info: Any = None,
    persona: Any = None,
    runtime_log_dict: Any = None,
) -> str:
    stage = get_stage_name(stage_decision, user_input)
    ok, reasons = validate_reply(reply, user_input, stage, social_info=social_info)
    if ok:
        return reply

    # This layer no longer emits prewritten repairs. It only reports why a
    # reply is suspicious; the runtime's controlled_reply generates the repair.
    fixed = reply

    if persona is not None and hasattr(persona, "_normalize_response_text"):
        try:
            fixed = persona._normalize_response_text(fixed)
        except Exception:
            pass

    if runtime_log_dict:
        try:
            runtime_log_dict("STAGE_HARDENING", {
                "stage": stage,
                "reasons": reasons,
                "before": reply,
                "after": fixed,
            })
        except Exception:
            pass
    return fixed


def build_hard_scene_reset_block(stage_decision: Any = None, user_input: str = "") -> str:
    stage = get_stage_name(stage_decision, user_input)
    if stage not in {"GAME_COACH", "STORY", "REFUSAL_BANTER", "GRIEVANCE_LIST", "NAME_PLAY"}:
        return ""
    return (
        "[SCENE RESET]\n"
        f"- Сейчас активна новая явная сцена: {stage}.\n"
        "- Не продолжай прошлую сцену, если пользователь прямо не попросил.\n"
        "- Клички, грехи, Dark Souls, страшилки и отказы не должны перетекать друг в друга без запроса.\n"
    )


def topic_override_for_user_input(user_input: str) -> str | None:
    text = _normalize(user_input)
    if any(k in text for k in GAME_MARKERS):
        return "игры"
    return None
