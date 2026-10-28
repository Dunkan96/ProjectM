import logging
import random
import time

from behavior_director import BehaviorDirector
from config import PATIENCE
from persona import Persona, ResponseMode
from session_mind import SessionMind
from stage_director import StageDirector
from opinion_core import OpinionCore
from response_guard import ResponseGuard
from monika_self_state import MonikaSelfState


_persona_instance = None
runtime_logger = logging.getLogger("monika.runtime")


def get_persona() -> Persona:
    global _persona_instance
    if _persona_instance is None:
        _persona_instance = Persona()
    return _persona_instance


class Prompter:
    """Инициативный слой: Моника сама оживляет паузы, но не из банка шаблонов."""

    def __init__(self, signals, llm_callback, get_history_func=None, client=None, model=None, builder=None, get_emotion_func=None):
        self.signals = signals
        self.llm_callback = llm_callback
        self.get_history = get_history_func
        self.client = client
        self.model = model
        self.builder = builder
        self.get_emotion = get_emotion_func
        self.self_state = MonikaSelfState(builder.knowledge_conn) if builder is not None else None
        self.session_mind = SessionMind(max_turns=40)
        self.stage_director = StageDirector()
        self.opinion_core = OpinionCore(builder.knowledge_conn) if builder is not None else None
        self.response_guard = ResponseGuard()
        self.system_ready = False
        self.timeSinceLastMessage = 0.0
        self.current_desire = None
        self.desire_expiry = 0.0
        self.proactive_attempts = 0
        self.max_proactive_attempts = 2
        self._last_proactive_texts = []
        self.persona = get_persona()
        self.behavior_director = BehaviorDirector(self.persona)

    def _get_recent_history(self):
        if not self.get_history:
            return []
        history = self.get_history() or []
        normalized = []
        for msg in history:
            if isinstance(msg, dict):
                role = msg.get("role")
                content = msg.get("content", "")
            else:
                role = getattr(msg, "role", None)
                content = getattr(msg, "content", "")
            if role in {"user", "assistant"} and content:
                normalized.append({"role": role, "content": content})
        return normalized

    def _pick_proactive_topic(self) -> str:
        fallback_topics = ["игры", "интернет-хаос", "мемы", "ностальгия", "странные детали"]
        try:
            suggested = self.session_mind.suggest_proactive_topic(self._get_recent_history()) if self.session_mind else ""
            if suggested:
                return suggested
        except Exception:
            pass
        if not self.builder:
            return random.choice(fallback_topics)
        try:
            best_topic = self.builder.get_best_topic()
        except Exception:
            best_topic = None
        banned = {"разное", "жизнь", "мечты", "реальность", "смысл", "еда", "food", "пицца", "энергетик"}
        if best_topic and best_topic not in banned:
            # Проверяем не заезжена ли тема через desire_memory
            try:
                from desire_memory import DesireMemory
                dm = DesireMemory(self.builder.knowledge_conn)
                desires = dm.get_active_desires(limit=1)
                if desires and desires[0].get("target", "").lower() == best_topic.lower():
                    if int(desires[0].get("times_mentioned", 0) or 0) >= 15:
                        return random.choice(fallback_topics)
            except Exception:
                pass
            return best_topic
        return random.choice(fallback_topics)

    def _looks_like_stale_proactive(self, text: str, last_user_text: str, topic: str) -> bool:
        low = (text or "").lower().replace("ё", "е")
        last = (last_user_text or "").lower().replace("ё", "е")
        topic_low = (topic or "").lower().replace("ё", "е")
        stale_roots = ("пицц", "энергетик", "ананас")
        if any(root in low for root in stale_roots) and not any(root in last for root in stale_roots):
            return True
        if any(x in last for x in ["world of warcraft", "warcraft", "wow", "варкрафт"]) and not any(x in low for x in ["world of warcraft", "warcraft", "wow", "варкрафт", "азерот", "орда", "альянс"]):
            return True
        if any(x in last for x in ["стрима нет", "стрима пока", "вдвоем", "вдвоём"]) and any(x in low for x in ["стрим", "чат", "донат"]):
            return True
        if topic_low in {"еда", "food", "пицца", "энергетик"}:
            return True
        recent_pizza = sum(1 for sig in self._last_proactive_texts[-4:] if "пицц" in sig)
        if "пицц" in low and recent_pizza >= 1:
            return True
        return False

    def _refresh_desire(self, initiative_style: str, topic: str):
        if self.current_desire and time.time() <= self.desire_expiry:
            return
        desire_map = {
            "detail_hook": f"вытащить из темы '{topic}' странную или смешную деталь",
            "playful_poke": "слегка поддеть Дункана и раскачать паузу",
            "gentle_check_in": "мягко проверить, не пропал ли собеседник",
            "curious_nudge": f"подбросить живой вопрос вокруг темы '{topic}'",
        }
        self.current_desire = desire_map.get(initiative_style, f"оживить паузу через тему '{topic}'")
        self.desire_expiry = time.time() + 600

    def _recent_context_text(self) -> str:
        history = self._get_recent_history()
        if not history:
            return "Диалог пока почти пустой."
        lines = []
        for msg in history[-8:]:
            speaker = "Дункан/чат" if msg["role"] == "user" else "Моника"
            lines.append(f"{speaker}: {msg['content']}")
        return "\n".join(lines)

    def _facts_context_text(self) -> str:
        if not self.builder:
            return ""
        facts = []
        try:
            facts.extend(self.builder.get_identity_facts()[:6])
        except Exception:
            pass
        clean = []
        for fact in facts:
            fact = str(fact).strip()
            if fact and fact not in clean:
                clean.append(fact)
        if not clean:
            return ""
        return "Базовые факты личности, не тема для навязывания:\n" + "\n".join(f"- {fact}" for fact in clean[:6])

    def _self_context_text(self):
        blocks = []
        try:
            history = self._get_recent_history()
            if self.self_state:
                blocks.append(self.self_state.build_proactive_prompt_block(history))
            if self.session_mind:
                blocks.append(self.session_mind.build_proactive_prompt_block(history))
        except Exception as e:
            runtime_logger.info(f"PROACTIVE_SELF_STATE_ERROR | {e}")
        return "\n\n".join(block for block in blocks if block)

    def _generate_proactive_message(self):
        history = self._get_recent_history()
        last_user_text = ""
        for msg in reversed(history):
            if msg["role"] == "user":
                last_user_text = msg["content"]
                break

        plan = self.behavior_director.plan_response(last_user_text or "пауза в разговоре")
        initiative_style = plan.initiative_style
        topic = self._pick_proactive_topic()
        self._refresh_desire(initiative_style, topic)
        emotion = {}
        try:
            emotion = self.get_emotion() if self.get_emotion else {}
        except Exception:
            emotion = {}
        emotion_block = ""
        if emotion:
            emotion_block = (
                "Текущий эмоциональный фон:\n"
                f"- mood={emotion.get('mood', 'steady')}, stance={emotion.get('stance', 'react')}, "
                f"intensity={float(emotion.get('intensity', 0.35) or 0.35):.2f}.\n"
                "- Если фон support/repair/personal_focus/story/game_coach, не начинай случайную новую тему. "
                "Лучше продолжи текущую линию или мягко проверь собеседника.\n"
            )

        prompt = f"""{self.persona.get_full_system_prompt(ResponseMode.CASUAL_CHAT)}

Ты Моника. В разговоре наступила пауза, и ты можешь сама сказать одну живую реплику.

Текущий импульс: {self.current_desire}
Стиль инициативы: {initiative_style}
Тема-зацепка: {topic}
Запрещённые заезженные зацепки для инициативы: пицца, энергетик, ананасы, старый стримовый хаос, если пользователь сам сейчас их не поднял.

Последний контекст:
{self._recent_context_text()}

{self._facts_context_text()}

{self._self_context_text()}

{emotion_block}

Сгенерируй одну уникальную инициативную реплику Моники.
Правила:
- Не используй заготовки, приветствие и фразы "ты тут?", "тут стало тихо", "я тут как всегда", "привет", "как дела".
- Не начинай новую тему насильно, если можно продолжить текущую сцену.
- Не выдумывай прошлые события и личный физический опыт.
- Можно мягко поддеть, зацепиться за деталь, спросить коротко или продолжить свою мысль.
- 1-2 предложения, только текст реплики."""

        if not self.client:
            return None

        try:
            messages = [{"role": "user", "content": prompt}]
            if "qwen" in (self.model or "").lower():
                messages[0]["content"] = "/no_think\n" + messages[0]["content"]
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.9,
                max_tokens=90,
                presence_penalty=0.35,
                frequency_penalty=0.35,
                top_p=0.92,
            )
            text = (response.choices[0].message.content or "").strip()
            text = self.persona.apply_drift_guard(text)
            text = self.persona.apply_response_formula(
                text,
                ResponseMode.CASUAL_CHAT,
                max_sentences=2,
                require_reaction_opening=False,
                allow_tease=(initiative_style == "playful_poke"),
                require_softness=(initiative_style == "gentle_check_in"),
                allow_followup_question=True,
            )
            if not text or self.persona.is_weak_response(text):
                return None
            if emotion and emotion.get("suppress_background_layers"):
                low_text = text.lower().replace("ё", "е")
                last_low = (last_user_text or "").lower().replace("ё", "е")
                if last_low and not any(token in low_text for token in last_low.split()[:4]):
                    runtime_logger.info(f"PROACTIVE_EMOTION_FOCUS_BLOCK | stance={emotion.get('stance')} | text={text[:80]}")
                    return None
            if self._looks_like_stale_proactive(text, last_user_text, topic):
                runtime_logger.info(f"PROACTIVE_STALE_TOPIC_BLOCK | topic={topic} | text={text[:80]}")
                return None
            guard = self.response_guard.assess(text, last_user_text or "пауза", {"relationship_role": "creator"}) if self.response_guard else {"ok": True}
            if not guard.get("ok"):
                runtime_logger.info(f"PROACTIVE_GUARD_BLOCK | {guard}")
                return None
            text_normalized = self.persona._normalize_response_text(text).lower().strip()
            if hasattr(self, 'builder') and self.builder and hasattr(self.builder, '_recent_reply_cache'):
                if any(text_normalized == cached for cached in self.builder._recent_reply_cache):
                    runtime_logger.info(f"PROACTIVE_DUPLICATE | blocked: {text[:60]}")
                    return None
            signature = self.behavior_director._normalize_signature(text)
            if signature in self._last_proactive_texts:
                return None
            self._last_proactive_texts.append(signature)
            if len(self._last_proactive_texts) > 8:
                self._last_proactive_texts.pop(0)
            runtime_logger.info(f"PROACTIVE_GENERATED | {text}")
            return text
        except Exception as e:
            runtime_logger.error(f"PROACTIVE_ERROR | {e}")
            return None

    def prompt_now(self):
        if not self.signals.stt_ready or not self.signals.tts_ready:
            return False
        if self.signals.human_speaking or self.signals.AI_thinking or self.signals.AI_speaking:
            return False
        if self.signals.new_message:
            return False

        history = self._get_recent_history()
        if not history:
            return False

        # Test-stream proactive cadence. Do not use global PATIENCE=300 here:
        # five minutes is too long for a first VTuber test. Keep cooldowns so
        # Monika does not spam initiatives.
        if self.proactive_attempts <= 0:
            required_pause = float(getattr(self, "stream_idle_first_pause", 85.0))
        else:
            required_pause = float(getattr(self, "stream_idle_followup_pause", 155.0))

        if len(history) < 3:
            required_pause = max(required_pause, 110.0)
        if len(history) >= 10:
            required_pause = min(required_pause, 75.0)

        return self.timeSinceLastMessage > required_pause
    def run(self):
        runtime_logger.info("Prompter loop started (generated initiative)")
        last_debug_time = time.time()

        while not self.signals.terminate:
            if self.signals.last_message_time == 0.0:
                self.signals.last_message_time = time.time()
                self.timeSinceLastMessage = 0.0
            else:
                if not self.system_ready:
                    runtime_logger.info("SYSTEM READY")
                    self.system_ready = True

            self.timeSinceLastMessage = time.time() - self.signals.last_message_time

            if time.time() - last_debug_time > 15:
                runtime_logger.info(f"[Prompter] timeSince={self.timeSinceLastMessage:.1f}s")
                last_debug_time = time.time()

            if self.prompt_now():
                self.proactive_attempts += 1
                runtime_logger.info(f"PROMPTER_TRIGGER | attempt={self.proactive_attempts}")

                if self.proactive_attempts > self.max_proactive_attempts:
                    runtime_logger.warning("PROMPTER_PAUSE | too many proactive attempts")
                    time.sleep(max(PATIENCE, 120))
                    self.proactive_attempts = 0
                    continue

                self.signals.AI_thinking = True
                proactive_text = self._generate_proactive_message()
                self.signals.AI_thinking = False
                if proactive_text:
                    self.llm_callback(proactive_text)
                    self.signals.last_message_time = time.time()
                    self.timeSinceLastMessage = 0.0
                    self.proactive_attempts = 0
                    time.sleep(5)
            else:
                if self.signals.new_message:
                    self.proactive_attempts = 0

            time.sleep(0.1)
