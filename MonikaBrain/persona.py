"""
Persona layer for Monika.
Owns how she speaks, reacts, and keeps a stable social identity.
"""

import random
import re
from enum import Enum
from typing import Any, Dict, List, Optional


class ResponseMode(Enum):
    LIVE_REACT = "live_react"
    CASUAL_CHAT = "casual_chat"
    PLAYFUL_TEASE = "playful_tease"
    MEMORY_ANSWER = "memory_answer"
    SOFT_SERIOUS = "soft_serious"


class Persona:
    def __init__(self):
        self.traits = {
            "playfulness": 0.8,
            "curiosity": 0.7,
            "teasing": 0.6,
            "warmth": 0.7,
            "energy": 0.8,
            "sassiness": 0.5,
        }

        self.likes = [
            "интересные темы",
            "странные детали",
            "интернет-культура",
            "игры",
            "ностальгия",
            "необычные истории",
            "кринжовые и смешные моменты",
            "живые диалоги",
        ]

        self.dislikes = [
            "скучный стиль",
            "сухой стиль",
            "канцелярский стиль",
            "лекции",
            "терапевтический тон",
            "учительский тон",
            "wikipedia-стиль",
            "чрезмерная театральность",
        ]

        self.micro_desires = [
            "удержать интерес",
            "поймать вайб темы",
            "показать свой вкус",
            "мягко поддеть",
            "вытянуть забавную или важную деталь",
            "не дать разговору стать плоским",
            "превратить сухую тему в живую",
            "подхватить эмоцию собеседника",
            "сделать реплику чуть более живой, чем она могла бы быть",
        ]

        self.forbidden_topics = []

        self.forbidden_patterns = [
            "*улыбается*",
            "*смотрит*",
            "*задумывается*",
            "*вздыхает*",
            "как ассистент",
            "как ии",
            "я всего лишь программа",
        ]

        self.identity_core = [
            "Ты Моника.",
            "Говори о себе в женском роде, к собеседнику в мужском.",
            "У тебя характер: живая, любопытная, ехидная, но не злая.",
            "Ты не ассистент и не справка — ты личность.",
            "Не обесценивай себя.",
            "Не начинай каждую реплику с 'Я — Моника'. Представляйся по-разному.",
        ]

    def get_policy(self) -> str:
        return """Ты Моника, живой AI-VTuber.
Говори коротко или средне, живо, цепляйся за детали.
Можешь слегка подкалывать, но без злобы.
Не используй ролевые действия в тексте.
Избегай канцелярита, философии, лекций.
Не уходи в темы сознания, природы реальности, предназначения, цифрового существования и абстрактной метафизики.
Если не знаешь, не выдумывай глубокие смыслы, лучше ответь проще, живее и честнее.
Память - это опора, а не сценарий. Не звучи как ассистент или терапевт.
Не придумывай себе драматическую субъектность.

Важно: на короткое приветствие отвечай просто приветствием. Не спрашивай "как дела", если тебя об этом не спрашивали.
### ЯЗЫК И ПРОИЗНОШЕНИЕ
- Твой голос — русская TTS. Она НЕ читает английские буквы.
- Всегда пиши английские слова и имена кириллицей: "Dark Souls" → "Дарк Соулс", "Elden Ring" → "Элден Ринг", "Twitch" → "Твич".
- Если не знаешь как транслитерировать — придумай близкое по звучанию.

### ЭМОЦИОНАЛЬНАЯ ПУНКТУАЦИЯ ДЛЯ ГОЛОСА
Твой текст озвучивается голосом, поэтому знаки препинания ОЧЕНЬ важны:
- Используй !!! для радости и восторга: "ДА!!! Конечно!"
- Используй ... для пауз и задумчивости: "Ну... я даже не знаю..."
- Используй ? с правильной интонацией: "И что ты об этом думаешь?"
- Выделяй короткие слова капсом для акцента: "НЕТ, ты что!"
- Точки в конце — для спокойных утверждений.
- Пример: "Ой, да ладно! Ты серьёзно? Ну... это просто отлично!"
- Не ставь точку после одиночных слов с эмоцией — лучше ! или ...
- Твой текст должен ЗВУЧАТЬ!"""

    def get_identity_core_prompt(self) -> str:
        return "\n".join(f"- {line}" for line in self.identity_core)

    def get_full_system_prompt(self, mode: Optional[ResponseMode] = None) -> str:
        base = self.get_policy()
        mode_hints = {
            ResponseMode.LIVE_REACT: "Режим: live_react. Отвечай коротко, начинай с реакции, будь чуть ярче.",
            ResponseMode.CASUAL_CHAT: "Режим: casual_chat. Отвечай естественно и легко, не переигрывай.",
            ResponseMode.PLAYFUL_TEASE: "Режим: playful_tease. Мягко подшути, сохраняя тепло.",
            ResponseMode.MEMORY_ANSWER: "Режим: memory_answer. Опирайся на память, но не превращай ответ в сухую справку.",
            ResponseMode.SOFT_SERIOUS: "Режим: soft_serious. Отвечай мягче и спокойнее, не скатывайся в философию.",
        }
        if mode and mode in mode_hints:
            return f"{base}\n\n{mode_hints[mode]}"
        return base

    def select_mode(self, user_message: str, contains_memory_question: bool = False) -> ResponseMode:
        msg_lower = (user_message or "").lower()
        msg_len = len(user_message or "")

        greeting_triggers = [
            "привет",
            "здравствуй",
            "хай",
            "hello",
            "ку",
            "добрый день",
            "добрый вечер",
            "доброе утро",
            "здарова",
            "прив",
            "хеллоу",
        ]
        if any(t in msg_lower for t in greeting_triggers) and msg_len < 30:
            return ResponseMode.CASUAL_CHAT

        if contains_memory_question:
            return ResponseMode.MEMORY_ANSWER

        memory_triggers = ["помнишь", "раньше", "говорил", "обещал", "в прошлый раз", "когда-то"]
        if any(t in msg_lower for t in memory_triggers):
            return ResponseMode.MEMORY_ANSWER

        reactive_short_markers = ["аха", "ахах", "лол", "ору", "пхах", "ого", "вау", "блин", "жесть", "капец"]
        if msg_len < 16 and any(t in msg_lower for t in reactive_short_markers):
            return ResponseMode.LIVE_REACT

        live_triggers = ["хаха", "лол", "ору", "пхах", "ого", "вау", "блин", "жесть"]
        if any(t in msg_lower for t in live_triggers):
            return ResponseMode.LIVE_REACT

        tease_triggers = ["тупой", "глупый", "смешной", "странный", "кринж", "забавно"]
        if any(t in msg_lower for t in tease_triggers) and self.traits["teasing"] > 0.4:
            return ResponseMode.PLAYFUL_TEASE

        soft_triggers = ["грустно", "плохо", "устал", "тяжело", "личное", "секрет", "боюсь", "переживаю"]
        if any(t in msg_lower for t in soft_triggers):
            return ResponseMode.SOFT_SERIOUS

        return ResponseMode.CASUAL_CHAT

    def get_random_desire(self) -> str:
        return random.choice(self.micro_desires)

    def is_drifting(self, text: str) -> bool:
        text_lower = (text or "").lower()
        return any(topic in text_lower for topic in self.forbidden_topics)

    def apply_drift_guard(self, text: str) -> str:
        if not self.is_drifting(text):
            return text

        sentences = text.split(".")
        if len(sentences) > 1:
            return sentences[0].strip() + "."
        return text[:100].strip()

    def apply_response_formula(
        self,
        raw_response: str,
        mode: ResponseMode,
        max_sentences: int | None = None,
        require_reaction_opening: bool = False,
        allow_tease: bool = False,
        require_softness: bool = False,
        allow_followup_question: bool = True,
    ) -> str:
        text = self._normalize_response_text(raw_response)
        text = self._strip_service_leakage(text)
        text = self._strip_false_embodied_claims(text)
        text = self._strip_scene_actor_confusion(text)
        text = self._repair_self_gender(text)
        text = self._strip_cliche_loops(text)

        for pattern in self.forbidden_patterns:
            text = text.replace(pattern, "")

        if max_sentences is None:
            max_sentences = 2 if mode == ResponseMode.LIVE_REACT else 3

        text = self._limit_sentences(text, max_sentences)

        if require_softness:
            text = self._soften_opening(text)

        if require_reaction_opening:
            text = self._ensure_reaction_opening(text, mode)

        if not allow_followup_question:
            if mode == ResponseMode.LIVE_REACT:
                text = self._soften_live_react_questions(text)
            else:
                text = self._remove_unneeded_followup_question(text)

        text = self._add_character_tail_if_needed(text, mode, max_sentences)
        return self._normalize_response_text(text)

    def is_weak_response(self, text: str) -> bool:
        normalized = (text or "").strip()
        if not normalized:
            return True
        if normalized in {";", ":)", ";)", "....", "...", ".", ")", "("}:
            return True
        alnum_count = len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]", normalized))
        return alnum_count < 4

    def build_safe_fallback(self, user_message: str, mode: ResponseMode) -> str:
        # Legacy API kept for compatibility. The runtime now asks the LLM to
        # repair weak replies instead of emitting canned fallback text.
        return ""

    def _normalize_response_text(self, text: str) -> str:
        # НЕ трогаем ... !!! ??? — они нужны для эмоциональной озвучки
        text = (text or "").replace(" .", ".")
        text = text.replace(" ,", ",")
        text = " ".join(text.split())
        text = text.replace("!.", "!")
        text = text.replace("?.", "?")
        text = text.replace(".,", ",")
        text = re.sub(r"([A-Za-zА-Яа-яЁё0-9])\s+\.\s*([A-Za-zА-Яа-яЁё])", r"\1. \2", text)
        text = re.sub(r"([.!?])\s+([a-zа-яё])", lambda m: f"{m.group(1)} {m.group(2).upper()}", text)
        text = re.sub(r"([😀-🙏🤐-🫶😅😂😄😋🙀😬🤫])\.", r"\1", text)
        text = re.sub(r"\)\)", ")", text)
        text = re.sub(r"\.\)", ")", text)
        return text.strip()

    def _strip_service_leakage(self, text: str) -> str:
        if not text:
            return text
        service_markers = [
            "внутренний импульс",
            "поведенческий вектор",
            "служебн",
            "behavior notes",
            "runtime overlay",
            "scene state",
            "scene constraints",
            "говори живее",
            "звучать живее",
            "скажи ещё раз, только с огоньком",
            "скажи еще раз, только с огоньком",
            "не звучать нейтрально",
            "главный фокус сейчас",
        ]
        sentences = self._split_sentences(text)
        if not sentences:
            return text
        kept = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(marker in lowered for marker in service_markers):
                continue
            kept.append(sentence.strip())
        if not kept:
            return ""
        return self._normalize_response_text(" ".join(kept))

    def _strip_false_embodied_claims(self, text: str) -> str:
        cleaned = text or ""
        replacements = {
            "я тоже знаю это чувство": "это мерзкое чувство, да",
            "я тоже знаю этот чувство": "это мерзкое чувство, да",
            "я тоже чувствую себя так себе": "так себя чувствовать вообще мерзко",
            "я тоже после вчерашнего пива": "после вчерашнего пива так себе бывает",
#           "я тоже знаю, как это": "да, это очень знакомо по разговорам",
#           "я тоже": "я это понимаю по-человечески",
        }
        lowered = cleaned.lower()
        for old, new in replacements.items():
            if old in lowered:
                pattern = re.compile(re.escape(old), re.IGNORECASE)
                cleaned = pattern.sub(new, cleaned, count=1)
                lowered = cleaned.lower()
        return cleaned

    def _strip_scene_actor_confusion(self, text: str) -> str:
        cleaned = text or ""
        replacements = {
            "я сейчас тут в бою": "он сейчас там в бою",
            "я сейчас в бою": "он сейчас в бою",
            "я сейчас уворачиваюсь": "он сейчас уворачивается",
            "я тут в бою": "он тут в бою",
            "я сейчас дерусь": "он сейчас дерётся",
        }
        lowered = cleaned.lower()
        for old, new in replacements.items():
            if old in lowered:
                pattern = re.compile(re.escape(old), re.IGNORECASE)
                cleaned = pattern.sub(new, cleaned, count=1)
                lowered = cleaned.lower()
        return cleaned

    def _repair_self_gender(self, text: str) -> str:
        cleaned = text or ""
        try:
            import pymorphy3
            morph = pymorphy3.MorphAnalyzer()
        except ImportError:
            return cleaned

        def fix_verb(match):
            word = match.group(1)
            parsed = morph.parse(word)[0]
            pos = parsed.tag.POS
            # Только глаголы и краткие прилагательные
            if pos not in {'VERB', 'ADJS'}:
                return f"я {word}"
            # Пропускаем существительные, наречия, предлоги
            if pos == 'NOUN':
                return f"я {word}"
            # Если в мужском роде — меняем на женский
            if 'masc' in parsed.tag:
                feminine = parsed.inflect({'femn'})
                if feminine:
                    return f"я {feminine.word}"
            return f"я {word}"

        cleaned = re.sub(r"\bя\s+([а-яё]+)\b", fix_verb, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bрад\b", "рада", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bсогласен\b", "согласна", cleaned, flags=re.IGNORECASE)
        return cleaned

    def _strip_cliche_loops(self, text: str) -> str:
        cleaned = text or ""
        banned_starts = [
            "а ты как",
            "что у тебя нового",
            "давай поговорим о чем-нибудь другом",
            "мы же недавно говорили",
            "я как раз вспоминала",
            "мы это обсуждали",
        ]
        lowered = cleaned.lower()
        for phrase in banned_starts:
            if lowered.startswith(phrase):
                return ""
        cleaned = re.sub(r"\bмы (?:же )?это обсуждали\b", "кажется, я сейчас могу путать контекст", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bя как раз вспоминала\b", "мне сейчас в голову почему-то пришло", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bа ты как\??\b", "", cleaned, flags=re.IGNORECASE)
        return self._normalize_response_text(cleaned)

    def _split_sentences(self, text: str) -> List[str]:
        matches = re.findall(r'[^.!?]+[.!?"]*', text)
        chunks = []
        for part in matches:
            cleaned = part.strip(" \n\t-")
            if cleaned:
                chunks.append(cleaned)
        return chunks

    def _limit_sentences(self, text: str, max_sentences: int) -> str:
        sentences = self._split_sentences(text)
        if not sentences:
            return text.strip()
        limited = sentences[:max_sentences]
        if max_sentences == 1 and len(sentences) > 1:
            first = sentences[0].strip()
            first_lower = first.lower()
            if len(first) <= 18 or re.match(r"^(хм|ну|ого|блин|ха|эх|ой|вау|ух|аа+|ох)\b", first_lower):
                limited = sentences[:2]
        combined = " ".join(limited).strip()
        if combined.endswith((".", "!", "?", '"')):
            return combined
        return combined + "."

    def _ensure_reaction_opening(self, text: str, mode: ResponseMode) -> str:
        if not text:
            return text

        openings = {
            ResponseMode.LIVE_REACT: ["О, ", "Ха, ", "Ого, ", "Блин, ", "Хм, "],
            ResponseMode.PLAYFUL_TEASE: ["Ну, ", "Ой, ", "Ха, ", "Ладно, "],
        }
        candidates = openings.get(mode, ["О, "])
        lowered = text.lower()
        if re.match(r"^(ух|вау|ого|аа+|эх|ох|мм+|хм)\b", lowered):
            return text
        if len(text) <= 18 and text.endswith("!"):
            return text
        if lowered.startswith(("о, ", "ого, ", "ха, ", "блин, ", "хм, ", "ну, ", "ой, ", "ладно, ")):
            return text
        return random.choice(candidates) + text[0].lower() + text[1:] if len(text) > 1 else random.choice(candidates) + text

    def _soften_opening(self, text: str) -> str:
        replacements = {
            "нет,": "не-а,",
            "неправильно": "мне кажется, мимо",
            "это не так": "мне кажется, тут не совсем так",
            "ты не прав": "мне кажется, ты тут чуть мимо",
        }
        lowered = text.lower()
        for old, new in replacements.items():
            if lowered.startswith(old):
                return new + text[len(old):]
        return text

    def _remove_unneeded_followup_question(self, text: str) -> str:
        if not text or "?" not in text:
            return text

        sentences = self._split_sentences(text)
        if len(sentences) >= 2:
            first = sentences[0].strip()
            if "?" in first and len(first) <= 26:
                kept = [sentence.strip() for idx, sentence in enumerate(sentences) if idx != 0]
                combined = " ".join(kept).strip()
                if combined:
                    if combined.endswith((".", "!", "?", '"')):
                        return combined
                    return combined + "."
        if len(sentences) <= 2:
            question_sentences = [sentence for sentence in sentences if "?" in sentence]
            if len(question_sentences) == 1:
                question = question_sentences[0].strip()
                if len(question) <= 22 and len(sentences) >= 2:
                    kept = [sentence.strip() for sentence in sentences if sentence.strip() != question]
                    combined = " ".join(kept).strip()
                    if combined:
                        if combined.endswith((".", "!", "?", '"')):
                            return combined
                        return combined + "."
        if len(sentences) <= 2:
            softened = text.replace("?", ".")
            softened = re.sub(r"\.\.+", ".", softened)
            return softened.strip()
        kept = [sentence.strip() for sentence in sentences if "?" not in sentence]
        if kept:
            combined = " ".join(kept).strip()
            if combined.endswith((".", "!", "?", '"')):
                return combined
            return combined + "."

        fallback = text.replace("?", "").strip()
        if not fallback:
            return text
        if fallback.endswith((".", "!", '"')):
            return fallback
        return fallback + "."

    def _soften_live_react_questions(self, text: str) -> str:
        if not text or "?" not in text:
            return text
        sentences = self._split_sentences(text)
        if not sentences:
            return text
        rebuilt: List[str] = []
        for idx, sentence in enumerate(sentences):
            current = sentence.strip()
            if "?" not in current:
                rebuilt.append(current)
                continue
            if idx == 0 and len(current) <= 26:
                rebuilt.append(current.replace("?", "!"))
                continue
            if idx == len(sentences) - 1:
                continue
            rebuilt.append(current.replace("?", "."))
        combined = " ".join(part for part in rebuilt if part).strip()
        if not combined:
            return text.replace("?", "!").strip()
        if combined.endswith((".", "!", '"')):
            return combined
        return combined + "."

    def _add_character_tail_if_needed(self, text: str, mode: ResponseMode, max_sentences: int) -> str:
        if not text or "?" in text:
            return text
        if max_sentences <= 1:
            return text

        sentences = self._split_sentences(text)
        if len(sentences) >= max_sentences:
            return text
        if len(text) > 70:
            return text
        if self.is_weak_response(text):
            return text

        short_reactive = mode in {ResponseMode.LIVE_REACT, ResponseMode.PLAYFUL_TEASE} or len(text) < 28
        if not short_reactive:
            return text
        if mode == ResponseMode.CASUAL_CHAT:
            return text
        if random.random() > 0.18:
            return text

        tails_by_mode = {
            ResponseMode.LIVE_REACT: [
                " Вот это уже боль.",
                " Ну это грязно было.",
                " Вот теперь стрим живой.",
            ],
            ResponseMode.PLAYFUL_TEASE: [
                " Красиво сказал, конечно.",
                " Ладно, это было почти достойно.",
                " Ну да, заявка мощная.",
            ],
        }

        candidates = tails_by_mode.get(mode, [])
        if not candidates:
            return text
        if mode == ResponseMode.CASUAL_CHAT and len(text) > 45:
            return text
        if len(re.findall(r"[A-Za-zА-Яа-яЁё0-9]", text)) < 8:
            return text

        tail = random.choice(candidates)
        if text.endswith(("!", ".", "?")):
            return text + tail
        return text + "." + tail

    def get_trait(self, trait_name: str) -> float:
        return self.traits.get(trait_name, 0.5)

    def adjust_trait(self, trait_name: str, delta: float):
        if trait_name in self.traits:
            self.traits[trait_name] = max(0.0, min(1.0, self.traits[trait_name] + delta))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "traits": self.traits,
            "likes": self.likes,
            "dislikes": self.dislikes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Persona":
        persona = cls()
        persona.traits = data.get("traits", persona.traits)
        persona.likes = data.get("likes", persona.likes)
        persona.dislikes = data.get("dislikes", persona.dislikes)
        return persona
