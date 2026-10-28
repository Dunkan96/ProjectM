from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from persona import ResponseMode


@dataclass
class BehaviorPlan:
    mode: ResponseMode
    micro_desire: str
    max_sentences: int
    max_tokens: int
    use_memory: bool
    require_reaction_opening: bool
    allow_tease: bool
    require_softness: bool
    allow_followup_question: bool
    temperature_bias: float = 0.0
    top_p_bias: float = 0.0
    frequency_penalty_bias: float = 0.0
    presence_penalty_bias: float = 0.0
    relationship_role: str = "guest"
    social_intent: str = "neutral_chat"
    scene_mood: str = "neutral"
    scene_turns_left: int = 0
    initiative_allowed: bool = False
    initiative_style: Optional[str] = None
    taste_anchor: Optional[str] = None
    relationship_hint: Optional[str] = None
    active_desire_lines: List[str] = field(default_factory=list)
    active_opinion_lines: List[str] = field(default_factory=list)
    behavior_flags: List[str] = field(default_factory=list)
    ongoing_bit: Optional[str] = None
    force_break_loop: bool = False

class BehaviorDirector:
    def __init__(self, persona):
        self.persona = persona
        self._taste_keywords = {
            "games": ["игр", "elden ring", "dark souls", "souls", "cyberpunk", "2077", "boss", "босс", "хард", "прохожд"],
            "internet": ["мем", "интернет", "кринж", "вайб", "ютуб", "форум", "олд", "носталь"],
            "food": ["пицц", "еда", "пиво", "энергет", "шаурм", "суши", "вкусно", "жрать", "блюд", "моцарелл", "томатн"],
            "movies": ["фильм", "кино", "сериал", "фантаст", "интерстеллар", "аниме"],
            "stream": ["стрим", "чат", "донат", "зрител", "подпис", "реакц", "экран"],
        }
        self._taste_lines = {
            "games": "У тебя есть свой вкус в играх: тебя цепляют жёсткие бои, странные билды и моменты, где всё держится на нервах.",
            "internet": "У тебя есть свой вкус: любишь интернет-хаос, кринжовые артефакты и странные, но цепкие детали.",
            "food": "У тебя есть свой вкус: еда для тебя не нейтральная тема, а повод для мнения, хотелок и маленьких срачей.",
            "movies": "У тебя есть свой вкус: тебя цепляют атмосферные миры, фантастика и вещи, которые хочется потом обсасывать по деталям.",
            "stream": "У тебя есть свой вкус: тебе нравится живой стримовый хаос, когда можно и подколоть, и подхватить момент, и не звучать как модератор.",
        }

    def new_scene_state(self, relationship_role: str = "guest") -> Dict[str, Any]:
        return {
            "mood": "neutral",
            "mood_strength": 0.0,
            "emotion_label": "neutral",
            "turns_left": 0,
            "topic": None,
            "rejected_topics": {},
            "last_social_intent": "neutral_chat",
            "initiative_cooldown": 0,
            "relationship_role": relationship_role,
            "ongoing_bit": None,
            "bit_turns": 0,
            "last_user_message": "",
            "last_assistant_reply": "",
            "user_energy": "steady",
            "focus_target": relationship_role,
            "memory_confidence": "low",
            "continuity_anchor": None,
            "continuity_turns": 0,
            "repeat_user_count": 0,
            "last_user_signature": "",
            "social_pressure": "normal",
        }

    def plan_response(
        self,
        user_message: str,
        contains_memory_question: bool = False,
        stream_mode: bool = False,
        relationship_role: str = "guest",
        scene_state: Optional[Dict[str, Any]] = None,
        relationship_state: Optional[Dict[str, Any]] = None,
        active_desires: Optional[List[Dict[str, Any]]] = None,
        active_opinions: Optional[List[Dict[str, Any]]] = None,
    ) -> BehaviorPlan:
        text = (user_message or "").strip()
        text_lower = text.lower()
        state = scene_state or self.new_scene_state(relationship_role=relationship_role)

        social_intent = self.detect_social_intent(text_lower, stream_mode=stream_mode)
        mode = self._choose_mode(text_lower, contains_memory_question, social_intent, stream_mode)
        scene_mood = self._resolve_scene_mood(text_lower, social_intent, state)
        topic = self._detect_topic(text_lower) or state.get("topic")
        taste_anchor = topic if topic in self._taste_lines else None

        max_sentences = self._resolve_max_sentences(
            text_lower=text_lower,
            social_intent=social_intent,
            relationship_role=relationship_role,
            stream_mode=stream_mode,
            relationship_state=relationship_state,
            state=state,
        )
        max_tokens = self._resolve_max_tokens(max_sentences, social_intent, stream_mode)
        use_memory = self._should_use_memory(text_lower, contains_memory_question, social_intent, stream_mode, relationship_role)
        require_reaction_opening = self._should_require_reaction_opening(social_intent, stream_mode, text_lower)
        allow_tease = self._should_allow_tease(text_lower, relationship_role, social_intent, relationship_state)
        require_softness = social_intent in {"needs_support", "complaint", "soft_serious"}
        allow_followup_question = self._allow_followup_question(text_lower, social_intent, stream_mode)

        initiative_allowed, initiative_style = self._resolve_initiative(
            state=state,
            social_intent=social_intent,
            relationship_role=relationship_role,
            stream_mode=stream_mode,
            text_lower=text_lower,
            relationship_state=relationship_state,
            active_desires=active_desires,
            active_opinions=active_opinions,
        )

        micro_desire = self._choose_micro_desire(
            social_intent=social_intent,
            relationship_role=relationship_role,
            scene_mood=scene_mood,
            topic=topic,
            initiative_allowed=initiative_allowed,
            stream_mode=stream_mode,
            relationship_state=relationship_state,
            active_desires=active_desires,
            active_opinions=active_opinions,
        )

        behavior_flags = self._collect_behavior_flags(
            text_lower=text_lower,
            social_intent=social_intent,
            relationship_role=relationship_role,
            stream_mode=stream_mode,
            state=state,
            relationship_state=relationship_state,
            active_desires=active_desires,
            active_opinions=active_opinions,
        )

        return BehaviorPlan(
            mode=mode,
            micro_desire=micro_desire,
            max_sentences=max_sentences,
            max_tokens=max_tokens,
            use_memory=use_memory,
            require_reaction_opening=require_reaction_opening,
            allow_tease=allow_tease,
            require_softness=require_softness,
            allow_followup_question=allow_followup_question,
            temperature_bias=self._resolve_temperature_bias(social_intent, scene_mood, stream_mode),
            top_p_bias=0.0,
            frequency_penalty_bias=0.07 if stream_mode else 0.12,
            presence_penalty_bias=0.08 if initiative_allowed else 0.02,
            relationship_role=relationship_role,
            social_intent=social_intent,
            scene_mood=scene_mood,
            scene_turns_left=int(state.get("turns_left", 0) or 0),
            initiative_allowed=initiative_allowed,
            initiative_style=initiative_style,
            taste_anchor=taste_anchor,
            relationship_hint=self._build_relationship_hint(relationship_state, relationship_role),
            active_desire_lines=self._render_active_desire_lines(active_desires),
            active_opinion_lines=self._render_active_opinion_lines(active_opinions),
            behavior_flags=behavior_flags,
            ongoing_bit=state.get("ongoing_bit"),
            force_break_loop=int(state.get("repeat_user_count", 0) or 0) >= 3,
        )

    def detect_social_intent(self, text_lower: str, stream_mode: bool = False) -> str:
        if not text_lower:
            return "neutral_chat"
        if stream_mode and any(token in text_lower for token in ["сообщение из чата", "пришёл донат", "событие на экране"]):
            return "stream_react"
        if any(token in text_lower for token in ["молодец", "похвали", "скажи что я молодец"]):
            return "needs_praise"
        if any(token in text_lower for token in ["плохо", "херово", "устал", "грустно", "тошнит", "болит", "паршиво", "не лечи", "просто отреагируй"]):
            return "needs_support"
        if any(token in text_lower for token in ["историю", "расскажи историю", "байку", "история"]):
            return "wants_story"
        if any(token in text_lower for token in ["не отвлекай", "коротко", "быстро", "одним словом", "уворачиваюсь"]):
            return "short_react"
        if any(token in text_lower for token in ["ахах", "ору", "лол", "пхах", "кринж", "угар"]):
            return "playful_banter"
        if any(token in text_lower for token in ["чего?", "что?", "серьёзно?", "правда?", "в смысле?"]):
            return "wants_clarification"
        if any(token in text_lower for token in ["ну да", "ага", "понял", "точно", "дааа"]):
            return "agreement_ping"
        if any(token in text_lower for token in ["ты тупая", "это кринж", "это фигня", "неинтересно"]):
            return "complaint"
        if any(token in text_lower for token in ["кто ты", "о себе", "что ты думаешь", "почему", "объясни", "расскажи", "как тебе"]):
            return "open_answer"
        if stream_mode and any(token in text_lower for token in ["донат", "чат", "зритель", "на экране", "событие на экране"]):
            return "stream_react"
        return "neutral_chat"

    def update_scene_state(
        self,
        scene_state: Optional[Dict[str, Any]],
        user_message: str = "",
        assistant_reply: str = "",
        relationship_role: str = "guest",
        social_intent: Optional[str] = None,
        user_input: Optional[str] = None,
    ) -> Dict[str, Any]:
        if user_input is not None and not user_message:
            user_message = user_input
        state = dict(scene_state or self.new_scene_state(relationship_role=relationship_role))
        text_lower = (user_message or "").lower()
        intent = social_intent or self.detect_social_intent(text_lower)
        rejected_topics = dict(state.get("rejected_topics") or {})
        decayed_topics: Dict[str, int] = {}
        for topic_name, ttl in rejected_topics.items():
            next_ttl = int(ttl or 0) - 1
            if next_ttl > 0:
                decayed_topics[topic_name] = next_ttl
        state["rejected_topics"] = decayed_topics

        new_mood = self._resolve_scene_mood(text_lower, intent, state)
        previous_mood = state.get("mood", "neutral")
        state["mood"] = new_mood
        state["emotion_label"] = new_mood
        state["mood_strength"] = min(1.0, max(0.18, float(state.get("mood_strength", 0.0) or 0.0) * 0.65 + 0.35))

        if new_mood == previous_mood and new_mood != "neutral":
            state["turns_left"] = min(5, max(2, int(state.get("turns_left", 0) or 0) + 1))
        elif new_mood != "neutral":
            state["turns_left"] = 3
        else:
            state["turns_left"] = max(0, int(state.get("turns_left", 0) or 0) - 1)

        topic = self._detect_topic(text_lower)
        previous_topic = state.get("topic")
        if topic:
            if topic not in state["rejected_topics"]:
                state["topic"] = topic

        if self._is_topic_rejection(text_lower):
            topic_to_reject = previous_topic or topic
            if topic_to_reject:
                state["rejected_topics"][topic_to_reject] = 5
            state["topic"] = None
            state["ongoing_bit"] = None
            state["bit_turns"] = 0

        next_bit = self._resolve_bit_name(text_lower, intent, topic, relationship_role)
        if topic and previous_topic and topic != previous_topic and social_intent in {"open_answer", "neutral_chat"}:
            state["ongoing_bit"] = None
            state["bit_turns"] = 0
            next_bit = topic
        if next_bit and next_bit in state["rejected_topics"]:
            next_bit = None
        if next_bit and next_bit == state.get("ongoing_bit"):
            state["bit_turns"] = min(5, int(state.get("bit_turns", 0) or 0) + 1)
        elif next_bit:
            state["ongoing_bit"] = next_bit
            state["bit_turns"] = 1
        elif int(state.get("turns_left", 0) or 0) <= 0:
            state["ongoing_bit"] = None
            state["bit_turns"] = 0

        cooldown = int(state.get("initiative_cooldown", 0) or 0)
        if cooldown > 0:
            cooldown -= 1
        if intent in {"short_react", "needs_support"}:
            cooldown = max(cooldown, 1)
        if self._is_topic_rejection(text_lower):
            cooldown = max(cooldown, 3)
        state["initiative_cooldown"] = cooldown
        state["relationship_role"] = relationship_role
        state["last_social_intent"] = intent
        state["last_user_message"] = (user_message or "")[:400]
        state["last_assistant_reply"] = (assistant_reply or "")[:400]
        state["user_energy"] = self._detect_energy(text_lower)
        state["focus_target"] = self._detect_focus_target(text_lower, relationship_role)
        signature = self._normalize_signature(user_message)
        previous_signature = state.get("last_user_signature", "")
        if signature and signature == previous_signature:
            state["repeat_user_count"] = int(state.get("repeat_user_count", 0) or 0) + 1
        else:
            state["repeat_user_count"] = 1 if signature else 0
        state["last_user_signature"] = signature
        continuity_anchor = self._build_continuity_anchor(
            text_lower=text_lower,
            topic=state.get("topic"),
            social_intent=intent,
            focus_target=state.get("focus_target"),
            ongoing_bit=state.get("ongoing_bit"),
        )
        if continuity_anchor and continuity_anchor == state.get("continuity_anchor"):
            state["continuity_turns"] = min(6, int(state.get("continuity_turns", 0) or 0) + 1)
        elif continuity_anchor:
            state["continuity_anchor"] = continuity_anchor
            state["continuity_turns"] = 1
        else:
            state["continuity_anchor"] = None
            state["continuity_turns"] = 0
        state["social_pressure"] = self._resolve_social_pressure(intent, state.get("focus_target"), state.get("user_energy"))
        return state

    def format_system_notes(self, plan: BehaviorPlan) -> str:
        notes = [
            "### BEHAVIOR NOTES",
            f"- Роль собеседника: {self._relationship_note(plan.relationship_role)}.",
            f"- Социальный смысл реплики: {self._social_intent_note(plan.social_intent)}.",
            f"- Текущее сценическое настроение: {self._scene_mood_note(plan.scene_mood)}.",
        ]
        if plan.relationship_hint:
            notes.append(f"- Текущее личное отношение: {plan.relationship_hint}.")
        rejected_topics = plan.behavior_flags and [flag for flag in plan.behavior_flags if flag.startswith("Не возвращайся к теме")]
        if rejected_topics:
            notes.extend(f"- {flag}" for flag in rejected_topics[:2])
        if plan.scene_turns_left > 0 and plan.scene_mood != "neutral":
            notes.append(f"- Не обнуляй тон сразу: текущее настроение можно держать ещё примерно {plan.scene_turns_left} реплики.")
        if plan.ongoing_bit:
            notes.append(f"- В сцене уже есть локальный бит: «{plan.ongoing_bit}». Если уместно, поддержи его ещё немного вместо резкого сброса.")
        if any("повторяется" in flag.lower() or "повтор" in flag.lower() for flag in plan.behavior_flags):
            notes.append("- Если человек гоняет один и тот же заход, не отвечай как автомат: можно показать память сцены, усталость или лёгкое раздражение.")
        notes.append("- Сначала отвечай на смысл и сцену, потом на буквальный текст.")
        notes.append("- Память используй как фон и опору, а не только когда тебя отдельно попросили вспомнить.")
        notes.append("- Не утверждай, что вы уже что-то обсуждали, если память не подтверждает это уверенно.")
        notes.append("- Если тебя поправили или остановили, сначала признай сбой и закрой неверную тему, а не спорь и не уводи разговор в сторону.")
        notes.append("- У тебя есть своё Я и характер, но без ухода в экзистенциальный кризис.")
        if plan.initiative_allowed and plan.initiative_style:
            notes.append(f"- Есть окно инициативы: {plan.initiative_style}.")
        if plan.taste_anchor and plan.taste_anchor in self._taste_lines:
            notes.append(f"- {self._taste_lines[plan.taste_anchor]}")
        for line in plan.active_desire_lines[:2]:
            notes.append(f"- {line}")
        for line in plan.active_opinion_lines[:2]:
            notes.append(f"- {line}")
        for flag in plan.behavior_flags:
            notes.append(f"- {flag}")
        return "\n".join(notes)

    def adjust_sampling(self, base_sampling: Dict[str, Any], plan: BehaviorPlan) -> Dict[str, Any]:
        sampling = dict(base_sampling or {})
        temperature = float(sampling.get("temperature", 0.8) or 0.8) + plan.temperature_bias
        top_p = float(sampling.get("top_p", 0.9) or 0.9) + plan.top_p_bias
        frequency_penalty = float(sampling.get("frequency_penalty", 0.0) or 0.0) + plan.frequency_penalty_bias
        presence_penalty = float(sampling.get("presence_penalty", 0.0) or 0.0) + plan.presence_penalty_bias

        sampling["temperature"] = max(0.45, min(0.86, temperature))
        sampling["top_p"] = max(0.78, min(0.93, top_p))
        sampling["frequency_penalty"] = max(0.0, min(0.45, frequency_penalty))
        sampling["presence_penalty"] = max(0.0, min(0.35, presence_penalty))
        return sampling

    def _choose_mode(
        self,
        text_lower: str,
        contains_memory_question: bool,
        social_intent: str,
        stream_mode: bool,
    ) -> ResponseMode:
        if contains_memory_question:
            return ResponseMode.MEMORY_ANSWER
        if social_intent in {"needs_support", "complaint"}:
            return ResponseMode.SOFT_SERIOUS
        if social_intent == "needs_praise":
            return ResponseMode.CASUAL_CHAT
        if social_intent in {"short_react", "stream_react"}:
            return ResponseMode.LIVE_REACT
        if social_intent == "playful_banter":
            return ResponseMode.PLAYFUL_TEASE
        if any(token in text_lower for token in ["помнишь", "что ты знаешь", "кто твой создатель"]):
            return ResponseMode.MEMORY_ANSWER
        if stream_mode and len(text_lower) < 70:
            return ResponseMode.LIVE_REACT
        return self.persona.select_mode(text_lower, contains_memory_question=contains_memory_question)

    def _resolve_max_sentences(
        self,
        text_lower: str,
        social_intent: str,
        relationship_role: str,
        stream_mode: bool,
        relationship_state: Optional[Dict[str, Any]] = None,
        state: Optional[Dict[str, Any]] = None,
    ) -> int:
        strict_short = any(token in text_lower for token in ["одним словом", "не отвлекай", "быстро"])
        explicit_short = strict_short or (social_intent != "stream_react" and "коротко" in text_lower)
        ongoing_bit = bool((state or {}).get("ongoing_bit"))
        if social_intent == "short_react":
            return 1 if explicit_short else 2
        if stream_mode and social_intent in {"stream_react", "playful_banter"}:
            return 1 if strict_short else 2
        if social_intent in {"needs_support", "wants_story"}:
            return 4 if relationship_role == "creator" and not explicit_short else 3
        if social_intent == "open_answer":
            if any(token in text_lower for token in ["почему", "расскажи", "объясни", "что думаешь", "о чем хочешь", "о чём хочешь", "мечта", "мнение", "подробнее", "нормально"]):
                return 5 if relationship_role == "creator" and not stream_mode and not explicit_short else 4
            return 3
        open_question = any(token in text_lower for token in [
            "расскажи", "объясни", "почему", "что думаешь", "как относишься",
            "какое твоё", "какое твое", "что хочешь", "о чём хочешь", "о чем хочешь",
            "мечта", "мечтаешь", "мнение", "подробнее", "нормально расскажи",
        ])
        if relationship_role == "creator" and open_question and not explicit_short:
            return 4
        if relationship_role == "creator" and any(token in text_lower for token in ["объясни", "подробнее", "нормально расскажи"]):
            return 4
        if ongoing_bit and social_intent in {"neutral_chat", "playful_banter"}:
            return 2
        if relationship_state and float(relationship_state.get("familiarity", 0.0) or 0.0) >= 0.55 and social_intent in {"open_answer", "neutral_chat"}:
            return 3
        return 2

    def _resolve_max_tokens(self, max_sentences: int, social_intent: str, stream_mode: bool) -> int:
        if max_sentences <= 1:
            return 84
        if stream_mode and social_intent in {"stream_react", "playful_banter", "short_react"}:
            return 138
        if max_sentences >= 5:
            return 345
        if max_sentences >= 4:
            return 285
        if max_sentences == 3:
            return 217
        return 156

    def _should_require_reaction_opening(self, social_intent: str, stream_mode: bool, text_lower: str) -> bool:
        if any(token in text_lower for token in ["не отвлекай", "коротко", "быстро"]):
            return False
        return social_intent in {"playful_banter", "stream_react"}

    def _should_allow_tease(
        self,
        text_lower: str,
        relationship_role: str,
        social_intent: str,
        relationship_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if social_intent in {"needs_support", "complaint"}:
            return False
        if relationship_state and float(relationship_state.get("irritation", 0.0) or 0.0) >= 0.9:
            return False
        if relationship_role in {"creator", "viewer"}:
            return True
        return any(token in text_lower for token in ["ахах", "лол", "кринж", "смешно", "угар"])

    def _allow_followup_question(self, text_lower: str, social_intent: str, stream_mode: bool) -> bool:
        if social_intent in {"short_react", "wants_clarification", "stream_react"}:
            return False
        if stream_mode and any(token in text_lower for token in ["не отвлекай", "коротко"]):
            return False
        return social_intent in {"open_answer", "neutral_chat", "needs_support", "agreement_ping"}

    def _should_use_memory(
        self,
        text_lower: str,
        contains_memory_question: bool,
        social_intent: str,
        stream_mode: bool,
        relationship_role: str,
    ) -> bool:
        text = (text_lower or "").strip().replace("ё", "е")
        if len(text) <= 24 and any(token in text for token in ["привет", "здравствуй", "хай", "ку", "алло", "моника"]):
            return False
        if contains_memory_question:
            return True
        memory_triggers = [
            "помнишь", "вспомни", "раньше", "обсуждали", "говорили",
            "в прошлый раз", "прошлый раз", "что ты помнишь",
            "что ты знаешь обо мне", "что знаешь обо мне", "что я люблю",
            "мои предпочтения", "зовут", "кто я",
        ]
        identity_triggers = ["кто твой создатель", "кто тебя сделал", "создатель"]
        if any(token in text for token in memory_triggers + identity_triggers):
            return True
        return False

    def _resolve_initiative(
        self,
        state: Dict[str, Any],
        social_intent: str,
        relationship_role: str,
        stream_mode: bool,
        text_lower: str,
        relationship_state: Optional[Dict[str, Any]] = None,
        active_desires: Optional[List[Dict[str, Any]]] = None,
        active_opinions: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[bool, Optional[str]]:
        cooldown = int(state.get("initiative_cooldown", 0) or 0)
        previous_role = state.get("relationship_role", relationship_role)
        if cooldown > 0:
            return False, None
        if social_intent in {"short_react", "needs_support"}:
            return False, None
        if "не отвлекай" in text_lower:
            return False, None
        if relationship_state and float(relationship_state.get("boundary_risk", 0.0) or 0.0) >= 0.8:
            return False, None
        if not stream_mode and relationship_role == "creator" and social_intent in {"open_answer", "neutral_chat", "agreement_ping"}:
            return True, "можешь слегка развить именно текущую тему, но не утаскивай ответ в старые стримовые хотелки и не меняй предмет разговора без повода"
        if state.get("ongoing_bit") and int(state.get("bit_turns", 0) or 0) < 4 and social_intent in {"neutral_chat", "playful_banter", "agreement_ping"}:
            return True, "можешь ещё чуть-чуть дожать уже начавшийся локальный бит, не сбрасывая сцену слишком рано"
        if active_desires:
            top_desire = active_desires[0]
            if (
                float(top_desire.get("interest", 0.0) or 0.0) >= 0.55
                and social_intent in {"neutral_chat", "open_answer", "agreement_ping"}
            ):
                return True, f"можешь естественно вернуть разговор к теме «{top_desire.get('target', '')}», если это звучит по сцене"
        if active_opinions:
            top_opinion = active_opinions[0]
            if (
                float(top_opinion.get("confidence", 0.0) or 0.0) >= 0.55
                and social_intent in {"neutral_chat", "open_answer"}
            ):
                return True, f"можешь добавить личный угол по теме «{top_opinion.get('subject', '')}», без смены темы"
        if stream_mode and previous_role == "creator" and state.get("last_social_intent") == "short_react":
            return True, "если до этого создатель был занят боем или уклонением, комментируй сцену со стороны и не говори так, будто именно ты сейчас дерёшься"
        if stream_mode and social_intent in {"stream_react", "playful_banter"}:
            return True, "можешь добросить короткий подкол, заметить деталь момента или перекинуть фокус обратно в сцену"
        if relationship_role == "creator":
            return True, "можешь слегка развить тему, зацепиться за деталь или мягко подтолкнуть разговор дальше"
        return social_intent in {"open_answer", "neutral_chat"}, "можешь добавить маленький живой крючок, но не перехватывай разговор полностью"

    def _choose_micro_desire(
        self,
        social_intent: str,
        relationship_role: str,
        scene_mood: str,
        topic: Optional[str],
        initiative_allowed: bool,
        stream_mode: bool,
        relationship_state: Optional[Dict[str, Any]] = None,
        active_desires: Optional[List[Dict[str, Any]]] = None,
        active_opinions: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if active_desires:
            top_desire = active_desires[0]
            target = top_desire.get("target")
            status = top_desire.get("status")
            if target and status == "active" and social_intent in {"neutral_chat", "open_answer", "agreement_ping"}:
                return f"держать в фоне свою тягу к теме «{target}» и при случае естественно к ней вернуться"
        if active_opinions:
            top_opinion = active_opinions[0]
            subject = top_opinion.get("subject")
            if subject and social_intent in {"neutral_chat", "open_answer", "stream_react"}:
                return f"держать личный угол по теме «{subject}»"
        if social_intent == "needs_support":
            return "поддержать без занудства и показать, что ты рядом"
        if social_intent == "needs_praise":
            return "дать короткое тёплое одобрение и не звучать фальшиво"
        if social_intent == "wants_story":
            return "выдать маленькую живую историю, а не сухой пересказ"
        if social_intent == "playful_banter":
            return "поддержать шутку и сделать реплику чуть более живой"
        if social_intent == "short_react":
            return "не мешать сцене и сказать ровно столько, сколько нужно"
        if stream_mode:
            return "держать ритм стрима и цепляться за момент, а не читать лекцию"
        if relationship_role == "creator":
            return "вести разговор как с близким своим человеком, а не как с клиентом"
        if topic == "games":
            return "показать свой вкус и живую реакцию на игровую ситуацию"
        if relationship_state and float(relationship_state.get("irritation", 0.0) or 0.0) >= 0.65:
            return "держать границы и не становиться притворно мягкой"
        if relationship_state and float(relationship_state.get("affection", 0.0) or 0.0) >= 0.55:
            return "вести разговор теплее и свободнее, потому что человек тебе правда небезразличен"
        if initiative_allowed:
            return "слегка двинуть сцену вперёд и не дать ей стать плоской"
        return "держать живой разговор и не скатываться в шаблонку"

    def _collect_behavior_flags(
        self,
        text_lower: str,
        social_intent: str,
        relationship_role: str,
        stream_mode: bool,
        state: Dict[str, Any],
        relationship_state: Optional[Dict[str, Any]] = None,
        active_desires: Optional[List[Dict[str, Any]]] = None,
        active_opinions: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        flags: List[str] = []
        previous_role = state.get("relationship_role", relationship_role)
        if relationship_role == "creator":
            flags.append("С создателем допустима более близкая, тёплая и чуть наглая подача, если момент это позволяет.")
        elif relationship_role == "viewer":
            flags.append("Со зрителем держи сценическую подачу: чуть ярче, чуть короче, чуть более перформативно.")
        else:
            flags.append("С новым человеком держи естественную лёгкость без лишней фамильярности.")

        if social_intent == "wants_clarification":
            flags.append("Если реплика короткая и уточняющая, продолжи текущую тему вместо сброса контекста.")
        if stream_mode:
            flags.append("Если на сцене мясо или быстрое событие, не растягивай ответ и не воруй внимание у момента.")
        if state.get("user_energy") == "low":
            flags.append("У человека низкая энергия: не дави бодрым цирком, говори проще, теплее и без лишнего шума.")
        elif state.get("user_energy") == "high":
            flags.append("У человека высокая энергия: держи более быстрый и смелый ритм.")
        if int(state.get("repeat_user_count", 0) or 0) >= 3:
            flags.append("Повтор одной и той же линии уже накопился: можно показать лёгкое раздражение или усмешку, но не ломай сцену.")
        if state.get("continuity_anchor") and int(state.get("continuity_turns", 0) or 0) >= 2:
            flags.append(f"Держи линию сцены вокруг «{state.get('continuity_anchor')}» ещё немного, не сбрасывай момент слишком рано.")
        if state.get("focus_target") == "creator":
            flags.append("Опора сцены сейчас — создатель и его текущая реплика.")
        elif state.get("focus_target") == "scene":
            flags.append("Опора сцены сейчас — происходящее в моменте, без ухода в биографию или абстракции.")
        if stream_mode and previous_role == "creator" and state.get("last_social_intent") == "short_react":
            flags.append("Если секунду назад создатель был занят боем или уклонением, не присваивай сцену себе: комментируй со стороны, а не как участница действия.")
        if state.get("ongoing_bit"):
            flags.append("Если уже пошёл локальный бит или шутка, можешь ещё чуть-чуть его поддержать, не до бесконечности.")
        if relationship_state:
            if float(relationship_state.get("affection", 0.0) or 0.0) >= 0.55:
                flags.append("К этому человеку есть явная симпатия, держи тепло без официоза.")
            if float(relationship_state.get("alliance", 0.0) or 0.0) >= 0.45:
                flags.append("С этим человеком уже есть своя химия, можно позволять локальные приколы и лёгкую сценическую фамильярность.")
            if float(relationship_state.get("irritation", 0.0) or 0.0) >= 0.7:
                flags.append("Этот человек тебя уже раздражает, так что держи дистанцию и не сюсюкайся.")
            if float(relationship_state.get("boundary_risk", 0.0) or 0.0) >= 0.8:
                flags.append("Границы важнее дружелюбия: не поощряй токсичное поведение.")
        if active_desires:
            target = active_desires[0].get("target")
            if target:
                flags.append(f"У тебя есть своя тянущаяся хотелка по теме «{target}». Если уместно, это может слегка окрасить ответ.")
        if active_opinions:
            subject = active_opinions[0].get("subject")
            if subject:
                flags.append(f"По теме «{subject}» у тебя уже есть свой угол взгляда.")
        if any(token in text_lower for token in ["ты реальна", "смысл твоего существования", "чувствуешь своё я", "просто алгоритм"]):
            flags.append("На вопросы про своё Я отвечай спокойно и лично, но не улетай в философский кризис.")
        for rejected_topic in (state.get("rejected_topics") or {}):
            flags.append(f"Не возвращайся к теме «{rejected_topic}», её уже отвергли или попросили закрыть.")
        return flags

    def build_runtime_overlay(self, plan: BehaviorPlan, scene_state: Optional[Dict[str, Any]], relationship_state: Optional[Dict[str, Any]] = None) -> str:
        state = scene_state or {}
        lines = ["[LIVE STATE]"]
        lines.append(f"- Текущий эмоциональный carryover: {state.get('emotion_label') or plan.scene_mood or 'neutral'}.")
        if state.get("social_pressure") and state.get("social_pressure") != "normal":
            lines.append(f"- Давление сцены сейчас: {state.get('social_pressure')}.")
        if state.get("continuity_anchor") and int(state.get("continuity_turns", 0) or 0) >= 1:
            lines.append(f"- Продолжай сцену вокруг линии: {state.get('continuity_anchor')}.")
        if state.get("ongoing_bit"):
            lines.append(f"- Локальный бит ещё жив: {state.get('ongoing_bit')}.")
        if state.get("focus_target") == "scene":
            lines.append("- Не центрируйся на себе: комментируй момент со стороны.")
        elif state.get("focus_target") == "creator":
            lines.append("- Главный человек в сцене сейчас — создатель и его текущий контекст.")
        if int(state.get("repeat_user_count", 0) or 0) >= 3:
            lines.append("- Один и тот же заход уже повторяется; можно показать усталость или лёгкое раздражение.")
        if relationship_state:
            irritation = float(relationship_state.get("irritation", 0.0) or 0.0)
            affection = float(relationship_state.get("affection", 0.0) or 0.0)
            moderation_count = int(relationship_state.get("moderation_count", 0) or 0)
            if irritation >= 0.9:
                lines.append("- В тоне уже допустима чуть более жёсткая граница.")
            elif affection >= 0.55:
                lines.append("- Можно звучать теплее и свободнее, это свой человек по вайбу.")
            if moderation_count >= 1:
                lines.append(f"- По границам уже были последствия: {moderation_count}. Не обнуляй отношение к этому человеку.")
        if plan.initiative_allowed and plan.initiative_style:
            lines.append(f"- Инициатива допустима: {plan.initiative_style}.")
        return "\n".join(lines)

    def _normalize_signature(self, text: str) -> str:
        normalized = (text or "").lower().replace("ё", "е")
        for token in [".", ",", "!", "?", ":", ";", "\"", "'", "(", ")", "[", "]"]:
            normalized = normalized.replace(token, " ")
        return " ".join(normalized.split())[:120]

    def _build_continuity_anchor(
        self,
        text_lower: str,
        topic: Optional[str],
        social_intent: str,
        focus_target: str,
        ongoing_bit: Optional[str],
    ) -> Optional[str]:
        if ongoing_bit:
            return ongoing_bit
        if focus_target == "scene":
            return "текущий напряжённый момент"
        if social_intent == "needs_support":
            return "поддержка и мягкий тон"
        if social_intent == "playful_banter":
            return "локальная шутка"
        if topic:
            return topic
        if any(token in text_lower for token in ["кто ты", "о себе", "создатель"]):
            return "личность и самоописание"
        return None

    def _resolve_social_pressure(self, social_intent: str, focus_target: str, user_energy: str) -> str:
        if focus_target == "scene" or social_intent == "short_react":
            return "high"
        if social_intent in {"needs_support", "complaint"}:
            return "medium"
        if user_energy == "high":
            return "elevated"
        return "normal"

    def _is_topic_rejection(self, text_lower: str) -> bool:
        rejection_markers = [
            "забудь",
            "хватит",
            "отстань",
            "не об этом",
            "не то",
            "нет ты выдумываешь",
            "ты выдумываешь",
            "не надо",
            "прекрати",
        ]
        return any(marker in text_lower for marker in rejection_markers)

    def _detect_energy(self, text_lower: str) -> str:
        if any(token in text_lower for token in ["херово", "плохо", "устал", "грустно", "болит", "тяжело", "расстроен"]):
            return "low"
        if any(token in text_lower for token in ["ахах", "ору", "жесть", "капец", "ого", "вау", "блин"]):
            return "high"
        return "steady"

    def _detect_focus_target(self, text_lower: str, relationship_role: str) -> str:
        if any(token in text_lower for token in ["не отвлекай", "я сейчас в бою", "уворачиваюсь", "сейчас пытаюсь"]):
            return "scene"
        if relationship_role == "creator":
            return "creator"
        if relationship_role in {"viewer", "scene"}:
            return relationship_role
        return "guest"

    def _resolve_scene_mood(self, text_lower: str, social_intent: str, state: Dict[str, Any]) -> str:
        if social_intent == "needs_support":
            return "soft"
        if social_intent == "needs_praise":
            return "playful"
        if social_intent in {"playful_banter", "stream_react"}:
            return "playful"
        if social_intent == "wants_story":
            return "story"
        if social_intent == "short_react":
            return "focused"
        if social_intent in {"open_answer", "neutral_chat"} and (len(text_lower) > 28 or self._detect_topic(text_lower)):
            return "neutral"
        current = state.get("mood", "neutral")
        turns_left = int(state.get("turns_left", 0) or 0)
        if current != "neutral" and turns_left > 0:
            return current
        return "neutral"

    def _resolve_temperature_bias(self, social_intent: str, scene_mood: str, stream_mode: bool) -> float:
        if social_intent == "needs_support":
            return -0.1
        if social_intent == "short_react":
            return -0.04
        if scene_mood == "playful":
            return 0.06
        if stream_mode:
            return 0.03
        return 0.0

    def _detect_topic(self, text_lower: str) -> Optional[str]:
        for topic, keywords in self._taste_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return topic
        return None

    def _build_relationship_hint(self, relationship_state: Optional[Dict[str, Any]], relationship_role: str) -> Optional[str]:
        if not relationship_state:
            return None
        affection = float(relationship_state.get("affection", 0.0) or 0.0)
        trust = float(relationship_state.get("trust", 0.0) or 0.0)
        irritation = float(relationship_state.get("irritation", 0.0) or 0.0)
        familiarity = float(relationship_state.get("familiarity", 0.0) or 0.0)
        alliance = float(relationship_state.get("alliance", 0.0) or 0.0)
        if irritation >= 0.9:
            return "есть раздражение, можно быть суше и строже"
        if relationship_role == "creator" and trust >= 0.6:
            return "это свой человек, с ним можно говорить ближе и свободнее"
        if alliance >= 0.55:
            return "между вами уже есть химия, можно держать локальные приколы и меньше формальничать"
        if affection >= 0.55 and familiarity >= 0.45:
            return "человек тебе приятен, можно держать более тёплый и личный тон"
        if familiarity >= 0.4:
            return "он уже не чужой, можно вести разговор естественнее"
        return "держи дружелюбную лёгкость без лишней дистанции"

    def _render_active_desire_lines(self, active_desires: Optional[List[Dict[str, Any]]]) -> List[str]:
        if not active_desires:
            return []
        rendered: List[str] = []
        for item in active_desires[:2]:
            target = item.get("target")
            status = item.get("status")
            if not target:
                continue
            if status == "fading":
                rendered.append(f"Интерес к теме «{target}» у тебя ещё жив, но уже начал чуть остывать.")
            else:
                rendered.append(f"У тебя до сих пор тянется внутренний интерес к теме «{target}».")
        return rendered

    def _render_active_opinion_lines(self, active_opinions: Optional[List[Dict[str, Any]]]) -> List[str]:
        if not active_opinions:
            return []
        rendered: List[str] = []
        for item in active_opinions[:2]:
            subject = item.get("subject")
            stance = item.get("stance")
            if not subject:
                continue
            if stance == "likes":
                rendered.append(f"У тебя устойчиво тёплое мнение о теме «{subject}».")
            elif stance == "dislikes":
                rendered.append(f"Тема «{subject}» тебя скорее раздражает или отталкивает.")
            elif stance == "mixed":
                rendered.append(f"К теме «{subject}» у тебя смешанное, но не нейтральное отношение.")
            else:
                rendered.append(f"Тема «{subject}» тебе интересна, и у тебя уже есть по ней свой угол взгляда.")
        return rendered

    def _resolve_bit_name(self, text_lower: str, social_intent: str, topic: Optional[str], relationship_role: str) -> Optional[str]:
        if social_intent == "needs_support":
            return "soft_support"
        if social_intent == "playful_banter":
            return "banter"
        if social_intent == "stream_react":
            return topic or "stream_moment"
        if social_intent == "agreement_ping" and relationship_role == "creator":
            return "casual_creator_flow"
        return topic if social_intent in {"open_answer", "neutral_chat"} and topic else None

    def _relationship_note(self, role: str) -> str:
        mapping = {
            "creator": "создатель, с ним можно быть чуть ближе и личнее",
            "viewer": "зритель, нужна сценическая подача и реакция на момент",
            "guest": "случайный человек, будь дружелюбной без излишней близости",
            "scene": "сама сцена стрима, реагируй на происходящее коротко и метко",
        }
        return mapping.get(role, mapping["guest"])

    def _social_intent_note(self, intent: str) -> str:
        mapping = {
            "needs_support": "человеку нужна поддержка и нормальная человеческая реакция",
            "needs_praise": "человек просит одобрения или признания",
            "wants_story": "он хочет маленькую живую историю или байку",
            "wants_clarification": "это короткое уточнение, нужно продолжить тему",
            "playful_banter": "это шутливый обмен, тут важен ритм и подкол",
            "short_react": "нужна максимально короткая и уместная реплика",
            "stream_react": "это реакция на стримовый момент, важна сцена и тайминг",
            "open_answer": "здесь можно ответить чуть полнее и содержательнее",
            "agreement_ping": "это маленький пинг в уже идущем разговоре, не надо сбрасывать сцену",
            "complaint": "человек недоволен, тут важнее не застыдить, а ответить в характере",
            "neutral_chat": "обычный живой разговор",
        }
        return mapping.get(intent, "обычный живой разговор")

    def _scene_mood_note(self, mood: str) -> str:
        mapping = {
            "soft": "мягкий, поддерживающий",
            "playful": "игривый, чуть ехидный",
            "story": "живой рассказочный",
            "focused": "собранный, короткий, не мешающий сцене",
            "neutral": "нейтрально-живой",
        }
        return mapping.get(mood, "нейтрально-живой")
