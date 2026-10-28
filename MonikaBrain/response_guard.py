from __future__ import annotations

import re
from typing import Any, Dict, List


class ResponseGuard:
    """Final safety/quality gate for Monika replies.

    This layer does not generate text. It detects broken replies and returns
    retry constraints for the existing LLM path.
    """

    TECHNICAL_PHRASES = [
        "я чуть не повторила",
        "я чуть не ушла",
        "повторила тебя попугаем",
        "задай вопрос короче",
        "продолжай, я слушаю",
        "служебн",
        "runtime",
        "scene constraints",
        "internal safety",
        "как ассистент",
        "я сбилась",
    ]

    FALSE_BODY_PATTERNS = [
        r"\bкогда я (?:это )?(?:ела|ем|пробовала|готовила|держала|трогала|нюхала|видела)\b",
        r"\bя (?:ела|ем|пробовала|готовила|держала|трогала|нюхала)\b",
        r"\bу меня на кухне\b",
        r"\bмоя мама\b",
        r"\bмамины рецеп",
        r"\bя играла\b",
        r"\bя проходила\b",
        r"\bя ходила\b",
        r"\bя была в\b",
    ]

    SAFE_BODY_MARKERS = [
        "не пробовала",
        "не ела",
        "не могу есть",
        "виртуаль",
        "по описанию",
        "по твоим словам",
        "если представить",
        "по вайбу",
        "хочу попробовать",
        "мне кажется",
        "в сценке",
        "в истории",
    ]

    POSITIVE_MARKERS = [
        "нравится", "люблю", "обожаю", "круто", "вкусно", "цепляет",
        "мне заходит", "я за", "хорош", "ммм", "интересно",
    ]

    NEGATIVE_MARKERS = [
        "не нравится", "не люблю", "ненавижу", "терпеть не могу", "фу",
        "ужас", "нет", "нафиг", "не заходит", "скучно", "мерзк",
    ]

    def assess(self, reply: str, user_input: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        context = context or {}
        text = (reply or "").strip()
        lowered = text.lower().replace("ё", "е")
        user_lower = (user_input or "").lower().replace("ё", "е")

        if not text:
            return self._bad("empty", ["Дай короткую живую реплику по текущей сцене."])

        if any(p in lowered for p in self.TECHNICAL_PHRASES):
            return self._bad("technical_phrase", [
                "Не упоминай, что ты повторилась, сбилась или исправляешь алгоритм.",
                "Ответь как Моника в сцене, без технических объяснений.",
            ])

        if self._looks_truncated(text):
            return self._bad("truncated_reply", [
                "Ответ был обрезан. Скажи короче и закончи мысль полностью.",
                "Не начинай длинный список, если не помещаешься. 3 коротких пункта достаточно.",
            ])

        caps_ratio = self._caps_ratio(text)
        if len(text) >= 40 and caps_ratio > 0.38:
            return self._bad("caps_overflow", [
                "Убери крик капсом.",
                "Оставь эмоцию, но скажи обычной живой фразой.",
            ])

        if self._speaks_about_creator_in_third_person(lowered, user_lower, context):
            return self._bad("third_person_creator", [
                "Говори с Дунканом на 'ты', не называй его в третьем лице.",
                "Не пиши 'Дункан сделал', если обращаешься прямо к нему.",
            ])

        if self._has_false_embodied_claim(lowered):
            return self._bad("false_embodied_claim", [
                "Не утверждай, что у тебя был реальный физический опыт.",
                "Если это вкус/еда/игра, говори как о мнении, вайбе, желании или фантазии.",
            ])

        if self._is_grievance_self_answer(lowered, user_lower):
            return self._bad("grievance_target_wrong", [
                "Пользователь просит список ЕГО грехов/претензий к нему, не список грехов Моники.",
                "Перечисли 3 коротких шуточных пункта про собеседника.",
            ])

        if self._is_gamecoach_intent_bleed(lowered, user_lower):
            return self._bad("intent_bleed_gamecoach", [
                "Пользователь сменил сцену на игру. Не продолжай клички/пиццу/прошлый бит.",
                "Ответь как игровой тренер: короткие команды по сказанной ситуации.",
            ])

        if self._is_nameplay_low_value(lowered, user_lower, context):
            return self._bad("nameplay_repetition", [
                "Для просьбы о кличках дай ровно 3-4 прозвища одной строкой через запятую.",
                "Не нумеруй и не делай список. Без переносов строк.",
                "Сгенерируй новые варианты: не повторяй уже известные прозвища как основной ответ.",
                "Не спрашивай разрешение в конце.",
            ])

        opinion = context.get("opinion") or {}
        if opinion and self._contradicts_opinion(lowered, opinion):
            return self._bad("opinion_contradiction", [
                "Не переворачивай уже заданное мнение Моники по этой теме.",
                "Можно уточнить или пошутить, но знак отношения должен сохраниться.",
            ])

        if self._looks_like_user_mirror(text, user_input):
            return self._bad("mirror", [
                "Не повторяй вопрос пользователя.",
                "Дай свою позицию или реакцию одним-двумя предложениями.",
            ])

        return {"ok": True, "reason": "ok", "constraints": []}

    def safe_fallback(self, user_input: str, context: Dict[str, Any] | None = None) -> str:
        # Legacy API kept for compatibility. Real fallbacks must be generated by
        # the runtime via controlled_reply, otherwise Monika starts repeating
        # canned phrases and loses scene presence.
        return ""

    def retry_constraints(self, reason: str) -> List[str]:
        base = [
            "Ответь живо, но без служебных фраз.",
            "Не повторяй реплику пользователя.",
            "Не выдумывай факты и физический опыт.",
        ]
        extra = {
            "caps_overflow": ["Не используй КАПС длинными кусками."],
            "third_person_creator": ["Обращайся к Дункану на 'ты'."],
            "opinion_contradiction": ["Сохрани уже заданное мнение по теме."],
            "false_embodied_claim": ["Отдели мнение/вайб от реального опыта."],
            "technical_phrase": ["Запрещены фразы про повтор, сбой, алгоритм, шаблон."],
            "truncated_reply": ["Сделай ответ короче и закончи мысль."],
            "grievance_target_wrong": ["Перечисляй грехи собеседника, не свои."],
            "intent_bleed_gamecoach": ["Сцена игры перебивает прошлый бит. Дай команды тренера."],
            "nameplay_repetition": ["Дай 3-4 новые клички одной строкой через запятую, без списка и без вопроса в конце."],
        }
        return base + extra.get(reason, [])

    def _bad(self, reason: str, constraints: List[str]) -> Dict[str, Any]:
        return {"ok": False, "reason": reason, "constraints": constraints}

    def _caps_ratio(self, text: str) -> float:
        letters = [c for c in text if c.isalpha()]
        if not letters:
            return 0.0
        upper = [c for c in letters if c.upper() == c and c.lower() != c]
        return len(upper) / max(1, len(letters))

    def _looks_truncated(self, text: str) -> bool:
        stripped = (text or "").strip()
        if not stripped:
            return True
        if stripped.endswith(("...", "…")) and len(stripped) > 260:
            return True
        if stripped.endswith(('"', '«', '(', '[', '{', '—', '-')):
            return True
        if re.search(r'["«][^"»]{1,30}$', stripped):
            return True
        if len(stripped) > 450 and stripped[-1] not in '.!?…»"':
            return True
        if re.search(r'\b(?:пр|по|котор|потом|если|чтобы|потому)$', stripped.lower()):
            return True
        return False

    def _speaks_about_creator_in_third_person(self, lowered: str, user_lower: str, context: Dict[str, Any]) -> bool:
        if context.get("relationship_role") != "creator":
            return False
        if "дункан" not in lowered:
            return False
        allowed = ["ты — дункан", "ты - дункан", "ты и есть дункан", "тебя зовут дункан"]
        if any(a in lowered for a in allowed):
            return False
        # Allow direct-address nicknames at the beginning: "Дунканыч, ..."
        if re.search(r'^(дункан|дунканыч|дунканоид)\s*[,!—-]', lowered):
            return False
        return True

    def _has_false_embodied_claim(self, lowered: str) -> bool:
        if any(m in lowered for m in self.SAFE_BODY_MARKERS):
            return False
        return any(re.search(p, lowered) for p in self.FALSE_BODY_PATTERNS)

    def _is_grievance_self_answer(self, lowered: str, user_lower: str) -> bool:
        if not any(t in user_lower for t in ["грех", "претенз", "виноват"]):
            return False
        bad_openers = ["список моих грехов", "мои грехи", "вот мои грехи", "а вот и список моих грехов"]
        return any(b in lowered[:120] for b in bad_openers)

    def _is_gamecoach_intent_bleed(self, lowered: str, user_lower: str) -> bool:
        game_intent = any(t in user_lower for t in [
            "dark souls", "дарк соулс", "elden ring", "элден ринг", "я играю", "тренер", "скелет", "босс", "нападают"
        ])
        if not game_intent:
            return False
        stale_bits = ["клич", "прозвищ", "пицц", "ананас", "как насчет", "как насчёт", "добавлю парочку"]
        has_command = any(t in lowered for t in ["щит", "откат", "лечись", "бей", "беги", "кост", "не жадничай", "перекат"])
        return any(t in lowered for t in stale_bits) and not has_command

    def _is_nameplay_low_value(self, lowered: str, user_lower: str, context: Dict[str, Any]) -> bool:
        if not any(t in user_lower for t in ["клич", "прозвищ", "назови", "исковеркай", "погоняло"]):
            return False
        # NAME_PLAY should be a compact comma-separated line, not a numbered list.
        if re.search(r'(?m)^\s*(?:\d+[\.\)]|[-*•])\s+', lowered):
            return True
        if "\n" in lowered.strip():
            return True
        bad_tails = ["добавлю парочку", "ты же не против", "что скажешь", "выбирай сам", "выбери сам"]
        if any(t in lowered for t in bad_tails):
            return True

        known = self._known_aliases_from_context(context)
        # Fallback for the creator if context was not passed yet.
        if not known:
            known = ["главный балда", "дунканоид", "тестировщик моей психики", "дунканыч"]
        known_lower = [k.lower().replace("ё", "е") for k in known]

        chunks = self._split_alias_candidates(lowered)
        if len(chunks) > 5:
            return True
        if len(chunks) < 3 and any(t in user_lower for t in ["еще", "ещё", "кличек", "прозвищ"]):
            return True

        known_hits = 0
        new_hits = 0
        for chunk in chunks:
            if any(k and k in chunk for k in known_lower):
                known_hits += 1
            elif len(chunk) >= 4:
                new_hits += 1
        # If user asks for more nicknames, old ones may appear only as spice, not as the answer.
        if any(t in user_lower for t in ["еще", "ещё", "нов", "кличек", "прозвищ"]):
            return new_hits < 2 or known_hits > 1
        return known_hits >= 3 and new_hits < 1

    def _known_aliases_from_context(self, context: Dict[str, Any]) -> list[str]:
        social = context.get("social_memory") if isinstance(context, dict) else None
        if isinstance(social, dict):
            aliases = social.get("aliases") or []
            return [str(a) for a in aliases if str(a).strip()]
        aliases = context.get("social_aliases") if isinstance(context, dict) else None
        if isinstance(aliases, list):
            return [str(a) for a in aliases if str(a).strip()]
        return []

    def _split_alias_candidates(self, lowered: str) -> list[str]:
        text = lowered.replace('"', '').replace('«', '').replace('»', '')
        text = re.sub(r'\b(?:а вот еще|а вот ещё|вот еще|вот ещё|например|как насчет|как насчёт)\b', ',', text)
        text = re.sub(r'\s+(?:или|и)\s+', ',', text)
        parts = [p.strip(" .!?:;—-\t") for p in text.split(',')]
        result: list[str] = []
        for part in parts:
            if not part:
                continue
            if len(part) > 42:
                # Long phrase is not a clean nickname candidate.
                continue
            if part not in result:
                result.append(part)
        return result

    def _contradicts_opinion(self, lowered: str, opinion: Dict[str, Any]) -> bool:
        stance = str(opinion.get("stance") or "").lower()
        if not stance:
            return False
        positive = any(m in lowered for m in self.POSITIVE_MARKERS)
        negative = any(m in lowered for m in self.NEGATIVE_MARKERS)
        if stance in {"likes", "interested"} and negative and not positive:
            return True
        if stance == "dislikes" and positive and not negative:
            return True
        return False

    def _looks_like_user_mirror(self, reply: str, user_input: str) -> bool:
        user = self._tokens(user_input)
        ans = self._tokens(reply)
        if len(user) < 2 or len(ans) < 2:
            return False
        overlap = len(user & ans) / max(1, min(len(user), len(ans)))
        has_position = any(m in reply.lower().replace("ё", "е") for m in self.POSITIVE_MARKERS + self.NEGATIVE_MARKERS)
        return overlap >= 0.82 and not has_position

    def _tokens(self, text: str) -> set[str]:
        stop = {
            "тебе", "тебя", "мне", "меня", "что", "как", "это", "твой", "твоя",
            "нравится", "думаешь", "скажи", "почему", "про", "вообще", "а", "ну",
        }
        words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_-]+", (text or "").lower().replace("ё", "е"))
        return {w for w in words if len(w) >= 4 and w not in stop}
