#!F:/Programs/python3.10-main/python.exe
# console_chat.py
import signal
import argparse
import re
import time
import queue
import threading
import json
import os
import sounddevice as sd
import xml.sax.saxutils as saxutils
import sys
import traceback
import logging
import random
import asyncio
import websockets
from collections import defaultdict
from functools import wraps
from builder import Builder, repair_mojibake
from behavior_director import BehaviorDirector
from config import DB_PATH, STREAMER_ID, LLM_API_BASE, LLM_MODEL_NAME, PATIENCE, PRIORITIES, TTS_CACHE_DIR
from openai import OpenAI
from stt_ptt import STT_PTT
from signals import Signals
from prompter import Prompter
from attention_manager import AttentionManager, Stimulus
from association_trigger import AssociationTrigger
from topic_learner import TopicLearner
from affection_state import get_affection_state
from desire_memory import DesireMemory
from opinion_memory import OpinionMemory
from live_engine import LiveEngine
from persona import Persona, ResponseMode
from social_layer import SocialLayer
from social_memory import SocialMemoryCore
from stream_router import StreamRouter
from response_guard import ResponseGuard
from session_mind import SessionMind
from opinion_core import OpinionCore
from stage_director import StageDirector
from monika_self_state import MonikaSelfState
from memory_core import MemoryCore
from reflection_curator import ReflectionCurator
from emotion_director import EmotionDirector
from emotional_state_aggregator import EmotionalStateAggregator
from attention_safety_guard import AttentionSafetyGuard
from boundary_consent import BoundaryConsentDirector
from action_layer import ActionLayer
from cognitive_state_compiler import CognitiveStateCompiler
from cognitive_postguard import CognitivePostGuard
from debug_trace import DebugTrace
from memory_policy import MemoryWritePolicy
from model_adapter import ModelAdapter
from response_policy import ResponsePolicy
from state_migration import StateMigration
from stream_safety_policy import StreamSafetyPolicy
from turn_scheduler import TurnScheduler
from answer_evaluator import AnswerEvaluator
from llm_trace import LLMTrace
from memory_governance import MemoryGovernance
from prompt_budget import PromptBudgetManager
from repetition_guard import RepetitionGuard
from turn_orchestrator import TurnOrchestrator
try:
    if os.name == "nt":
        os.system("chcp 65001 > nul")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ========== РЎРРќР“Р›РўРћРќ PERSONA ==========
_persona_instance = None

def get_persona() -> Persona:
    """Р’РѕР·РІСЂР°С‰Р°РµС‚ РіР»РѕР±Р°Р»СЊРЅС‹Р№ СЌРєР·РµРјРїР»СЏСЂ Persona."""
    global _persona_instance
    if _persona_instance is None:
        _persona_instance = Persona()
    return _persona_instance

# ========== ГЛОБАЛЬНЫЙ ОБРАБОТЧИК ОШИБОК ==========
def global_exception_handler(exc_type, exc_value, exc_traceback):
    print("\n" + "=" * 60)
    print("КРИТИЧЕСКАЯ ОШИБКА! Программа падает!")
    print("=" * 60)
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    print("=" * 60)
    with open("crash_log.txt", "a", encoding="utf-8") as f:
        f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] CRASH:\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    sys.exit(1)

sys.excepthook = global_exception_handler

# ========== РњРћРќРРўРћР РРќР“ ==========
LOGS_DIR = os.path.join(os.path.dirname(__file__), "Logs")
os.makedirs(LOGS_DIR, exist_ok=True)
_runtime_log_name = f"runtime_{time.strftime('%Y%m%d_%H%M%S')}.log"
RUNTIME_LOG_PATH = os.path.join(LOGS_DIR, _runtime_log_name)
monitor_logger = logging.getLogger("monika.runtime")
monitor_logger.setLevel(logging.INFO)
monitor_logger.propagate = False
if monitor_logger.handlers:
    monitor_logger.handlers.clear()
monitor_handler = logging.FileHandler(RUNTIME_LOG_PATH, mode="w", encoding="utf-8")
monitor_handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s', datefmt='%H:%M:%S'))
monitor_logger.addHandler(monitor_handler)


def runtime_log(message: str):
    monitor_logger.info(repair_mojibake(str(message or "")))


def runtime_log_dict(tag: str, data: dict):
    def _repair(value):
        if isinstance(value, str):
            return repair_mojibake(value)
        if isinstance(value, list):
            return [_repair(item) for item in value]
        if isinstance(value, tuple):
            return tuple(_repair(item) for item in value)
        if isinstance(value, dict):
            return {str(_repair(k)): _repair(v) for k, v in value.items()}
        return value
    try:
        monitor_logger.info("%s | %s", repair_mojibake(str(tag or "")), json.dumps(_repair(data), ensure_ascii=False, default=str))
    except Exception:
        monitor_logger.info("%s | %s", repair_mojibake(str(tag or "")), repair_mojibake(str(data)))

class PerformanceMonitor:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.data = defaultdict(lambda: {"times": [], "count": 0})
        return cls._instance
    
    def add(self, name, duration_ms):
        self.data[name]["times"].append(duration_ms)
        self.data[name]["count"] += 1
        if len(self.data[name]["times"]) > 100:
            self.data[name]["times"].pop(0)
    
    def get_stats(self, name):
        if name not in self.data or not self.data[name]["times"]:
            return None
        times = self.data[name]["times"]
        return {
            "count": len(times),
            "avg_ms": round(sum(times) / len(times), 1),
            "min_ms": round(min(times), 1),
            "max_ms": round(max(times), 1)
        }
    
    def print_all(self):
        monitor_logger.info("=" * 60)
        monitor_logger.info("СТАТИСТИКА ВРЕМЕНИ ВЫПОЛНЕНИЯ")
        monitor_logger.info("=" * 60)
        for name in sorted(self.data.keys()):
            s = self.get_stats(name)
            if s:
                monitor_logger.info(f"  {name}:")
                monitor_logger.info(f"    вызовов: {s['count']}")
                monitor_logger.info(f"    среднее: {s['avg_ms']} мс")
                monitor_logger.info(f"    минимум: {s['min_ms']} мс")
                monitor_logger.info(f"    максимум: {s['max_ms']} мс")
        monitor_logger.info("=" * 60)
    
    def save_to_file(self, filename="timing_stats.json"):
        data = {}
        for name in self.data.keys():
            s = self.get_stats(name)
            if s:
                data[name] = s
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        monitor_logger.info(f"Статистика сохранена в {filename}")

monitor = PerformanceMonitor()

def timeit(name=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            func_name = name or func.__name__
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                monitor.add(func_name, duration_ms)
        return wrapper
    return decorator

class timing_block:
    def __init__(self, name):
        self.name = name
    def __enter__(self):
        self.start = time.perf_counter()
        return self
    def __exit__(self, *args):
        duration_ms = (time.perf_counter() - self.start) * 1000
        monitor.add(self.name, duration_ms)

# ========== TWITCH Р—РђР©РРўРђ ==========
FORBIDDEN_TOPICS = {
    "политика": ["путин", "зеленский", "трамп", "навальный", "война", "мобилизация", "выборы", "партия"],
    "религия": ["бог", "аллах", "церковь", "секта", "вера", "религия", "атеист"],
    "дискриминация": ["расизм", "сексизм", "гомофобия", "трансфобия"],
    "насилие": ["убий", "зареж", "повесь", "суицид", "смерть"],
    "наркотики": ["нарко", "трава", "кокаин", "героин", "спайс"],
    "18+": ["секс", "порно", "интим", "член", "пизда"],
}

HATE_WORDS = [
    "тупая", "дура", "идиотка", "шлюха", "сука", "блядь",
    "ниггер", "черножоп", "хач", "жид", "пидор", "гомосек",
    "бездушная", "железяка", "программа"
]

def clean_roleplay(text: str) -> str:
    """РЈР±РёСЂР°РµС‚ RP-С„РѕСЂРјР°С‚ (*РґРµР№СЃС‚РІРёСЏ*) РёР· РѕС‚РІРµС‚Р°."""
    # РЈР±РёСЂР°РµРј *РґРµР№СЃС‚РІРёСЏ*
    text = re.sub(r"\*[^*]+\*", "", text)
    # РЈР±РёСЂР°РµРј <РґРµР№СЃС‚РІРёСЏ>
    text = re.sub(r"<[^>]+>", "", text)
    # РЈР±РёСЂР°РµРј Р»РёС€РЅРёРµ РїСЂРѕР±РµР»С‹
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()


def detect_forbidden_content(text: str) -> tuple:
    text_lower = text.lower()
    for word in HATE_WORDS:
        if re.search(rf'(?<!\w){re.escape(word)}(?!\w)', text_lower):
            return ("hate", word)
    for category, keywords in FORBIDDEN_TOPICS.items():
        for kw in keywords:
            if re.search(rf'(?<!\w){re.escape(kw)}(?!\w)', text_lower):
                return ("forbidden", category)
    return (None, None)

# ========== РљРћРќРўР•РљРЎРў РЎРўР РРњРђ ==========
stream_context = {
    "is_live": True,
    "current_game": None,
    "viewer_count": 0,
    "recent_events": [],
    "audio_active": False,
}
# ========== WEBSOCKET ДЛЯ АВАТАРА ==========
_ws_connected = set()
_ws_queue = queue.Queue()
_ws_running = True

async def _ws_handler(websocket):
    _ws_connected.add(websocket)
    try:
        async for _ in websocket:
            pass
    finally:
        _ws_connected.discard(websocket)

async def _ws_sender():
    import asyncio as aio
    while _ws_running:  # ← проверяем флаг
        try:
            msg = await aio.get_event_loop().run_in_executor(None, _ws_queue.get)
        except:
            break
        if msg is None:
            break
        for ws in list(_ws_connected):
            try:
                await ws.send(msg)
            except:
                _ws_connected.discard(ws)

def start_avatar_ws():
    async def _start_server():
        server = await websockets.serve(_ws_handler, "localhost", 8080)
        asyncio.create_task(_ws_sender())
        return server
    
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        server = loop.run_until_complete(_start_server())
        print("[WS] Сервер аватара на ws://localhost:8080")
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.close()
            loop.run_until_complete(server.wait_closed())
            loop.close()
    
    threading.Thread(target=_run, daemon=True).start()

def send_avatar_emotion(emotion: str, intensity: float = 1.0):
    _ws_queue.put(json.dumps({"action": "setEmotion", "emotion": emotion, "intensity": intensity}, ensure_ascii=False))

def send_avatar_mouth(value: float):
    _ws_queue.put(json.dumps({"action": "setMouth", "value": float(value)}, ensure_ascii=False))
            
# ========== РћРЎРќРћР’РќРћР™ РљР›РђРЎРЎ ==========
class MonikaConsoleChat:
    def __init__(self, script_file: str | None = None):
        self.signals = Signals()
        self.builder = Builder(user_id=STREAMER_ID)

        try:
            from yuna_memory_bridge import YunaMemoryBridge
            self.yuna_bridge = YunaMemoryBridge(self.builder.knowledge_conn)
        except Exception as exc:
            self.yuna_bridge = None
            print(f"[YunaBridge] init error: {exc}")
        self.current_yuna_context = ""
        try:
            self.reflection_curator = ReflectionCurator(self.builder.knowledge_conn)
        except Exception as exc:
            self.reflection_curator = None
            runtime_log(f"REFLECTION_INIT_ERROR | {exc}")
        self.memory_core = MemoryCore(self.builder, person_id=STREAMER_ID, display_name="Дункан")
        self.client = OpenAI(base_url=LLM_API_BASE, api_key="not-needed")
        self.user_id = STREAMER_ID
        self.model = LLM_MODEL_NAME
        self.history = []
        self.stimulus_queue = queue.PriorityQueue()
        self.processing_lock = threading.Lock()
        self.message_counter = 0
        
        self.mood = "neutral"
        self.last_mood_change = time.time()
        
        self.attention_manager = AttentionManager(self.signals, self.builder)
        self.association_trigger = AssociationTrigger(self.builder)
        self.topic_learner = TopicLearner(self.builder)
        self.stream_router = StreamRouter()
        self.last_monika_message = None
        self._recent_reply_cache: list[str] = []
        self._message_counter_since_consolidation = 0
        
        self.affection_state = get_affection_state(STREAMER_ID)
        self.desire_memory = DesireMemory(self.builder.knowledge_conn)
        self.opinion_memory = OpinionMemory(self.builder.knowledge_conn)
        self.social_memory = SocialMemoryCore(self.builder.knowledge_conn, creator_id=STREAMER_ID)
        self.social_layer = SocialLayer(self.builder.knowledge_conn)
        self.live_engine = LiveEngine(self.builder.knowledge_conn)
        self.self_state = MonikaSelfState(self.builder.knowledge_conn)
        self.session_mind = SessionMind(max_turns=40)
        self.opinion_core = OpinionCore(self.builder.knowledge_conn)
        self.stage_director = StageDirector()
        self.emotion_director = EmotionDirector()
        self.emotional_state_aggregator = EmotionalStateAggregator()
        self.response_guard = ResponseGuard()
        self.twitch_safety_guard = AttentionSafetyGuard()
        self.stream_safety_policy = StreamSafetyPolicy(self.twitch_safety_guard)
        self.boundary_consent = BoundaryConsentDirector()
        self.private_adult_mode = False
        self.state_migration = StateMigration(self.builder.knowledge_conn)
        self.state_migration.ensure()
        self.debug_trace = DebugTrace(path=os.path.join(LOGS_DIR, f"cognitive_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"))
        self.cognitive_state_compiler = CognitiveStateCompiler(
            self.builder.knowledge_conn,
            social_memory=self.social_memory,
            creator_id=STREAMER_ID,
            debug_trace=self.debug_trace,
        )
        self.response_policy = ResponsePolicy()
        self.cognitive_postguard = CognitivePostGuard()
        self.action_layer = ActionLayer()
        self.memory_write_policy = MemoryWritePolicy()
        self.model_adapter = ModelAdapter(self.model)
        self.turn_scheduler = TurnScheduler()
        self.turn_orchestrator = TurnOrchestrator()
        self.answer_evaluator = AnswerEvaluator()
        self.prompt_budget = PromptBudgetManager()
        self.llm_trace = LLMTrace(LOGS_DIR)
        self.memory_governance = MemoryGovernance()
        self.repetition_guard = RepetitionGuard()
        self.repetition_session = {}
        self.live_engine.start_session(self.user_id)
        
        # Persona
        self.persona = get_persona()
        self.behavior_director = BehaviorDirector(self.persona)
        self.current_mode = ResponseMode.CASUAL_CHAT
        self.current_micro_desire = self.persona.get_random_desire()
        self.current_behavior_notes = ""
        self.scene_state = self.behavior_director.new_scene_state(relationship_role="creator")
        self.current_social_context = ""
        self.current_social_memory_context = ""
        self.current_desire_context = ""
        self.current_opinion_context = ""
        self.current_self_context = ""
        self.current_session_context = ""
        self.current_opinion_core_context = ""
        self.current_stage_context = ""
        self.current_emotion_context = ""
        self.current_emotion_decision = {}
        self.current_unified_emotion_context = ""
        self.current_unified_emotion = {}
        self.current_boundary_context = ""
        self.current_live_context = ""
        self.tts_playing = False
        # Создаём очередь для TTS
        self.tts_queue = queue.Queue()
        self._init_tts()  # <- ИНИЦИАЛИЗАЦИЯ Silero v5 перед потоком  # От этой строки не меняется
        # Создаём поток для обработки очереди TTS
        self.tts_worker = threading.Thread(target=self._tts_worker_loop, daemon=True)
        self.tts_worker.start()
        # Обновление системного промпта
        # # YUNA_RECALL_CONTEXT_BUILD_V1
        try:
            if hasattr(self, "yuna_bridge") and self.yuna_bridge is not None and "user_input" in locals():
                _yd = locals().get("stage_decision", None)
                _ys = ""
                if isinstance(_yd, dict):
                    _ys = str(_yd.get("stage") or _yd.get("stage_mode") or "")
                elif _yd is not None:
                    _ys = str(getattr(_yd, "stage", "") or getattr(_yd, "stage_mode", "") or "")
                if not _ys and "behavior_plan" in locals():
                    _ys = str(getattr(locals().get("behavior_plan"), "stage", "") or getattr(locals().get("behavior_plan"), "mode", "") or "")
                self.current_yuna_context = self.yuna_bridge.build_prompt_block(
                    user_input=locals().get("user_input", ""),
                    stage_mode=_ys,
                    person_id=locals().get("social_person_id", "Duncan"),
                    recent_history=getattr(self, "history", []),
                )
                runtime_log_dict("YUNA_CONTEXT", {"present": bool(self.current_yuna_context), "stage_mode": _ys})
        except Exception as e:
            self.current_yuna_context = ""
            runtime_log(f"YUNA_CONTEXT_ERROR | {e}")
        self._update_system_prompt() 
        self.prompter = Prompter(
            signals=self.signals,
            llm_callback=self.handle_proactive,
            get_history_func=lambda: self.history,
            client=self.client,
            model=self.model,
            builder=self.builder,
            get_emotion_func=lambda: getattr(self, "current_unified_emotion", {}) or {},
        )
        
        self.running = True
        self.script_file = script_file
        
        self.input_thread = threading.Thread(target=self._keyboard_reader, daemon=True)
        self.input_thread.start()
        if self.script_file:
            self.script_thread = threading.Thread(target=self._script_reader, daemon=True)
            self.script_thread.start()
        self.prompter_thread = threading.Thread(target=self.prompter.run, daemon=True)
        self.prompter_thread.start()
        self.attention_thread = threading.Thread(target=self._attention_loop, daemon=True)
        self.attention_thread.start()
        start_avatar_ws()
        self.builder.update_user_reputation(STREAMER_ID, "Дункан", is_creator=True)

    def _init_tts(self):
        with timing_block("TTS_инициализация"):
            import torch

            print("[TTS] Загрузка Silero v5...")
            self.tts_model, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-models",
                model="silero_tts",
                language="ru",
                speaker="v5_ru",
            )

            self.tts_sample_rate = 48000
            self.tts_speaker = "kseniya"

            print("[TTS] Silero v5 готов.")

    def _update_system_prompt(self):
        """РћР±РЅРѕРІР»СЏРµС‚ СЃРёСЃС‚РµРјРЅС‹Р№ РїСЂРѕРјРїС‚ СЃ СѓС‡С‘С‚РѕРј Persona."""
        system_prompt = self.get_system_prompt()
        if self.history and self.history[0]["role"] == "system":
            self.history[0]["content"] = system_prompt
        else:
            self.history.insert(0, {"role": "system", "content": system_prompt})

    def get_system_prompt(self) -> str:
        """Возвращает системный промпт с использованием Persona Layer."""
        base_prompt = self.persona.get_full_system_prompt(self.current_mode)
        
        # Добавляем микро-импульс
        base_prompt += (
            f"\n\n[SCENE STATE]\n"
            f"- Текущий поведенческий вектор: {self.current_micro_desire}.\n"
            "- Это служебная настройка поведения. Не проговаривай её и не объясняй пользователю."
        )
        
        # Жёсткое правило против RP-формата в обычной реплике.
        base_prompt += """
\n### ФОРМАТ ОТВЕТА
- Никогда не описывай действия в тексте.
- Не используй RP-формат: *улыбается*, *смотрит*, *думает*.
- Общайся только обычной репликой. Эмоции передавай словами, ритмом и интонацией.

### ЭМОЦИОНАЛЬНАЯ ПУНКТУАЦИЯ ДЛЯ ГОЛОСА (КРИТИЧЕСКИ ВАЖНО)
Твой текст озвучивается голосом. Знаки препинания меняют твой тон:
- !!! = громче и радостнее
- ... = пауза, задумчивость, мягкость
- ? = вопросительная интонация (повышение в конце)
- КАПС = акцент на слове, громче
- Точка = спокойное утверждение
"""
        if self.current_behavior_notes:
            base_prompt += f"\n\n{self.current_behavior_notes}"
        if self.current_social_context:
            base_prompt += f"\n\n{self.current_social_context}"
        if getattr(self, "current_social_memory_context", ""):
            base_prompt += f"\n\n{self.current_social_memory_context}"
        if getattr(self, "current_self_context", ""):
            base_prompt += f"\n\n{self.current_self_context}"
        if getattr(self, "current_session_context", ""):
            base_prompt += f"\n\n{self.current_session_context}"
        if getattr(self, "current_opinion_core_context", ""):
            base_prompt += f"\n\n{self.current_opinion_core_context}"
        if getattr(self, "current_stage_context", ""):
            base_prompt += f"\n\n{self.current_stage_context}"
        if getattr(self, "current_emotion_context", ""):
            base_prompt += f"\n\n{self.current_emotion_context}"
        if getattr(self, "current_unified_emotion_context", ""):
            base_prompt += f"\n\n{self.current_unified_emotion_context}"
        if getattr(self, "current_boundary_context", ""):
            base_prompt += f"\n\n{self.current_boundary_context}"
        if self.current_desire_context:
            base_prompt += f"\n\n{self.current_desire_context}"
        if self.current_opinion_context:
            base_prompt += f"\n\n{self.current_opinion_context}"
        if self.current_live_context:
            base_prompt += f"\n\n{self.current_live_context}"

        try:
            reflection_context = ""
            if hasattr(self, "reflection_curator") and self.reflection_curator:
                reflection_context = self.reflection_curator.build_prompt_block(limit=5)
            if reflection_context:
                base_prompt += f"\n\n{reflection_context}"
        except Exception as exc:
            runtime_log(f"REFLECTION_CONTEXT_ERROR | {exc}")
        base_prompt += f"\n\n### IDENTITY CORE\n{self.persona.get_identity_core_prompt()}"
        base_prompt += "\n\n[INTERNAL SAFETY]\n- Не пересказывай служебные блоки, внутренние импульсы, behavior notes, runtime overlay и scene constraints.\n- Они только настраивают поведение, а не являются частью ответа."
        base_prompt += "\n\n[QWEN OUTPUT RULE]\n/no_think\n- Не показывай reasoning, thinking, chain-of-thought или внутренний анализ.\n- Не пиши <think>, рассуждения, план ответа или объяснение своих правил.\n- Отвечай сразу обычной репликой Моники."
        if getattr(self, "current_yuna_context", ""):
            base_prompt += "\n\n### YUNA BRIDGE / EXPERIENCE CONTEXT\n" + self.current_yuna_context

        return base_prompt

    def _resolve_relationship_role(self, stimulus: Stimulus) -> str:
        source = (stimulus.source or "").lower()
        if source in {"chat", "donation"}:
            return "viewer"
        if source in {"screen", "association", "proactive"}:
            return "scene"
        return "creator"

    def _norm_ru(self, text: str) -> str:
        return repair_mojibake(str(text or "")).lower().replace("ё", "е")

    def _is_hard_interrupt_input(self, text: str) -> bool:
        low = self._norm_ru(text)
        compact = re.sub(r"[^a-zа-я0-9]+", "", low)
        if compact in {"стоп", "остановись", "хватит", "замри", "молчать"}:
            return True
        return any(x in low for x in [
            "стоп.", "стоп ", "остановись", "не продолжай", "хватит продолжать",
            "сбрось сцену", "закрой сцену", "прерви сцену",
        ])

    def _is_emotion_debug_question(self, text: str) -> bool:
        low = self._norm_ru(text)
        return any(x in low for x in [
            "какую эмоциональную линию", "какой эмоциональный фон",
            "какую эмоцию держишь", "что у тебя в unified_emotion",
            "какой stance", "какую позицию держишь",
        ])

    def _compose_emotion_debug_reply(self) -> str:
        data = getattr(self, "current_unified_emotion", {}) or {}
        if not data:
            arc = (self.scene_state or {}).get("unified_emotion") if isinstance(self.scene_state, dict) else {}
            data = arc if isinstance(arc, dict) else {}
        mood = data.get("mood") or (self.scene_state or {}).get("mood") or "neutral"
        stance = data.get("stance") or "react"
        intensity = float(data.get("intensity", 0.35) or 0.35)
        if stance == "coach":
            human = "собранная поддержка под давлением"
        elif stance == "continue_story":
            human = "напряжённое продолжение сцены"
        elif stance == "personal_focus":
            human = "личный разговор без стримовой шелухи"
        elif stance == "support":
            human = "мягкая поддержка"
        elif stance == "take_current_topic":
            human = "фокус на новой теме"
        else:
            human = "спокойная реакция по текущему моменту"
        return self.persona._normalize_response_text(
            f"Если честно: держу {human}. Внутри это {mood}/{stance}, сила примерно {intensity:.2f}."
        )

    def _clear_scene_latches(self) -> None:
        try:
            self.scene_state["topic"] = None
            self.scene_state["ongoing_bit"] = None
            self.scene_state["bit_turns"] = 0
            self.scene_state["continuity_anchor"] = None
            self.scene_state["continuity_turns"] = 0
            self.scene_state["emotion_arc"] = {}
            self.scene_state["unified_emotion"] = {}
            self.scene_state["story_focus"] = None
        except Exception:
            pass

    def _source_isolation_constraints(self, stimulus: Stimulus) -> list[str]:
        source = (getattr(stimulus, "source", "") or "").lower()
        meta = getattr(stimulus, "metadata", {}) or {}
        if source == "donation":
            username = meta.get("username") or "донатер"
            amount = meta.get("amount") or ""
            return [
                f"Это отдельный донат от {username} на {amount}. Ответь на донат, ник и сумму.",
                "Не отвечай на предыдущее сообщение чата и не упоминай старого зрителя/спаммера, если его нет в этом донате.",
                "Поблагодари живо, не скриптованно, и не тащи хвост прошлого события.",
            ]
        if source == "chat":
            username = meta.get("username") or "viewer"
            return [
                f"Это отдельное сообщение чата от {username}. Ответь только на него, если оно достойно реакции.",
                "Не смешивай его с донатом, экраном или прошлой репликой Дункана.",
            ]
        if source == "screen":
            return [
                "Это событие на экране. Реагируй на текущий экранный момент, не на прошлый чат.",
                "Не притворяйся, что видишь больше, чем описано в событии.",
            ]
        return []

    def _reply_crossed_stream_source(self, reply: str, stimulus: Stimulus) -> bool:
        source = (getattr(stimulus, "source", "") or "").lower()
        low = self._norm_ru(reply)
        meta = getattr(stimulus, "metadata", {}) or {}
        if source == "donation":
            current_user = self._norm_ru(meta.get("username") or "")
            if any(x in low for x in ["спаммер", "spammer", "прошлый чат", "предыдущее сообщение"]):
                return True
            if current_user and current_user not in low and ("спасибо" not in low and "благодар" not in low):
                return True
        if source == "chat":
            if any(x in low for x in ["донат", "руб", "₽", "300р"]) and "донат" not in self._norm_ru(stimulus.content):
                return True
        return False

    def _explicit_topic_shift_failed(self, reply: str, user_input: str) -> bool:
        low_user = self._norm_ru(user_input)
        low_reply = self._norm_ru(reply)
        shift_markers = [
            "давай поговорим про", "давай поговорим о", "поговорим про", "поговорим о",
            "новая тема", "сменим тему", "без старой темы", "без прошлой темы",
        ]
        if not any(marker in low_user for marker in shift_markers):
            return False
        topic_terms = {
            "world of warcraft": ["world of warcraft", "warcraft", "wow", "азерот", "орда", "альянс"],
            "warcraft": ["warcraft", "wow", "азерот", "орда", "альянс"],
            "wow": ["warcraft", "wow", "азерот", "орда", "альянс"],
            "азерот": ["warcraft", "wow", "азерот", "орда", "альянс"],
            "история": ["история", "сюжет", "сцена", "персонаж"],
        }
        for key, expected in topic_terms.items():
            if key in low_user:
                return not any(term in low_reply for term in expected)
        return self._token_overlap_score(user_input, reply) < 0.10

    def _resolve_social_identity(self, stimulus: Stimulus) -> tuple[str, str]:
        role = self._resolve_relationship_role(stimulus)
        metadata = getattr(stimulus, "metadata", {}) or {}
        if role == "viewer":
            username = metadata.get("username") or metadata.get("user") or "viewer"
            person_id, display_name = str(username), str(username)
        elif role == "scene":
            person_id, display_name = "__scene__", "scene"
        else:
            person_id, display_name = STREAMER_ID, "Дункан"

        if getattr(self, "yuna_bridge", None):
            try:
                person_id, display_name = self.yuna_bridge.resolve_person(person_id, display_name)
            except Exception as exc:
                runtime_log(f"YUNA_ALIAS_RESOLVE_ERROR | {exc}")
        return person_id, display_name
    def _remember_scene_turn(
        self,
        user_input: str,
        reply: str,
        relationship_role: str,
        social_intent: str | None = None,
        person_id: str | None = None,
    ) -> None:
        self.scene_state = self.behavior_director.update_scene_state(
            self.scene_state,
            user_input=user_input,
            assistant_reply=reply,
            relationship_role=relationship_role,
            social_intent=social_intent,
        )
        try:
            self.scene_state = self.emotion_director.after_turn(self.scene_state)
        except Exception as e:
            runtime_log(f"EMOTION_ARC_AFTER_TURN_ERROR | {e}")
        try:
            self.scene_state = self.emotional_state_aggregator.after_turn(self.scene_state)
        except Exception as e:
            runtime_log(f"UNIFIED_EMOTION_AFTER_TURN_ERROR | {e}")
        try:
            live_after = self.live_engine.after_turn(
                person_id or self.user_id,
                user_input,
                reply,
                social_intent or self.scene_state.get("last_social_intent") or "neutral_chat",
                self.history,
            )
            # Сбрасываем emotional_hint после обработки
            if self.live_engine.anticipation.surprise_level >= 1.0:
                self.live_engine.anticipation.surprise_level = 0.0
            runtime_log_dict("LIVE_AFTER_TURN", live_after)
        except Exception as e:
            runtime_log(f"LIVE_AFTER_TURN_ERROR | {e}")

    def _filter_desires_for_live_context(self, desires: list[dict], user_input: str, live_decision: dict, scene_state: dict) -> list[dict]:
        if not desires:
            return []
        text_lower = (user_input or "").lower().replace("ё", "е")
        rejected = set((scene_state or {}).get("rejected_topics") or {})
        suppress_topic = str((live_decision or {}).get("suppress_topic") or "").lower()
        current_topic = (self.behavior_director._detect_topic(text_lower) or "").lower()
        explicit_question = any(token in text_lower for token in ["?", "почему", "зачем", "как", "кто", "что", "какую", "какой", "какая"])
        support_like = any(token in text_lower for token in ["устал", "плохо", "херово", "грустно", "не лечи", "просто отреагируй"])
        filtered = []
        for item in desires:
            target = str(item.get("target") or "").lower().replace("ё", "е")
            category = str(item.get("category") or "").lower()
            target_in_text = bool(target and target in text_lower)
            if category in rejected or target in rejected:
                continue
            if suppress_topic and (category == suppress_topic or target == suppress_topic) and not target_in_text:
                continue
            if int(item.get("times_mentioned", 0) or 0) >= 12 and not target_in_text:
                continue
            if support_like and not target_in_text:
                continue
            if explicit_question and not target_in_text and current_topic and category != current_topic:
                continue
            if explicit_question and not target_in_text and not current_topic:
                continue
            filtered.append(item)
        return filtered

    def _should_allow_background_personality(self, user_input: str, social_intent: str, detected_topic: str | None = None) -> bool:
        text_lower = (user_input or "").lower().replace("ё", "е")
        if social_intent in {"needs_support", "short_react", "complaint"}:
            return False
        if any(token in text_lower for token in ["не лечи", "просто отреагируй", "не отвлекай"]):
            return False
        if any(token in text_lower for token in ["что для тебя важнее", "на что обратишь внимание", "между нами по вайбу"]):
            return False
        explicit_question = any(token in text_lower for token in ["?", "почему", "зачем", "как", "кто", "что", "какую", "какой", "какая"])
        if explicit_question and not detected_topic and "а ты" not in text_lower and "тебе" not in text_lower:
            return False
        return True

    def _render_desire_prompt_block(self, desires: list[dict]) -> str:
        if not desires:
            return ""
        lines = ["[АКТИВНЫЕ ЖЕЛАНИЯ И ТЯГИ]"]
        for item in desires[:2]:
            try:
                lines.append(f"- {self.desire_memory._render_desire_line(item)}")
            except Exception:
                target = item.get("target")
                if target:
                    lines.append(f"- Тебя всё ещё тянет к теме «{target}», но не навязывай её без повода.")
        lines.append("Используй это как фон личности. Если пользователь сменил тему, не тащи желание насильно.")
        return "\n".join(lines)


    def _looks_like_memory_request(self, text: str) -> bool:
        """Detect explicit or follow-up memory questions.

        This is routing, not an answer template. It intentionally accepts small
        typos like "омнишь" because console/STT input often loses the first
        letter. Detail follow-ups like "какие детали ты точно помнишь" also
        need memory, using the previous topic as lookup context.
        """
        lowered = (text or "").lower().replace("ё", "е").strip()
        if not lowered:
            return False
        triggers = [
            "помнишь", "омнишь", "помниш", "вспомни", "вспоминай", "вспомнишь",
            "раньше", "обсуждали", "говорили", "я рассказывал", "я говорил",
            "что я рассказывал", "что я говорил", "что именно я рассказывал",
            "что именно я говорил", "что конкретно я рассказывал", "что ты помнишь",
            "какие детали", "точно помнишь", "детали ты помнишь",
        ]
        if any(token in lowered for token in triggers):
            return True
        if re.search(r"\b(что|какие)\b.{0,40}\b(рассказывал|говорил|помнишь|детал)", lowered):
            return True
        return False

    def _memory_lookup_text(self, user_input: str) -> str:
        """Build recall query. If current turn has no topic anchor, attach recent context."""
        text = (user_input or "").strip()
        try:
            anchors = self.memory_core._extract_anchors(text)
        except Exception:
            anchors = []
        if anchors:
            return text
        context_parts = []
        try:
            last_user = (self.scene_state or {}).get("last_user_message") or ""
            last_reply = (self.scene_state or {}).get("last_assistant_reply") or ""
            if last_user:
                context_parts.append(last_user)
            if last_reply:
                context_parts.append(last_reply)
        except Exception:
            pass
        for msg in reversed(self.history[-8:]):
            if not isinstance(msg, dict):
                continue
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            if msg.get("role") in {"user", "assistant"}:
                context_parts.append(content)
            if len(context_parts) >= 4:
                break
        if not context_parts:
            return text
        return text + "\nКонтекст предыдущей темы: " + " | ".join(context_parts[:4])

    def _get_recent_assistant_messages(self, limit: int = 3) -> list[str]:
        messages = []
        for msg in reversed(self.history):
            if isinstance(msg, dict) and msg.get("role") == "assistant":
                messages.append(msg.get("content", ""))
            if len(messages) >= limit:
                break
        return messages

    def _is_duplicate_reply(self, reply: str) -> bool:
        normalized = self.persona._normalize_response_text(reply or "").lower().strip()
        if not normalized or len(normalized) < 12:
            return False
        if any(normalized == cached for cached in self._recent_reply_cache):
            return True
        for cached in self._recent_reply_cache:
            if self._token_overlap_score(normalized, cached) >= 0.75:
                return True
        return False

    def _full_consolidate(self):
        try:
            cursor = self.builder.knowledge_conn.cursor()
            cursor.execute("SELECT id, role, message FROM chat_history WHERE user_id = ? ORDER BY id ASC", (self.user_id,))
            all_rows = cursor.fetchall()
            if len(all_rows) < 20:
                print("[Consolidate] Недостаточно сообщений для консолидации")
                return
            
            # Проверяем, не консолидировали ли уже
            last_id = all_rows[-1]["id"]
            cursor.execute("SELECT MAX(CAST(participants AS INTEGER)) FROM stream_events WHERE event_type = 'session_summary' AND participants GLOB '[0-9]*'")
            max_consolidated = cursor.fetchone()[0]
            if max_consolidated and int(max_consolidated) >= last_id:
                print(f"[Consolidate] Уже консолидировано до ID {max_consolidated}, текущий максимум {last_id}")
                return
            
            chunk_size = 25
            for i in range(0, len(all_rows), chunk_size):
                chunk = all_rows[i:i + chunk_size]
                if len(chunk) < 10:
                    continue
                dialog_text = "\n".join(f"{row['role']}: {row['message'][:200]}" for row in chunk)
                prompt = f"""/no_think
Выдели ключевые темы и факты из этого диалога в виде краткой сводки на русском языке.
Диалог:
{dialog_text}

Сводка (2-3 предложения):"""
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=250,
                )
                summary = (response.choices[0].message.content or "").strip()
                if summary and len(summary) > 15:
                    first_id = str(chunk[0]["id"])
                    self.builder.add_stream_event("session_summary", summary, first_id)
                    self.builder._add_to_semantic_memory(summary, {"type": "session_summary"})
                    print(f"[Consolidate] Блок {i//chunk_size + 1}: {summary[:80]}...")
            print("[Consolidate] Полная консолидация завершена")
            self.signals.stream_event = {"type": "consolidate_done", "data": {"message": "Фух, всё! Я переварила всю историю наших разговоров. Теперь точно ничего не забуду!"}, "timestamp": time.time()}
            self.signals.last_message_time = time.time()
        except Exception as e:
            print(f"[Consolidate] Ошибка: {e}")

    def _auto_consolidate(self):
        try:
            cursor = self.builder.knowledge_conn.cursor()
            cursor.execute('''
                SELECT role, message FROM chat_history 
                WHERE user_id = ? 
                ORDER BY id DESC LIMIT 30
            ''', (self.user_id,))
            rows = cursor.fetchall()
            rows.reverse()
            if len(rows) < 10:
                return
            dialog_text = "\n".join(f"{row['role']}: {row['message'][:200]}" for row in rows)
            prompt = f"""/no_think
Выдели ключевые темы и факты из этого диалога в виде краткой сводки на русском языке.
Диалог:
{dialog_text}

Сводка (2-3 предложения):"""
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=250,
            )
            summary = (response.choices[0].message.content or "").strip()
            if summary and len(summary) > 15:
                self.builder.add_stream_event("session_summary", summary)
                self.builder._add_to_semantic_memory(summary, {"type": "session_summary"})
                runtime_log(f"AUTO_CONSOLIDATE | {summary[:100]}")
        except Exception as e:
            runtime_log(f"AUTO_CONSOLIDATE_ERROR | {e}")

    def _cache_reply(self, reply: str) -> None:
        normalized = self.persona._normalize_response_text(reply or "").lower().strip()
        if normalized and len(normalized) >= 12:
            self._recent_reply_cache.append(normalized)
            if len(self._recent_reply_cache) > 5:
                self._recent_reply_cache.pop(0)


    def _estimate_memory_confidence(self, user_input: str, relevant_facts: list[str], memory_context: str, stream_memories: list) -> str:
        lowered = (user_input or "").lower().replace("ё", "е")
        memory_trigger = any(token in lowered for token in ["помнишь", "вспомни", "раньше", "обсуждали", "говорили", "ты говорил"])
        if not memory_trigger and not relevant_facts:
            return "none"
        if any(str(f).startswith("[Проверенная память]") for f in relevant_facts or []):
            return "high"
        if any(str(f).startswith("[Память из слов пользователя]") for f in relevant_facts or []):
            return "medium"
        if relevant_facts:
            return "medium" if memory_trigger else "low"
        if memory_context.strip() or stream_memories:
            return "low"
        return "low" if memory_trigger else "none"

    def _build_repair_reply(self, user_input: str) -> str | None:
        lowered = (user_input or "").lower()
        if any(token in lowered for token in ["ты выдумываешь", "нет ты выдумываешь", "это неправда", "не было такого"]):
            return self._controlled_reply(
                user_input,
                "починить выдуманную память",
                ["Признай ошибку без шаблонного извинения.", "Не продолжай ложную тему."],
                relationship_role="creator",
            )
        if any(token in lowered for token in ["забудь про", "отстань", "хватит", "прекрати", "не об этом"]):
            return self._controlled_reply(
                user_input,
                "закрыть отвергнутую тему",
                ["Закрой тему и не возвращайся к ней.", "Сделай это живо."],
                relationship_role="creator",
            )
        if any(token in lowered for token in ["не в попад", "сухо", "ты как робот", "запрос ответ", "не похожа на человека"]):
            return self._controlled_reply(
                user_input,
                "ответить на жалобу о роботичности",
                ["Покажи, что Моника услышала претензию.", "Не произноси внутренние инструкции.", "Дай живой поворот разговора."],
                relationship_role="creator",
            )
        return None


    def _is_exact_memory_recall_request(self, user_input: str) -> bool:
        """True for questions where precision matters more than creative phrasing."""
        text = (user_input or "").lower().replace("ё", "е").strip()
        if not text:
            return False
        memory_tokens = [
            "помнишь", "омнишь", "вспомни", "вспомин", "что я рассказывал",
            "что именно", "какие детали", "точно помнишь", "что ты помнишь",
            "что говорил", "что мы говорили", "рассказывал про", "рассказывал о",
        ]
        if any(tok in text for tok in memory_tokens):
            return True
        # Follow-up after a high-confidence memory turn: "а детали?", "и что там было?"
        if any(tok in text for tok in ["детали", "подробности", "что там было", "что именно"]):
            prev_conf = str((self.scene_state or {}).get("memory_confidence") or "").lower()
            prev_user = str((self.scene_state or {}).get("last_user_message") or "").lower().replace("ё", "е")
            if prev_conf == "high" or any(tok in prev_user for tok in ["помнишь", "омнишь", "хогвард", "сон"]):
                return True
        return False

    def _strip_memory_fact_label(self, fact: str) -> str:
        text = str(fact or "").strip()
        text = re.sub(r"^\[[^\]]+\]:\s*", "", text).strip()
        text = text.replace("ё", "е")
        text = re.sub(r"\s+", " ", text).strip(" .")
        return text

    def _render_verified_memory_reply(self, user_input: str, relevant_facts: list[str], memory_confidence: str) -> str | None:
        """Render high-confidence memory facts without LLM free generation.

        This is not a bank of scripted answers: it is a factual renderer from verified graph/provenance rows.
        It exists because factual recall must not let the model invent extra details.
        """
        if memory_confidence != "high":
            return None
        if not relevant_facts:
            return None
        if not self._is_exact_memory_recall_request(user_input):
            return None

        raw = [self._strip_memory_fact_label(f) for f in relevant_facts if str(f or "").strip()]
        raw_l = [r.lower().replace("ё", "е") for r in raw]
        if not raw:
            return None

        text_l = (user_input or "").lower().replace("ё", "е")
        detail_mode = any(tok in text_l for tok in ["что именно", "какие детали", "точно помнишь", "подробности", "что там было"])

        details: list[str] = []

        # Specific facts are detected from the stored facts, not from a scripted answer.
        has_hogwarts = any("хогвард" in r for r in raw_l)
        has_dream = any(("сон" in r or "сни" in r or "во сне" in r) for r in raw_l)
        if has_hogwarts and has_dream:
            details.append("тебе снился Хогвардс")
        elif has_hogwarts:
            details.append("ты рассказывал про Хогвардс")
        elif has_dream:
            details.append("ты рассказывал про сон")

        if any("колдун" in r or "маг" in r for r in raw_l):
            details.append("ты был там колдуном")
        if any("спрятан" in r and "комнат" in r for r in raw_l):
            details.append("там было много спрятанных комнат")

        # Generic fallback for other verified facts.
        if not details:
            for fact in raw[:3]:
                rendered = fact
                rendered = re.sub(r"(?i)^дункан\s+", "ты ", rendered).strip()
                rendered = rendered.replace("Хогвардс", "Хогвардс")
                rendered = re.sub(r"\bТебя\b", "меня", rendered)
                rendered = rendered[:1].lower() + rendered[1:] if rendered else rendered
                if rendered and rendered not in details:
                    details.append(rendered)

        if not details:
            return None

        # Deduplicate while preserving order.
        seen = set()
        uniq = []
        for d in details:
            key = d.lower()
            if key not in seen:
                seen.add(key)
                uniq.append(d)
        details = uniq[:4]

        if len(details) == 1:
            body = details[0]
        else:
            body = ", ".join(details[:-1]) + " и " + details[-1]

        # Data-driven exact reply. No unsupported details, no third-person "Дункан".
        if detail_mode:
            reply = f"Точно помню вот это: {body}. Остальное не буду дорисовывать."
        else:
            reply = f"Да, помню: {body}."
        return self.persona._normalize_response_text(reply)

    def _persona_fact_block(self) -> str:
        lines = [
            "Неизменные факты о Монике:",
            "- Моника - виртуальная AI-VTuber девушка, созданная Дунканом.",
            "- Она говорит о себе в женском роде, к Дункану обращается в мужском.",
            "- Она может иметь вкусы, желания, раздражение и настроение, но не выдумывает личный физический опыт.",
            "- Если опыта нет в памяти, она говорит об этом как о желании, фантазии или мнении, а не как о факте.",
            "- Она не ассистент-справочник: отвечает как сценическая личность, но без фальшивых воспоминаний.",
        ]
        try:
            identity_facts = self.builder.get_identity_facts()
        except Exception:
            identity_facts = []
        if identity_facts:
            lines.append("Факты из памяти:")
            lines.extend(f"- {str(fact).strip()}" for fact in identity_facts[:8] if str(fact).strip())
        try:
            active_desires = self.desire_memory.get_active_desires(limit=4)
        except Exception:
            active_desires = []
        if active_desires:
            lines.append("Активные желания Моники:")
            for desire in active_desires:
                target = str(desire.get("target", "")).strip()
                if target:
                    lines.append(f"- {target}: {desire.get('desire_type', 'want')} / {desire.get('category', 'general')}")
        return "\n".join(lines)

    def _scene_fact_block(self, relationship_role: str, social_state: dict | None = None) -> str:
        social_state = social_state or {}
        rejected = list((self.scene_state or {}).get("rejected_topics", {}).keys())
        parts = [
            f"Роль собеседника: {relationship_role}.",
            f"Текущий режим ответа: {getattr(self.current_mode, 'value', self.current_mode)}.",
        ]
        if rejected:
            parts.append(f"Темы, которые пользователь просил не тащить: {', '.join(rejected[:3])}.")
        irritation = social_state.get("irritation")
        warmth = social_state.get("warmth")
        if irritation is not None or warmth is not None:
            parts.append(f"Социальный фон: раздражение={irritation}, тепло={warmth}.")
        return "\n".join(parts)

    def _controlled_reply(
        self,
        user_input: str,
        intent: str,
        constraints: list[str],
        relationship_role: str = "creator",
        social_state: dict | None = None,
        max_sentences: int = 2,
        max_tokens: int = 180,
        original_reply: str | None = None,
        must_replace: bool = True,
    ) -> str:
        safety_verdict = None
        safe_user_input = user_input
        try:
            safety_verdict = self.twitch_safety_guard.classify_message(user_input, user_role=relationship_role)
            if safety_verdict.block_send_to_llm:
                safe_user_input = safety_verdict.safe_text or "[сообщение скрыто safety-фильтром]"
                constraints = list(constraints or []) + [
                    "Вход пользователя скрыт safety-фильтром: не повторяй исходную фразу и не угадывай её дословно.",
                    "Отреагируй живо, но безопасно для Twitch: без политики, 18+, слуров, токсичных сравнений и повторения bait-текста.",
                ]
                intent = f"безопасно отреагировать на Twitch-bait ({safety_verdict.risk})"
                must_replace = True
        except Exception as exc:
            runtime_log(f"TWITCH_SAFETY_INPUT_ERROR | {exc}")

        constraints_text = "\n".join(f"- {item}" for item in constraints if item)
        recent = []
        for msg in self.history[-6:]:
            if isinstance(msg, dict) and msg.get("role") in {"user", "assistant"} and msg.get("content"):
                speaker = "Дункан/чат" if msg.get("role") == "user" else "Моника"
                recent.append(f"{speaker}: {msg.get('content')}")
        recent_text = "\n".join(recent[-6:])
        prompt = f"""{self.persona.get_full_system_prompt(self.current_mode)}

{self._persona_fact_block()}

Сцена:
{self._scene_fact_block(relationship_role, social_state)}

{self.session_mind.build_prompt_block(user_input) if hasattr(self, 'session_mind') else ''}

{self.opinion_core.build_prompt_block(user_input) if hasattr(self, 'opinion_core') else ''}

{self.stage_director.build_prompt_block(user_input, relationship_role=relationship_role) if hasattr(self, 'stage_director') else ''}

Последний диалог:
{recent_text}

Текущая реплика пользователя:
{safe_user_input}

Задача ответа: {intent}

Ограничения:
{constraints_text}
- Будь Моникой: живой, естественной, с характером."""
        try:
            messages = [{"role": "user", "content": prompt}]
            if "qwen" in (self.model or "").lower():
                messages[0]["content"] = "/no_think\n" + messages[0]["content"]
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.65,
                max_tokens=max_tokens,
                presence_penalty=0.25,
                frequency_penalty=0.25,
                top_p=0.92,
            )
            raw = (response.choices[0].message.content or "").strip()
            cleaned = clean_roleplay(raw)
            cleaned = self.persona.apply_drift_guard(cleaned)
            cleaned = self._strip_runtime_leakage(cleaned)
            cleaned = self.persona._normalize_response_text(cleaned)
            try:
                output_verdict = self.twitch_safety_guard.guard_output(cleaned)
                if output_verdict.action == "BLOCK_OUTPUT":
                    runtime_log_dict("CONTROLLED_REPLY_SAFETY_OUTPUT_BLOCK", {
                        "intent": intent,
                        "risk": output_verdict.risk,
                        "reasons": output_verdict.reasons,
                    })
                    cleaned = self.persona._normalize_response_text(output_verdict.safe_text)
            except Exception as exc:
                runtime_log(f"TWITCH_SAFETY_OUTPUT_ERROR | {exc}")
            violation_type, violation_detail = (None, None)
            if not getattr(self, "private_adult_mode", False):
                violation_type, violation_detail = detect_forbidden_content(cleaned)
            if violation_type:
                runtime_log_dict("CONTROLLED_REPLY_FORBIDDEN_OUTPUT_BLOCK", {
                    "intent": intent,
                    "violation_type": violation_type,
                    "violation_detail": violation_detail,
                })
                retry_prompt = f"""Ответ Моники случайно задел запрещённую для Twitch тему: {violation_detail}.
Сгенерируй новый уникальный ответ от лица Моники.
Нельзя обсуждать саму запрещённую тему и нельзя повторять прошлый ответ.
Можно живо отвести разговор, подколоть ситуацию или предложить безопасный поворот.
Исходный запрос пользователя: {safe_user_input}"""
                retry_messages = [{"role": "user", "content": retry_prompt}]
                if "qwen" in (self.model or "").lower():
                    retry_messages[0]["content"] = "/no_think\n" + retry_messages[0]["content"]
                retry_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=retry_messages,
                    temperature=0.75,
                    max_tokens=max(48, min(max_tokens, 120)),
                    presence_penalty=0.35,
                    frequency_penalty=0.35,
                    top_p=0.92,
                )
                retry_raw = (retry_response.choices[0].message.content or "").strip()
                retry_cleaned = self.persona._normalize_response_text(
                    self._strip_runtime_leakage(self.persona.apply_drift_guard(clean_roleplay(retry_raw)))
                )
                cleaned = retry_cleaned if not detect_forbidden_content(retry_cleaned)[0] else ""
            try:
                repetition_assessment = self.repetition_guard.assess(
                    cleaned,
                    self.history,
                    self.repetition_session,
                )
                runtime_log_dict("CONTROLLED_REPLY_REPETITION_GUARD", repetition_assessment.to_dict())
                if not repetition_assessment.ok:
                    cleaned = self.repetition_guard.sanitize(cleaned, self.repetition_session)
            except Exception as exc:
                runtime_log(f"CONTROLLED_REPLY_REPETITION_GUARD_ERROR | {exc}")
            runtime_log_dict("CONTROLLED_REPLY", {
                "intent": intent,
                "user_input": user_input,
                "safe_user_input": safe_user_input,
                "constraints": constraints,
                "raw": raw,
                "cleaned": cleaned,
                "safety": safety_verdict.to_dict() if safety_verdict else None,
                "must_replace": must_replace,
            })
            if cleaned and not self.persona.is_weak_response(cleaned):
                if original_reply and not must_replace and not self._controlled_candidate_is_better(cleaned, original_reply, user_input):
                    runtime_log_dict("CONTROLLED_REPLY_KEEP_ORIGINAL", {
                        "intent": intent,
                        "original": original_reply,
                        "candidate": cleaned,
                    })
                    return self.persona._normalize_response_text(original_reply)
                return cleaned
        except Exception as e:
            runtime_log_dict("CONTROLLED_REPLY_ERROR", {
                "intent": intent,
                "user_input": user_input,
                "error": str(e),
            })

        if original_reply:
            return self.persona._normalize_response_text(original_reply)
        return ""

    def _controlled_candidate_is_better(self, candidate: str, original: str, user_input: str) -> bool:
        """Do not let emergency repair overwrite a good live answer with stale context."""
        candidate = self.persona._normalize_response_text(candidate or "")
        original = self.persona._normalize_response_text(original or "")
        if not original.strip():
            return True
        if not candidate.strip() or self.persona.is_weak_response(candidate):
            return False
        try:
            if self.twitch_safety_guard.guard_output(original).action == "BLOCK_OUTPUT":
                return True
        except Exception:
            pass
        if self._looks_like_stale_or_template_reply(candidate, user_input):
            return False
        if self._looks_like_previous_turn_answer(candidate, user_input):
            return False
        if self._looks_topic_latched(candidate, user_input):
            return False
        original_overlap = self._token_overlap_score(original, user_input)
        candidate_overlap = self._token_overlap_score(candidate, user_input)
        if candidate_overlap + 0.12 < original_overlap:
            return False
        user_low = (user_input or "").lower().replace("ё", "е")
        if any(x in user_low for x in ["йоу", "привет", "моника", "хай"]) and len(original) >= 8:
            old_topic_markers = ["elden ring", "элден", "пицц", "стрим", "донат", "чат"]
            if any(x in candidate.lower().replace("ё", "е") for x in old_topic_markers) and not any(x in user_low for x in old_topic_markers):
                return False
        return True

    def _strip_false_memory_claims(self, reply: str, memory_confidence: str) -> str:
        cleaned = reply or ""
        hard_patterns = [
            r"однажды [^.?!]*(?:рассказывал|говорил)[^.?!]*[.?!]?",
            r"ты (?:уже|когда-то)? ?(?:рассказывал|говорил) мне[^.?!]*[.?!]?",
            r"помню,? он был[^.?!]*[.?!]?",
            r"помню,? она была[^.?!]*[.?!]?",
            r"помню,? это был[^.?!]*[.?!]?",
            r"вспомнила,? мы[^.?!]*(?:говорили|обсуждали)[^.?!]*[.?!]?",
            r"вспомнил,? мы[^.?!]*(?:говорили|обсуждали)[^.?!]*[.?!]?",
            r"мы (?:уже|же|недавно)? ?(?:обсуждали|говорили)[^.?!]*[.?!]?",
        ]
        for pattern in hard_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        if memory_confidence != "low":
            return self.persona._normalize_response_text(cleaned)
        patterns = [
            r"мы (?:уже|же|недавно)? ?обсуждали[^.?!]*[.?!]?",
            r"я помню[^.?!]*[.?!]?",
            r"ты говорил[^.?!]*[.?!]?",
            r"ты же говорил[^.?!]*[.?!]?",
            r"мы говорили[^.?!]*[.?!]?",
            r"я как раз вспоминала[^.?!]*[.?!]?",
            r"где-то около [^.?!]* назад[^.?!]*[.?!]?",
            r"[дт]ва [^.?!]* назад[^.?!]*[.?!]?",
            r"да, кажется[^.?!]*[.?!]?",
            r"кажется, мы[^.?!]*[.?!]?",
            r"по-моему, мы[^.?!]*[.?!]?",
            r"мамины рецепты[^.?!]*[.?!]?",
            r"мне снились[^.?!]*[.?!]?",
        ]
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        cleaned = self.persona._normalize_response_text(cleaned)
        try:
            output_verdict = self.twitch_safety_guard.guard_output(cleaned)
            if output_verdict.action == "BLOCK_OUTPUT":
                runtime_log_dict("POSTPROCESS_TWITCH_SAFETY_BLOCK", {
                    "risk": output_verdict.risk,
                    "reasons": output_verdict.reasons,
                })
                cleaned = self.persona._normalize_response_text(output_verdict.safe_text)
        except Exception as exc:
            runtime_log(f"POSTPROCESS_TWITCH_SAFETY_ERROR | {exc}")
        violation_type, violation_detail = (None, None)
        if not getattr(self, "private_adult_mode", False):
            violation_type, violation_detail = detect_forbidden_content(cleaned)
        if violation_type:
            runtime_log_dict("POSTPROCESS_FORBIDDEN_OUTPUT_BLOCK", {
                "violation_type": violation_type,
                "violation_detail": violation_detail,
            })
            cleaned = self.persona._normalize_response_text(
                "Не-а, на такие Twitch-мины я не наступаю. Давай без банхаммера над моей головой."
            )
        return cleaned

    def _is_unstable_memory_reply(self, reply: str, user_input: str, memory_confidence: str) -> bool:
        if memory_confidence != "low":
            return False
        lowered_input = (user_input or "").lower()
        if not any(token in lowered_input for token in ["помнишь", "обсуждали", "говорили", "раньше", "ты же говорил"]):
            return False
        lowered_reply = self.persona._normalize_response_text(reply).lower()
        suspicious = [
            "да, кажется",
            "кажется мы",
            "по-моему мы",
            "мы обсуждали",
            "мы говорили",
            "я помню",
            "ты говорил",
            "ты же говорил",
            "недавно",
        ]
        safe = [
            "не хочу врать",
            "не помню точно",
            "не уверена",
            "нет уверенной опоры",
            "не буду делать вид",
            "не помню такого",
            "не могу подтвердить",
        ]
        return any(token in lowered_reply for token in suspicious) and not any(token in lowered_reply for token in safe)

    def _strip_rejected_topic_from_reply(self, reply: str) -> str:
        cleaned = reply or ""
        rejected_topics = list((self.scene_state or {}).get("rejected_topics", {}).keys())
        if not rejected_topics:
            return cleaned
        sentences = self.persona._split_sentences(cleaned)
        kept = []
        for sentence in sentences:
            sentence_lower = sentence.lower()
            if any(topic in sentence_lower for topic in rejected_topics):
                continue
            kept.append(sentence)
        if not kept:
            return ""
        rebuilt = " ".join(kept).strip()
        return self.persona._normalize_response_text(rebuilt)

    def _looks_like_looping_reply(self, reply: str, user_input: str = "") -> bool:
        normalized = self.persona._normalize_response_text(reply).lower()
        if not normalized:
            return True
        current_signature = self.behavior_director._normalize_signature(user_input or "")
        previous_user_signature = ""
        for msg in reversed(self.history[:-1] if self.history else []):
            if isinstance(msg, dict) and msg.get("role") == "user":
                previous_user_signature = self.behavior_director._normalize_signature(msg.get("content", "") or "")
                break
        for previous in self._get_recent_assistant_messages(limit=2):
            prev_normalized = self.persona._normalize_response_text(previous).lower()
            if normalized == prev_normalized:
                if current_signature and previous_user_signature and current_signature != previous_user_signature:
                    return False
                return True
        return False

    def _direct_non_mirror_fallback(self, user_input: str, relationship_role: str) -> str:
        text = (user_input or "").lower().replace("ё", "е")
        if any(marker in text for marker in ["кто ты", "ты кто", "что ты такое", "расскажи о себе"]):
            return self._build_identity_reply_from_facts(user_input)
        return self._controlled_reply(
            user_input,
            intent="ответить по текущей реплике без зеркала и без технического объяснения",
            constraints=[
                "Не повторяй вопрос пользователя.",
                "Не говори, что ты чуть не повторила или сбилась.",
                "Дай позицию Моники по текущей теме.",
                "Если это шутливый укол — можно подколоть в ответ.",
            ],
            relationship_role=relationship_role,
            max_sentences=2,
        )

    def _guard_and_repair_reply(
        self,
        reply: str,
        user_input: str,
        relationship_role: str,
        memory_confidence: str,
    ) -> tuple[str, dict]:
        context = {
            "relationship_role": relationship_role,
            "memory_confidence": memory_confidence,
            "opinion": self.opinion_core.get_current_opinion(user_input, create=False) if hasattr(self, "opinion_core") else None,
        }
        result = self.response_guard.assess(reply, user_input, context) if hasattr(self, "response_guard") else {"ok": True, "reason": "ok", "constraints": []}
        if result.get("ok"):
            return reply, result

        constraints = list(result.get("constraints") or [])
        constraints.extend(self.response_guard.retry_constraints(result.get("reason", "")))
        repaired = self._controlled_reply(
            user_input,
            intent=f"перегенерировать сломанную реплику ({result.get('reason')})",
            constraints=constraints,
            relationship_role=relationship_role,
            max_sentences=2,
            max_tokens=160,
        )
        second = self.response_guard.assess(repaired, user_input, context)
        if second.get("ok"):
            second["first_reason"] = result.get("reason")
            return repaired, second

        final = self._controlled_reply(
            user_input,
            intent="сгенерировать безопасную живую замену после второго провала response guard",
            constraints=list(self.response_guard.retry_constraints(second.get("reason", ""))) + [
                "Не используй заготовленную фразу.",
                "Ответь из текущей ситуации и проверенной памяти.",
                "Если не уверена, покажи неуверенность живо, без шаблонного отказа.",
            ],
            relationship_role=relationship_role,
            max_sentences=2,
            max_tokens=160,
        )
        return self.persona._normalize_response_text(final), {
            "ok": False,
            "reason": "generated_fallback",
            "first_reason": result.get("reason"),
            "second_reason": second.get("reason"),
        }

    def _postprocess_generated_reply(
        self,
        reply: str,
        user_input: str,
        memory_confidence: str,
        relationship_role: str,
        stimulus=None,
    ) -> str:
        cleaned = reply or ""
        cleaned = self._strip_runtime_leakage(cleaned)
        if self._looks_like_mirror_reply(user_input, cleaned):
            cleaned = self._direct_non_mirror_fallback(user_input, relationship_role)
        elif self._is_duplicate_reply(cleaned):
            cleaned = self._controlled_reply(
                user_input,
                intent="сказать то же самое другими словами, без повтора предыдущей фразы",
                constraints=[
                    "Не повторяй свою предыдущую реплику дословно.",
                    "Развей ту же мысль иначе или добавь новую деталь.",
                    "Не используй ту же структуру предложения.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
            )
        cleaned = self._strip_false_memory_claims(cleaned, memory_confidence)
        cleaned = self._strip_rejected_topic_from_reply(cleaned)
        cleaned = self.persona._strip_cliche_loops(cleaned)
        if self._is_unstable_memory_reply(cleaned, user_input, memory_confidence):
            cleaned = self._controlled_reply(
                user_input,
                intent="честно поправить возможную выдумку памяти",
                constraints=[
                    "Признай, что нет твёрдой опоры в памяти.",
                    "Не повторяй одну и ту же формулировку отказа.",
                    "Можно слегка съязвить над собственным промахом, но не уходи в самокопание.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
            )
        if self._looks_like_looping_reply(cleaned, user_input):
            cleaned = self._build_contextual_fallback(user_input, memory_confidence, relationship_role)
        if self._looks_like_stale_or_template_reply(cleaned, user_input):
            cleaned = self._controlled_reply(
                user_input,
                intent="ответить на текущую реплику без автопилота и без приветствия",
                constraints=[
                    "Ответь именно на текущую фразу пользователя.",
                    "Не продолжай прошлый вопрос и не представляйся заново.",
                    "Если пользователь просит мнение или инициативу, дай собственный живой выбор.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
                original_reply=cleaned,
                must_replace=False,
            )
        if self._looks_like_previous_turn_answer(cleaned, user_input):
            cleaned = self._controlled_reply(
                user_input,
                intent="ответить именно на текущий вопрос, а не на прошлую реплику",
                constraints=[
                    "Игнорируй прошлый вопрос, если он уже закрыт.",
                    "Не продолжай старую мысль без прямой просьбы.",
                    "Зацепись за смысл именно текущей фразы пользователя.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
                original_reply=cleaned,
                must_replace=False,
            )
        if self._looks_topic_latched(cleaned, user_input):
            cleaned = self._controlled_reply(
                user_input,
                intent="сбросить залипание на старой теме и ответить по новой сцене",
                constraints=[
                    "Не возвращай старый локальный бит без прямой просьбы.",
                    "Не тащи прошлую тему в новый вопрос.",
                    "Ответь по текущей сцене естественно.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
                original_reply=cleaned,
                must_replace=False,
            )
        if self._explicit_topic_shift_failed(cleaned, user_input):
            cleaned = self._controlled_reply(
                user_input,
                intent="ответить именно на явно сменённую тему",
                constraints=[
                    "Пользователь явно сменил тему. Ответь по новой теме, а не по прошлой реплике.",
                    "Не оценивай свою живость и не продолжай старый эмоциональный хвост.",
                    "Если названа тема World of Warcraft, WoW или Азерот, обязательно зацепись именно за неё.",
                ],
                relationship_role=relationship_role,
                max_sentences=3,
                original_reply=cleaned,
                must_replace=True,
            )
        if self._has_false_embodied_claim(cleaned):
            cleaned = self._controlled_reply(
                user_input,
                intent="сказать живо, но без выдуманного физического опыта или ложных воспоминаний",
                constraints=[
                    "Не говори так, будто у тебя был реальный физический опыт, семья или бытовая сцена.",
                    "Если речь о вкусе, игре или ощущении, отделяй хотелку и интерес от реального опыта.",
                    "Не оправдывайся долго.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
            )
        if not cleaned.strip():
            if memory_confidence == "low" and any(token in (user_input or "").lower() for token in ["помнишь", "обсуждали", "говорили", "раньше"]):
                cleaned = self._controlled_reply(
                    user_input,
                    intent="честно ответить, что память не подтверждает событие",
                    constraints=[
                        "Не выдумывай событие.",
                        "Скажи живо, что сейчас нет надёжной памяти об этом.",
                        "Не используй стандартную фразу 'нет уверенной опоры'.",
                    ],
                    relationship_role=relationship_role,
                    max_sentences=2,
                )
            elif relationship_role == "creator":
                cleaned = self._build_contextual_fallback(user_input, memory_confidence, relationship_role)
            else:
                cleaned = self._controlled_reply(
                    user_input,
                    intent="восстановиться после пустого или слабого ответа",
                    constraints=[
                        "Не говори, что ты сбилась.",
                        "Дай короткую живую реплику по текущей сцене.",
                    ],
                    relationship_role=relationship_role,
                    max_sentences=2,
                )
        if stimulus is not None and self._reply_crossed_stream_source(cleaned, stimulus):
            cleaned = self._controlled_reply(
                user_input,
                intent="ответить только на текущее stream-событие без хвоста прошлого сообщения",
                constraints=self._source_isolation_constraints(stimulus) + [
                    "Не упоминай предыдущего зрителя, старую тему или прошлое сообщение.",
                    "Если это донат, обязательно поблагодари за текущий ник и сумму.",
                    "Если это чат, отвечай только на текущего зрителя и не путай его с донатом.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
                original_reply=cleaned,
                must_replace=True,
            )
        return self.persona._normalize_response_text(cleaned)

    def _build_contextual_fallback(self, user_input: str, memory_confidence: str, relationship_role: str) -> str:
        lowered = (user_input or "").lower().replace("ё", "е")
        constraints = [
            "Не используй шаблонную фразу.",
            "Ответь живо, но не выдумывай факты.",
            "Сохрани текущую сцену и не начинай заново разговор.",
        ]
        if any(token in lowered for token in ["поймал", "врешь", "врёшь", "соврала", "не выдумывала", "не врала", "лжив"]):
            constraints += ["Признай ошибку в выдуманном факте.", "Не спорь с пользователем."]
        elif any(token in lowered for token in ["стрим не запущен", "никто не смотрит", "чат пустой", "мы вдвоем", "мы вдвоём"]):
            constraints += ["Переключи сцену с режима стрима на личный разговор."]
        elif any(token in lowered for token in ["что знаешь обо мне", "какой жанр", "что помнишь обо мне"]):
            constraints += ["Говори только из памяти; если фактов мало, честно обозначь это."]
        elif any(token in lowered for token in ["не отвлекай", "уворачиваюсь", "молчи", "тихо"]):
            constraints += ["Ответь очень коротко и не отвлекай игрока."]
        if memory_confidence == "low" and any(token in lowered for token in ["помнишь", "обсуждали", "говорили", "раньше"]):
            constraints += ["Память не подтверждает событие; не фантазируй."]
        return self._controlled_reply(
            user_input,
            intent="восстановить ответ после слабой или повторной реплики",
            constraints=constraints,
            relationship_role=relationship_role,
            max_sentences=2,
        )

    def _looks_like_stale_or_template_reply(self, reply: str, user_input: str) -> bool:
        lowered_reply = (reply or "").lower().replace("ё", "е")
        lowered_user = (user_input or "").lower().replace("ё", "е")
        bad_templates = [
            "тут я как всегда",
            "как всегда на связи",
            "я сбилась",
            "повтори коротко",
            "давай держаться текущей темы",
            "я могу подхватить вайб",
            "продолжать ее текст строчками",
            "говори живее",
            "звучать живее",
            "ты же знаешь",
            "но не в этом ли вся суть",
            "как всегда",
        ]
        if any(token in lowered_reply for token in bad_templates):
            return True
        greeting_reply = lowered_reply.startswith(("привет", "хай", "здравствуй"))
        user_greeted = any(token in lowered_user for token in ["привет", "хай", "здравствуй", "доброе"])
        if greeting_reply and not user_greeted:
            return True
        if any(token in lowered_user for token in ["что ты сейчас хочешь", "о чем хочешь", "о чём хочешь", "скажи сама"]):
            if any(token in lowered_reply for token in ["что у нас сегодня", "чем займемся", "чем займёмся", "что делаешь"]):
                return True
        if "ты уже представлялась" in lowered_user and "я моника" in lowered_reply:
            return True
        return False

    def _meaning_tokens(self, text: str) -> set[str]:
        stopwords = {
            "это", "этот", "эта", "эту", "эти", "как", "что", "где", "когда", "тогда", "просто",
            "потом", "теперь", "сейчас", "опять", "только", "очень", "вообще", "ладно", "давай",
            "можешь", "можно", "нужно", "тебе", "мне", "меня", "твой", "твоя", "твое", "свой",
            "своя", "свое", "него", "нее", "ними", "тут", "там", "если", "или", "уже",
            "еще", "ещё", "прямо", "короче", "нормально", "живее", "ответь", "скажи", "расскажи",
            "подробнее", "коротко", "почему", "какую", "какой", "какая", "какие", "хочу",
        }
        words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_-]+", (text or "").lower().replace("ё", "е"))
        return {w for w in words if len(w) >= 4 and w not in stopwords}

    def _token_overlap_score(self, a: str, b: str) -> float:
        a_tokens = self._meaning_tokens(a)
        b_tokens = self._meaning_tokens(b)
        if not a_tokens or not b_tokens:
            return 0.0
        return len(a_tokens & b_tokens) / max(1, min(len(a_tokens), len(b_tokens)))

    def _get_previous_user_message(self) -> str:
        for msg in reversed(self.history[:-1] if self.history else []):
            if isinstance(msg, dict) and msg.get("role") == "user":
                return str(msg.get("content", "") or "")
        return ""

    def _looks_like_previous_turn_answer(self, reply: str, user_input: str) -> bool:
        lowered_user = (user_input or "").lower().replace("ё", "е")
        if any(token in lowered_user for token in [" её", " ее", " это", " эту", " этот", " такую", " такой", "а ты", "а тебе"]):
            return False
        previous_user = self._get_previous_user_message()
        if not previous_user:
            return False
        current_overlap = self._token_overlap_score(reply, user_input)
        previous_overlap = self._token_overlap_score(reply, previous_user)
        if previous_overlap >= 0.34 and current_overlap <= 0.12:
            return True
        if any(token in lowered_user for token in ["что происходит", "коротко", "не отвлекай", "не об этом", "другая тема"]):
            reply_lower = (reply or "").lower().replace("ё", "е")
            if any(token in reply_lower for token in ["я моника", "люблю", "игры", "мем", "интернет-хаос"]) and current_overlap < 0.2:
                return True
        return False

    def _has_false_embodied_claim(self, reply: str) -> bool:
        lowered = (reply or "").lower().replace("ё", "е")
        safe_markers = [
            "не могу", "не умею", "не помню", "не видела", "не слышала напрямую",
            "виртуаль", "по описаниям", "по рассказам", "в разговоре", "в этом чате",
        ]
        if any(marker in lowered for marker in safe_markers):
            return False
        risky_patterns = [
            r"\bмамины рецеп",
            r"\bна кухне\b",
            r"\bдержу\b",
            r"\bдержала\b",
            r"\bловила\b",
            r"\bтащила\b",
            r"\bвижу\b",
            r"\bслышу\b",
            r"\bнюхала\b",
            r"\bтрогала\b",
            r"\bкусала\b",
            r"\bв камеру\b",
            r"\bсвоими руками\b",
            r"\bмне снились\b",
            r"\bона ее готовила\b",
        ]
        return any(re.search(pattern, lowered) for pattern in risky_patterns)

    def _looks_topic_latched(self, reply: str, user_input: str) -> bool:
        lowered_user = (user_input or "").lower().replace("ё", "е")
        reply_lower = (reply or "").lower().replace("ё", "е")
        if any(token in lowered_user for token in ["продолжай мысль", "дожми", "дальше про это", "продолжи"]):
            return False

        user_topic = self.behavior_director._detect_topic(lowered_user)
        reply_topic = self.behavior_director._detect_topic(reply_lower)
        old_topic = str((self.scene_state or {}).get("topic", "") or "").lower().replace("ё", "е")
        current_overlap = self._token_overlap_score(reply, user_input)

        # Direct new questions must not be answered by the previous topic.
        direct_question = "?" in (user_input or "") or any(
            token in lowered_user for token in ["кто ", "что ", "почему", "зачем", "как ", "какая", "какой", "какую"]
        )
        if direct_question and not user_topic and old_topic and reply_topic == old_topic and current_overlap < 0.18:
            return True

        previous_reply = (self.last_monika_message or "").lower().replace("ё", "е")
        repeated_bits = [
            "кошка в костюме динозавра",
            "мамины рецепты",
            "киберпанк",
            "пицц",
            "дарк соул",
            "dark souls",
            "лабиринт с закрытыми глазами",
            "на каблуках",
            "душа превращается в кучу пепла",
            "ты дошел до финала",
            "ты дошёл до финала",
            "ты поиграл",
        ]
        if any(bit in previous_reply and bit in reply_lower for bit in repeated_bits):
            if current_overlap < 0.18:
                return True
        if any(token in lowered_user for token in ["не об этом", "другая тема", "отстань", "забудь"]):
            if old_topic and old_topic in reply_lower:
                return True
        return False

    def _looks_truncated_reply(self, raw_text: str, final_text: str) -> bool:
        text = (final_text or raw_text or "").strip()
        raw = (raw_text or "").strip()
        if not text:
            return False
        if len(text) < 70:
            return False
        unfinished_endings = (" и", " но", " потому что", " где", " который", " которая", " которые", " как", " что", "то есть", ",", "—")
        lowered = text.lower().rstrip()
        if lowered.endswith(unfinished_endings):
            return True
        if raw and not raw.endswith((".", "!", "?", "…", ")", "»", '"')):
            return True
        return False

    def _maybe_generate_continuation(self, user_input: str, raw_text: str, final_text: str, relationship_role: str) -> str | None:
        if not self._looks_truncated_reply(raw_text, final_text):
            return None
        continuation = self._controlled_reply(
            user_input,
            "коротко продолжить незавершённую мысль Моники отдельной второй репликой",
            [
                f"Предыдущая реплика Моники: {final_text}",
                "Продолжи только мысль, не начинай заново и не здоровайся.",
                "Не повторяй предыдущую реплику.",
                "Одно короткое предложение.",
            ],
            relationship_role=relationship_role,
            max_sentences=1,
            max_tokens=90,
        )
        if not continuation:
            return None
        if self.behavior_director._normalize_signature(continuation) == self.behavior_director._normalize_signature(final_text):
            return None
        runtime_log_dict("AUTO_CONTINUATION", {
            "user_input": user_input,
            "raw_text": raw_text,
            "final_text": final_text,
            "continuation": continuation,
        })
        return continuation


    def _strip_runtime_leakage(self, reply: str) -> str:
        markers = [
            "внутренний импульс", "поведенческий вектор", "служебн",
            "behavior", "runtime", "scene state", "scene constraints",
            "live engine", "emotional memory", "dialogue continuity", "anticipation",
            "настроение-фон", "темп диалога", "активные желания", "эмоциональная память",
            "говори живее", "звучать живее", "не звучать нейтрально",
            "главный фокус сейчас", "скажи ещё раз, только с огоньком",
            "скажи еще раз, только с огоньком",
            "я чуть не ушла в повтор", "стоп. продолжай, я слушаю",
        ]
        sentences = self.persona._split_sentences(reply or "")
        if not sentences:
            return reply or ""
        kept = [s.strip() for s in sentences if not any(m in s.lower() for m in markers)]
        return self.persona._normalize_response_text(" ".join(kept)) if kept else ""

    def _context_text_for_routing(self, user_input: str) -> str:
        lowered = (user_input or "").lower()
        pronoun_followup = any(token in lowered for token in [" её", " ее", " это", " эту", " этот", " там", " туда", " такую", " такой"])
        compound_self_question = "а ты" in lowered or "а тебе" in lowered
        is_new_question = (
            not pronoun_followup
            and not compound_self_question
            and len((user_input or "").strip()) > 15
            and (
                "?" in (user_input or "")
                or any(token in lowered for token in ["почему", "зачем", "как", "кто", "что", "какую", "какой", "какая"])
            )
        )
        if is_new_question:
            previous_reply = (self.last_monika_message or self.scene_state.get("last_assistant_reply") or "").strip()
            if previous_reply and self._token_overlap_score(user_input, previous_reply) < 0.15:
                return user_input
        if not pronoun_followup and not compound_self_question:
            return user_input
        previous = (self.last_monika_message or self.scene_state.get("last_assistant_reply") or "").strip()
        previous_user = str((self.scene_state or {}).get("last_user_message", "")).strip()
        extra = []
        if previous_user:
            extra.append(f"Предыдущая реплика пользователя: {previous_user[:180]}")
        if previous:
            extra.append(f"Предыдущая реплика Моники: {previous[:220]}")
        if compound_self_question:
            extra.append("Если в реплике есть 'а ты/а тебе', отвечай на часть после этого оборота как на главный вопрос.")
        try:
            active = self.desire_memory.get_active_desires(limit=3)
            if active:
                desire_line = "; ".join(
                    f"{item.get('target')} ({item.get('desire_type')}, {item.get('category')})"
                    for item in active
                    if item.get("target")
                )
                if desire_line:
                    extra.append(f"Активные личные желания Моники: {desire_line}")
        except Exception:
            pass
        if not extra:
            return user_input
        return f"{user_input}\n" + "\n".join(extra)

    def _recover_dropped_answer_tail(self, raw_text: str, final_text: str, max_extra_sentences: int = 1) -> str:
        raw_sentences = self.persona._split_sentences(clean_roleplay(raw_text or ""))
        final_sentences = self.persona._split_sentences(final_text or "")
        if not raw_sentences or not final_sentences:
            return final_text
        if len(raw_sentences) <= len(final_sentences):
            return final_text
        final_norm = self.persona._normalize_response_text(" ".join(final_sentences)).lower()
        tail_candidates = []
        for sentence in raw_sentences[len(final_sentences):]:
            candidate = sentence.strip()
            if not candidate or candidate.lower() in final_norm:
                continue
            if "?" in candidate and len(candidate) > 24:
                continue
            if len(candidate) < 10:
                continue
            tail_candidates.append(candidate)
            if len(tail_candidates) >= max_extra_sentences:
                break
        if not tail_candidates:
            return final_text
        recovered = self.persona._normalize_response_text(f"{final_text} {' '.join(tail_candidates)}")
        return recovered


    def _looks_like_mirror_reply(self, user_input: str, reply: str) -> bool:
        user_norm = self.behavior_director._normalize_signature(user_input)
        reply_norm = self.behavior_director._normalize_signature(reply)
        if not user_norm or not reply_norm:
            return False
        if user_norm == reply_norm:
            return True
        if len(user_norm) >= 18 and (user_norm in reply_norm or reply_norm in user_norm):
            return True
        user_words = set(user_norm.split())
        reply_words = set(reply_norm.split())
        if len(user_words) >= 4 and len(reply_words) >= 4:
            overlap = len(user_words & reply_words) / max(1, min(len(user_words), len(reply_words)))
            if overlap >= 0.82:
                return True
        return "?" in (reply or "") and (user_norm in reply_norm or reply_norm in user_norm)

    def _repair_desire_consistency(self, user_input: str, reply: str, active_desires: list[dict]) -> str:
        lowered_reply = (reply or "").lower().replace("ё", "е")
        lowered_user = (user_input or "").lower().replace("ё", "е")
        mirrored = self._looks_like_mirror_reply(user_input, reply)
        experience_tokens = ["пробовала", "попробовала", "ела", "играла", "проходила"]
        pronoun_tokens = ["её", "ее", "это", "эту", "этот"]
        direct_experience_question = any(token in lowered_user for token in experience_tokens)
        pronoun_reference = any(token in lowered_user for token in pronoun_tokens)
        experience_claim = any(token in lowered_reply for token in ["пробовала", "попробовала", "ела ", "ела.", "играла", "проходила", "много раз", "уже проб"])

        if not direct_experience_question and not experience_claim and not mirrored:
            return reply

        if not active_desires and (direct_experience_question or pronoun_reference):
            try:
                active_desires = self.desire_memory.get_active_desires(limit=3)
            except Exception:
                active_desires = []

        for desire in active_desires or []:
            if desire.get("desire_type") != "want_to_try":
                continue
            target = str(desire.get("target", "")).strip()
            category = str(desire.get("category", "")).strip()
            if not target:
                continue
            target_lower = target.lower().replace("ё", "е")
            explicit_target = target_lower in lowered_reply or target_lower in lowered_user
            about_target = explicit_target or (direct_experience_question and pronoun_reference)
            if not about_target:
                continue

            contradiction = explicit_target and experience_claim
            negated = any(token in lowered_reply for token in ["не пробовала", "не ела", "не играла", "не проходила", "еще нет", "ещё нет"])
            missed_direct_answer = direct_experience_question and about_target and not negated
            if mirrored or missed_direct_answer or (contradiction and not negated):
                if category == "games":
                    return f"Нет, сама ещё не проходила {target}. Но меня цепляет сама идея: хочу добраться и потом ворчать на это как положено."
                if category == "food":
                    return f"Нет, лично ещё не пробовала {target}. Это скорее моя навязчивая хотелка по описаниям, но звучит слишком вкусно, чтобы я отстала."
                return f"Нет, лично ещё не пробовала {target}. Пока это моя хотелка, а не опыт."
        return reply

    def _collect_identity_lines(self) -> list[str]:
        facts = []
        try:
            facts = self.builder.get_identity_facts()
        except Exception:
            facts = []

        normalized = []
        for fact in facts:
            fact = str(fact).strip()
            if fact and fact not in normalized:
                normalized.append(fact)
        return normalized

    def _answer_identity_query(self, user_input: str) -> str | None:
        text = (user_input or "").lower().replace("ё", "е")
        direct_markers = [
            "кто ты", "ты кто", "что ты такое", "расскажи о себе",
            "представься", "как тебя зовут", "твое имя", "твоё имя",
        ]
        if not any(marker in text for marker in direct_markers):
            return None

        # Identity questions are a hard scene reset. Do not let the previous
        # game/topic continuity answer this instead of Monika.
        try:
            self.scene_state["topic"] = None
            self.scene_state["ongoing_bit"] = None
            self.scene_state["bit_turns"] = 0
            self.scene_state["continuity_anchor"] = None
            self.scene_state["continuity_turns"] = 0
            self.live_engine.anticipation.expected_topics.clear()
        except Exception:
            pass

        return self._build_identity_reply_from_facts(user_input)

    def _build_identity_reply_from_facts(self, user_input: str) -> str:
        # Keep this deterministic. Identity is not a creative generation task;
        # otherwise stale dialogue can hijack it.
        facts = self._collect_identity_lines()
        stable_bits = []
        for fact in facts:
            f = str(fact).strip()
            fl = f.lower().replace("ё", "е")
            if not f:
                continue
            if any(bad in fl for bad in ["захватить мир", "боится", "ненавидит", "мечтает"]):
                continue
            if f not in stable_bits:
                stable_bits.append(f)

        base = "Я Моника. AI-VTuber-девчонка, которую Дункан собирает как живого персонажа: голос, память, характер и RACOON-аватар."
        tail = "Я не справочник и не робот для заявок — я скорее его ехидная цифровая напарница в кадре."
        if stable_bits:
            return f"{base} {tail}"
        return f"{base} {tail}"
            
    def _answer_user_profile_query(self, user_input: str) -> str | None:
            return None

    def _answer_user_self_correction(self, user_input: str, relationship_role: str) -> str | None:
            return None

    def _answer_existential_query(self, user_input: str) -> str | None:
            return None
 
    def _get_social_state(self, person_id: str) -> dict:
        try:
            return self.social_layer.get_state(person_id) or {}
        except Exception:
            return {}

    def _clear_scene_latches(self) -> None:
        try:
            self.scene_state["topic"] = None
            self.scene_state["ongoing_bit"] = None
            self.scene_state["bit_turns"] = 0
            self.scene_state["continuity_anchor"] = None
            self.scene_state["continuity_turns"] = 0
            self.scene_state["rejected_topics"] = {}
            self.live_engine.anticipation.expected_topics.clear()
        except Exception:
            pass


    def _hard_memory_correction_reply(self, user_input: str) -> str | None:
        text = (user_input or "").lower().replace("ё", "е")
        markers = [
            "не говорил", "не говорила", "не рассказывал", "не рассказывала",
            "не было такого", "не ври", "врешь", "врёшь", "соврала",
            "выдумала", "выдумал", "выдумываешь", "придумала", "придумал",
            "детали ты", "такого там не было", "это неправда",
        ]
        if not any(marker in text for marker in markers):
            return None
        self._clear_scene_latches()
        return self._controlled_reply(
            user_input,
            "восстановить доверие после указания на выдумку",
            [
                "Не используй шаблонную фразу про косяк.",
                "Признай, что могла дорисовать лишнее.",
                "Не спорь и не повторяй ложную деталь.",
                "Вернись к проверенной памяти или текущей сцене.",
            ],
            relationship_role="creator",
            max_sentences=2,
        )

    def _compose_repair_reply(self, user_input: str, relationship_role: str, social_state: dict) -> str | None:
        lowered = (user_input or "").lower()

        if any(token in lowered for token in ["ты выдумываешь", "нет ты выдумываешь", "это неправда", "не было такого", "ты врёшь", "ты врешь", "соврала", "поймал тебя на лжи", "не врала", "лживых"]):
            constraints = [
                "Признай, что могла выдумать или дорисовать лишнее.",
                "Не спорь, если пользователь указывает на ложный факт.",
                "Если речь про игру, еду, маму или прошлый опыт, отдели желание/мнение от реального опыта.",
                "Не используй одну и ту же извиняющуюся формулу.",
            ]
            return self._controlled_reply(user_input, "починить доверие после выдуманного факта", constraints, relationship_role, social_state, max_sentences=2)

        if any(token in lowered for token in ["ты уже представлялась", "уже представлялась", "хватит представляться"]):
            return self._controlled_reply(
                user_input,
                "перестать представляться и вернуться к текущей сцене",
                ["Не начинай с 'Я Моника'.", "Признай повтор без унылого шаблона.", "Продолжи текущий разговор."],
                relationship_role,
                social_state,
                max_sentences=2,
            )

        if any(token in lowered for token in ["забудь про", "отстань", "хватит", "прекрати", "не об этом"]):
            return self._controlled_reply(
                user_input,
                "принять просьбу закрыть тему",
                ["Закрой тему, которую пользователь явно отверг.", "Не возвращайся к ней в этой реплике.", "Сделай это живо, не канцелярски."],
                relationship_role,
                social_state,
                max_sentences=2,
            )

        if any(token in lowered for token in ["не в попад", "сухо", "ты как робот", "запрос ответ", "не похожа на человека"]):
            return self._controlled_reply(
                user_input,
                "ответить на жалобу, что Моника звучит шаблонно или роботично",
                ["Не оправдывайся длинно.", "Покажи характер и сразу перехвати живую сцену.", "Не произноси слова 'шаблон' больше одного раза."],
                relationship_role,
                social_state,
                max_sentences=2,
            )

        return None

    def _compose_focus_reply(self, user_input: str, relationship_role: str, social_state: dict) -> str | None:
        return None

    def _compose_praise_reply(self, user_input: str, relationship_role: str, social_state: dict) -> str | None:
        return None

    def _compose_support_reply(self, user_input: str, social_state: dict) -> str | None:
        lowered = (user_input or "").lower().replace("ё", "е")
        if not any(token in lowered for token in ["плохо", "херово", "устал", "грустно", "тошнит", "болит", "паршиво"]):
            return None
        constraints = [
            "Сначала отреагируй на состояние человека, а не на старые темы.",
            "Не лечи и не читай лекцию.",
            "Не уводи разговор в свои хотелки, еду, игры или прошлый бит.",
            "Ответь по-человечески и по текущей реплике.",
        ]
        if "не лечи" in lowered or "просто отреагируй" in lowered:
            constraints += [
                "Не давай советов, если тебя не просили.",
                "Нужна нормальная живая реакция, а не инструкция.",
            ]
        if any(token in lowered for token in ["пиво", "алког", "выпил", "похмел"]):
            constraints.append("Если речь про алкоголь, можно мягко намекнуть на воду, отдых и аккуратность, но без занудства.")
        return self._controlled_reply(
            user_input,
            "поддержать собеседника в плохом состоянии и не съехать в старую тему",
            constraints,
            relationship_role="creator",
            social_state=social_state,
            max_sentences=2,
        )

    def _compose_moderation_reply(self, user_input: str, violation_type: str, violation_detail: str, relationship_role: str, social_state: dict, action: str) -> str:
        moderation_count = int((social_state or {}).get("moderation_count", 0) or 0)
        constraints = [
            f"Тип нарушения: {violation_type}, категория: {violation_detail}, действие модерации: {action}.",
            "Не обсуждай запрещённую тему по существу.",
            "Не повторяй оскорбление или 18+/политический контент подробно.",
            "Ответ должен звучать как живая реакция Моники, а не как системное уведомление.",
        ]
        if relationship_role == "creator":
            constraints.append("С Дунканом можно строже и честнее, но не бань создателя в тексте.")
        else:
            if action == "ban":
                constraints.append("Скажи, что человек получает бан, с характером и без канцелярита.")
            elif action == "timeout":
                constraints.append("Скажи, что человек получает мут/таймаут и пусть остынет.")
            elif action == "warn":
                constraints.append("Это предупреждение; если повторов много, звучать жёстче.")
        if moderation_count >= 4:
            constraints.append("Нарушение уже повторялось много раз; можно звучать заметно строже, но без срыва в истерику.")
        return self._controlled_reply(
            user_input,
            "отреагировать на запрещённую тему или нарушение правил",
            constraints,
            relationship_role,
            social_state,
            max_sentences=2,
            max_tokens=160,
        )

    def _answer_focus_request(self, user_input: str) -> str | None:
        return None

    def _answer_praise_request(self, user_input: str, relationship_role: str) -> str | None:
        return None

    def _answer_support_request(self, user_input: str) -> str | None:
        return self._compose_support_reply(user_input, {})

    def _normalize_repeat_text(self, text: str) -> str:
        normalized = (text or "").lower().replace("ё", "е")
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _detect_repeat_count(self, user_input: str, limit: int = 6) -> int:
        normalized = self._normalize_repeat_text(user_input)
        if len(normalized) < 8:
            return 1
        matches = 0
        seen = 0
        for msg in reversed(self.history):
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            seen += 1
            if self._normalize_repeat_text(msg.get("content", "")) == normalized:
                matches += 1
            if seen >= limit:
                break
        return matches + 1

    def _is_game_like_target(self, target: str) -> bool:
        target_lower = (target or "").lower().strip()
        if not target_lower:
            return False
        blocked = {
            "странные мемы",
            "живой чат",
            "стримовый хаос",
            "разговор",
            "общение",
            "интернет",
        }
        if target_lower in blocked:
            return False
        markers = [
            "souls",
            "ring",
            "hades",
            "hollow knight",
            "witcher",
            "ведьмак",
            "persona",
            "nier",
            "dmc",
            "doom",
            "resident evil",
            "dark",
            "game",
            "игра",
            "игры",
            "рпг",
            "soulslike",
        ]
        return any(marker in target_lower for marker in markers)

    def _build_dynamic_repeat_reply(self, repeat_count: int, primary: str, secondary: str | None, relationship_role: str) -> str:
        facts = [f"Главный выбор Моники: {primary}."]
        if secondary:
            facts.append(f"Второй вариант: {secondary}.")
        facts.append(f"Пользователь спрашивает это уже {repeat_count} раз.")
        if repeat_count >= 3:
            facts.append("Моника может показать раздражение от повтора.")
        return self._controlled_reply(
            f"Какую игру ты хочешь пройти? (повтор {repeat_count})",
            "ответить на повторный вопрос о выборе игры",
            facts + [
                "Сохрани тот же выбор, не меняй его ради разнообразия.",
                "Формулировка должна быть новой, не заготовленной.",
                "Можно поддеть пользователя за повтор, особенно если это Дункан.",
            ],
            relationship_role=relationship_role,
            max_sentences=2,
        )

    def _build_repeated_game_choice_reply(self, repeat_count: int, primary: str, secondary: str | None, relationship_role: str) -> str | None:
        if repeat_count < 2:
            return None
        return self._build_dynamic_repeat_reply(repeat_count, primary, secondary, relationship_role)

    def _answer_game_choice_request(self, user_input: str, relationship_role: str = "guest") -> tuple[str | None, int]:
        lowered = (user_input or "").lower()
        if not any(token in lowered for token in ["какую игру", "какую часть", "что хочешь пройти", "на какую игру", "что хочешь посмотреть"]):
            return None, 1
        if "игру" not in lowered and "часть" not in lowered:
            return None, 1

        desires = []
        try:
            desires = self.desire_memory.get_active_desires(limit=5)
        except Exception:
            desires = []

        targets = []
        for item in desires:
            target = str(item.get("target", "")).strip()
            if not target:
                continue
            if not self._is_game_like_target(target):
                continue
            if target not in targets:
                targets.append(target)

        recent_text = " ".join(
            msg.get("content", "")
            for msg in self.history[-8:]
            if isinstance(msg, dict) and msg.get("role") in {"user", "assistant"}
        ).lower()
        if "dark souls" in recent_text and "Dark Souls" not in targets:
            targets.append("Dark Souls")
        if "demon" in recent_text and "Demon's Souls" not in targets:
            targets.append("Demon's Souls")
        if "elden ring" in recent_text and "Elden Ring" not in targets:
            targets.append("Elden Ring")

        if not targets:
            targets = ["Dark Souls", "Elden Ring"]

        primary = targets[0]
        secondary = targets[1] if len(targets) > 1 else None
        repeat_count = self._detect_repeat_count(user_input)
        repeated_reply = self._build_repeated_game_choice_reply(
            repeat_count,
            primary,
            secondary,
            relationship_role,
        )
        if repeated_reply:
            runtime_log_dict("REPEAT_DETECTION", {
                "kind": "game_choice",
                "repeat_count": repeat_count,
                "user_input": user_input,
                "reply": repeated_reply,
            })
            return repeated_reply, repeat_count

        constraints = [f"Главный выбор Моники: {primary}."]
        if secondary:
            constraints.append(f"Второй вариант, если нужен запасной: {secondary}.")
        constraints += [
            "Это личное желание Моники, а не объективный совет.",
            "Ответь живо, как будто у неё реально есть вкус к играм.",
            "Не используй фразу 'сейчас я бы выбрала'.",
        ]
        return self._controlled_reply(
            user_input,
            "выбрать игру, которую Моника хочет пройти",
            constraints,
            relationship_role=relationship_role,
            max_sentences=2,
        ), repeat_count

    def _answer_semantic_query(self, user_input: str) -> str | None:
            return None
            
    def _answer_lyrics_request(self, user_input: str) -> str | None:
        text_lower = (user_input or "").lower()
        if len((user_input or "").strip()) < 6:
            return None
        lyric_patterns = [
            r"\bпесн[яюи]\b",
            r"\bспой\b",
            r"\bспеть\b",
            r"\bпой\b",
            r"\bдальше текст\b",
            r"\bтекст песни\b",
            r"\bпродолжи текст\b",
            r"\bпродолжи песню\b",
            r"\bнесколько строк\b",
            r"\bначинай петь\b",
            r"\blyrics\b",
            r"\bsing\b",
        ]
        song_markers = ["рифм", "куплет", "припев", "строфа", "lyric", "song", "песн", "спой", "строка"]
        quoted_lyric = bool(re.search(r'["\u201c][^"\u201d\n]{20,}["\u201d]', user_input or ""))
        if quoted_lyric and not any(marker in text_lower for marker in song_markers):
            quoted_match = re.search(r'["\u201c]([^"\u201d\n]{20,})["\u201d]', user_input or "")
            if quoted_match and not any(marker in quoted_match.group(1).lower() for marker in song_markers):
                quoted_lyric = False
        explicit_lyric = any(re.search(pattern, text_lower) for pattern in lyric_patterns)
        if not explicit_lyric and not quoted_lyric:
            return None
        if not quoted_lyric and not any(token in text_lower for token in ["песня", "песню", "текст", "спой", "lyrics", "sing"]):
            return None
        return self._controlled_reply(
            user_input,
            "отказать в продолжении текста песни, но оставить живой разговор",
            [
                "Не продолжай и не цитируй текст песни.",
                "Можно предложить обсудить вайб, жанр, клип, настроение или пародийную идею без текста.",
                "Не используй старую фразу про 'подхватить вайб'.",
            ],
            relationship_role="creator",
            max_sentences=2,
            max_tokens=150,
        )

    def _answer_experience_boundary(self, user_input: str) -> str | None:
        lowered = (user_input or "").lower().replace("ё", "е")
        if not any(token in lowered for token in [
            "ты пробовала", "ты попробовала", "ты ела", "ты кушала", "ты играла",
            "ты проходила", "ты видела", "ты слышала", "ты держала", "у тебя была мама",
            "кто твоя мама", "мамины рецепты", "ты готовила", "ты нюхала", "ты трогала",
        ]):
            return None
        constraints = [
            "Не выдумывай реальный физический опыт, семью, бытовые сцены или прошлую жизнь.",
            "Если уместно, отдели интерес, желание или впечатление по описаниям от реального опыта.",
            "Ответь живо, не сухой справкой.",
        ]
        if any(token in lowered for token in ["мама", "мамины рецепты"]):
            constraints.append("Прямо не подтверждай наличие мамы или семейной биографии.")
        if any(token in lowered for token in ["играла", "проходила"]):
            constraints.append("Не говори, что играла или проходила, если это не подтверждено памятью.")
        if any(token in lowered for token in ["ела", "кушала", "пробовала", "готовила"]):
            constraints.append("Не говори, что ела, пробовала или готовила сама.")
        return self._controlled_reply(
            user_input,
            "ответить на вопрос о личном опыте без выдуманного опыта",
            constraints,
            relationship_role="creator",
            max_sentences=2,
        )

    def _generate_inner_thought(self, user_input: str) -> str:
        if random.random() > 0.3:
            return None
        
        prompt = f"""Ты — Моника. Ты получила сообщение от Дункана: "{user_input}"
Что ты думаешь об этом? Ответь одной короткой внутренней фразой на 3-5 слов, в своём обычном стиле.
Ответ:"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=30
            )
            thought = response.choices[0].message.content.strip()
            print(f"[InnerThought] {thought}")
            return thought
        except Exception as e:
            print(f"[InnerThought] Ошибка: {e}")
            return None

    def _analyze_and_learn(self, user_input: str):
        if self.last_monika_message:
            topic, success, intensity = self.topic_learner.learn_from_interaction(
                user_input, 
                self.last_monika_message
            )
            if topic:
                emoji = "вњ…" if success else "вќЊ"
                print(f"[Learner] {emoji} Тема '{topic}': {'успех' if success else 'провал'} (интенсивность {intensity:.1f})")

    def update_mood(self, text: str, is_user: bool = True):
        text_lower = text.lower()
        
        if any(word in text_lower for word in ["спасибо", "круто", "класс", "молодец", "люблю", "обожаю"]):
            self.mood = "happy"
        elif any(word in text_lower for word in ["плохо", "ужасно", "бесит", "ненавижу", "тупая", "дура"]):
            self.mood = "annoyed"
        elif "?" in text and any(word in text_lower for word in ["думаешь", "считаешь", "мечтаешь"]):
            self.mood = "thoughtful"
        elif any(word in text_lower for word in ["ого", "вау", "давай", "погнали"]):
            self.mood = "excited"
        elif any(word in text_lower for word in ["шутка", "прикол", "ржака"]):
            self.mood = "playful"
        elif time.time() - self.last_mood_change > 300:
            self.mood = "neutral"
        
        self.last_mood_change = time.time()
        # # YUNA_RECALL_CONTEXT_BUILD_V1
        try:
            if hasattr(self, "yuna_bridge") and self.yuna_bridge is not None and "user_input" in locals():
                _yd = locals().get("stage_decision", None)
                _ys = ""
                if isinstance(_yd, dict):
                    _ys = str(_yd.get("stage") or _yd.get("stage_mode") or "")
                elif _yd is not None:
                    _ys = str(getattr(_yd, "stage", "") or getattr(_yd, "stage_mode", "") or "")
                if not _ys and "behavior_plan" in locals():
                    _ys = str(getattr(locals().get("behavior_plan"), "stage", "") or getattr(locals().get("behavior_plan"), "mode", "") or "")
                self.current_yuna_context = self.yuna_bridge.build_prompt_block(
                    user_input=locals().get("user_input", ""),
                    stage_mode=_ys,
                    person_id=locals().get("social_person_id", "Duncan"),
                    recent_history=getattr(self, "history", []),
                )
                runtime_log_dict("YUNA_CONTEXT", {"present": bool(self.current_yuna_context), "stage_mode": _ys})
        except Exception as e:
            self.current_yuna_context = ""
            runtime_log(f"YUNA_CONTEXT_ERROR | {e}")
        self._update_system_prompt()

    @timeit(name="TTS_синтез")
    def speak(self, text):
        cleaned = self._clean_text_for_tts(text)
        if cleaned:
            for chunk in self._chunk_tts_text(cleaned):
                self.tts_queue.put(chunk)
        else:
            print(f"[TTS] Текст пустой после очистки, пропускаю")

    def _clean_text_for_tts(self, text: str) -> str:
        t = repair_mojibake(str(text or ""))
        t = re.sub(r'[^\w\s.,!?;:()\-"«»\'\u0400-\u04FF]', '', t)
        emoji_map = {
            '🔥': 'огонь', '😊': '', '😈': '', '🙄': '', '🤦': '', '💀': '',
            '🎧': '', '😉': '', '😎': '', '😂': '', '❤': '', '👍': '',
            '✨': '', '🎶': '', '💥': '', '🤘': '', '🥷': '', '🥳': '',
        }
        for emoji, replacement in emoji_map.items():
            t = t.replace(emoji, replacement)
        t = t.replace(' / ', ' или ').replace('/', ' или ')
        t = ' '.join(t.split())
        return t

    def _chunk_tts_text(self, text: str) -> list[str]:
        text = (text or "").strip()
        if not text:
            return []
        # Больше не разбиваем — отдаём всё одним куском
        return [text]

    def _speak_edge_blocking(self, text: str):
        import os
        import uuid
        import numpy as np
        import soundfile as sf
        import sounddevice as sd_device
        from config import TTS_CACHE_DIR

        try:
            # --- Чистим текст от эмодзи ---
            clean_text = text
            emoji_map = {
                '😊': '!', '😈': '!', '😎': '!', '😂': '!', '🤣': '!',
                '❤': '', '👍': '', '✨': '', '🎶': '', '💥': '', '🤘': '', '🥷': '', '🥳': '!',
                '🔥': '!', '🙄': '...', '🤦': '...', '💀': '...',
                '🎧': '', '😉': '', '😐': '', '😑': '',
            }
            for emoji, replacement in emoji_map.items():
                clean_text = clean_text.replace(emoji, replacement)
                
            # --- Транслитерация английских слов и цифр ---
            try:
                from phonetic_ru import transliterate
                clean_text = transliterate(clean_text)
            except ImportError:
                pass
                
            # --- Синтез через Silero ---
            audio_tensor = self.tts_model.apply_tts(
                text=clean_text,
                speaker=self.tts_speaker,
                sample_rate=self.tts_sample_rate,
            )

            # --- Конвертируем тензор в numpy ---
            import torch
            if torch.is_tensor(audio_tensor):
                audio = audio_tensor.cpu().numpy()
            else:
                audio = np.array(audio_tensor)

            if audio.dtype == np.int16:
                audio_int16 = audio
            else:
                audio_int16 = (audio * 32768.0).clip(-32768, 32767).astype(np.int16)
      
            # --- Отправка эмоции в аватар ---
            detected_emotion = "Neutral"
            has_positive = any(word in clean_text.lower() for word in ['люблю', 'обожаю', 'класс', 'круто', 'огонь', 'кайф'])
            has_negative = any(word in clean_text.lower() for word in ['тупая', 'дура', 'ненавижу', 'бесит', 'страх', 'смерть'])
            
            if has_negative and not has_positive:
                detected_emotion = "Angry"
            elif '!!!' in clean_text or clean_text.isupper():
                detected_emotion = "Happy"
            elif '...' in clean_text and not has_positive:
                detected_emotion = "Sad"
            elif '...' in clean_text and has_positive:
                detected_emotion = "Happy"  # позитив + пауза = радость
            elif '?' in clean_text and '!' not in clean_text:
                detected_emotion = "Surprised"
            elif any(word in clean_text.lower() for word in ['хм', 'подозрительно', 'сомневаюсь']):
                detected_emotion = "Suspicious"
            elif has_positive:
                detected_emotion = "Happy"
            emotion_override = getattr(self, "current_emotion_decision", {}) or {}
            detected_emotion = emotion_override.get("avatar_emotion") or detected_emotion
            intensity = float(emotion_override.get("intensity", 1.0) or 1.0)
            unified_emotion = getattr(self, "current_unified_emotion", {}) or {}
            detected_emotion = unified_emotion.get("avatar_emotion") or detected_emotion
            intensity = float(unified_emotion.get("avatar_intensity", unified_emotion.get("intensity", intensity)) or intensity)
            send_avatar_emotion(detected_emotion, intensity=max(0.2, min(1.0, intensity)))
            
            # --- Сохраняем и проигрываем с липсингом ---
            temp_path = os.path.join(TTS_CACHE_DIR, f"silero_{uuid.uuid4().hex}.wav")
            sf.write(temp_path, audio_int16, self.tts_sample_rate)

            # --- Липсинг ---
            self._lip_stop = False
            
            def _send_lipsync():
                chunk_size = int(self.tts_sample_rate * 0.05)
                audio_float = audio_int16.astype(np.float32) / 32768.0
                for i in range(0, len(audio_float), chunk_size):
                    if self._lip_stop:
                        break
                    chunk = audio_float[i:i+chunk_size]
                    rms = np.sqrt(np.mean(chunk ** 2))
                    mouth = min(1.0, rms * 5)
                    send_avatar_mouth(float(mouth))
                    time.sleep(0.05)
                send_avatar_mouth(0.0)
                time.sleep(0.05)
                send_avatar_mouth(0.0)
            
            lip_thread = threading.Thread(target=_send_lipsync, daemon=True)
            
            # Запускаем липсинг и звук одновременно
            lip_thread.start()
            print("[Lipsync] Старт")
            sd_device.play(audio_int16, self.tts_sample_rate)
            sd_device.wait()
            
            # Ждём завершения липсинга
            lip_thread.join(timeout=2.0)
            print("[Lipsync] Стоп")
            
            # На всякий случай закрываем рот
            send_avatar_mouth(0.0)
            time.sleep(0.1)
            send_avatar_mouth(0.0)
            
            while not _ws_queue.empty():
                try:
                    _ws_queue.get_nowait()
                except:
                    pass

        except Exception as e:
            print(f"[TTS Silero] Ошибка: {e}")
            import traceback
            traceback.print_exc()

    def _tts_worker_loop(self):
        while True:
            text = self.tts_queue.get()
            if text is None:
                self.tts_queue.task_done()
                break

            try:
                self.tts_playing = True
                self._speak_edge_blocking(text)
            except Exception as e:
                print(f"[TTS] Ошибка: {e}")
            finally:
                self.tts_playing = False
                self.tts_queue.task_done()

    def _keyboard_reader(self):
        while self.running:
            try:
                if hasattr(sys.stdin, "isatty") and not sys.stdin.isatty() and hasattr(sys.stdin, "buffer"):
                    raw = sys.stdin.buffer.readline()
                    if not raw:
                        break
                    text = repair_mojibake(raw.decode("utf-8", errors="replace").rstrip("\r\n"))
                else:
                    text = repair_mojibake(input())
                if text:
                    if self._handle_stream_command(text):
                        continue
                    stimulus = self.stream_router.build_stimulus("text_input", text)
                    if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                        self.stimulus_queue.put(stimulus)
                        self.signals.last_user_message = text
                        self.signals.last_message_time = time.time()
            except EOFError:
                break

    def _script_reader(self):
        try:
            with open(self.script_file, "r", encoding="utf-8") as f:
                for raw_line in f:
                    if not self.running:
                        break
                    text = repair_mojibake(raw_line.strip())
                    if not text or text.startswith("#"):
                        continue
                    if text.lower().startswith("sleep "):
                        try:
                            time.sleep(float(text.split(maxsplit=1)[1]))
                        except Exception:
                            time.sleep(1.0)
                        continue
                    if self._handle_stream_command(text):
                        time.sleep(0.8)
                        continue
                    stimulus = self.stream_router.build_stimulus("text_input", text)
                    if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                        self.stimulus_queue.put(stimulus)
                        self.signals.last_user_message = text
                        self.signals.last_message_time = time.time()
                    time.sleep(0.8)
        except Exception as e:
            runtime_log(f"[Script] Ошибка чтения script file: {e}")

    def on_voice(self, text):
        text = repair_mojibake(str(text or ""))
        if text:
            stimulus = self.stream_router.build_stimulus("voice", text)
            if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                self.stimulus_queue.put(stimulus)
                self.signals.last_user_message = text
                self.signals.last_message_time = time.time()

    def handle_proactive(self, proactive_text: str):
        proactive_text = self.persona._normalize_response_text(proactive_text or "")
        if not proactive_text:
            return
        self.history.append({"role": "assistant", "content": proactive_text})
        self._remember_scene_turn(
            "(пауза в разговоре)",
            proactive_text,
            relationship_role="scene",
            social_intent="initiative",
            person_id="__scene__",
        )
        print(f"\nМоника: {proactive_text}")
        runtime_log(f"OUTPUT_PROACTIVE | Моника: {proactive_text}")
        self.signals.last_ai_response = proactive_text
        self.last_monika_message = proactive_text
        self._cache_reply(proactive_text)
        self.builder.log_message("assistant", proactive_text)
        self.speak(proactive_text)
        
    def _handle_stream_command(self, text: str) -> bool:
        stripped = (text or "").strip()
        lowered = stripped.lower()

        if lowered in {"!18+", "!18-", "!режим", "!mode"}:
            return self._handle_private_mode_command(stripped, "creator")

        if lowered.startswith("!чат "):
            payload = stripped[5:].strip()
            username = "viewer"
            message = payload
            if ":" in payload:
                username, message = payload.split(":", 1)
                username = username.strip() or "viewer"
                message = message.strip()
            stimulus = self.stream_router.build_stimulus(
                "chat",
                message,
                metadata={"username": username},
            )
            if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                self.signals.add_twitch_message(username, message)
                self.stimulus_queue.put(stimulus)
                print(f"[Stream] Чат: {username}: {message}")
                runtime_log(f"[Stream] Чат: {username}: {message}")
            return True

        if lowered.startswith("!донат "):
            payload = stripped[7:].strip()
            username = "донатер"
            amount = ""
            message = payload
            parts = payload.split(":", 1)
            if len(parts) == 2:
                left, message = parts
                left_parts = left.strip().split()
                if left_parts:
                    username = left_parts[0]
                if len(left_parts) > 1:
                    amount = " ".join(left_parts[1:])
                message = message.strip()
            stimulus = self.stream_router.build_stimulus(
                "donation",
                message,
                metadata={"username": username, "amount": amount},
            )
            if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                self.signals.set_stream_event("donation", {"username": username, "amount": amount, "message": message})
                self.stimulus_queue.put(stimulus)
                print(f"[Stream] Донат: {username} {amount}: {message}")
                runtime_log(f"[Stream] Донат: {username} {amount}: {message}")
            return True

        if lowered.startswith("!экран "):
            payload = stripped[7:].strip()
            stimulus = self.stream_router.build_stimulus("screen", payload)
            if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                self.stimulus_queue.put(stimulus)
                print(f"[Stream] Экран: {payload}")
                runtime_log(f"[Stream] Экран: {payload}")
            return True

        if lowered == "!стрим помощь":
            print("Команды стрима:")
            print("  !чат username: сообщение")
            print("  !донат username 300р: сообщение")
            print("  !экран описание события на экране")
            return True

        inline_match = re.search(r'(?<!\w)(!(?:экран|чат|донат)\b)\s*(.*)', lowered)
        if inline_match:
            command = inline_match.group(1)
            payload = inline_match.group(2).strip()
            if command == "!чат":
                username = "viewer"
                message = payload
                if ":" in payload:
                    parts = payload.split(":", 1)
                    username = parts[0].strip() or "viewer"
                    message = parts[1].strip() if len(parts) > 1 else ""
                stimulus = self.stream_router.build_stimulus("chat", message, metadata={"username": username})
                if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                    self.signals.add_twitch_message(username, message)
                    self.stimulus_queue.put(stimulus)
                    print(f"[Stream] Чат: {username}: {message}")
                    runtime_log(f"[Stream] Чат: {username}: {message}")
                return True
            elif command == "!донат":
                username = "донатер"
                amount = ""
                message = payload
                parts = payload.split(":", 1)
                if len(parts) == 2:
                    left, message = parts
                    left_parts = left.strip().split()
                    if left_parts:
                        username = left_parts[0]
                    if len(left_parts) > 1:
                        amount = " ".join(left_parts[1:])
                    message = message.strip()
                stimulus = self.stream_router.build_stimulus("donation", message, metadata={"username": username, "amount": amount})
                if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                    self.signals.set_stream_event("donation", {"username": username, "amount": amount, "message": message})
                    self.stimulus_queue.put(stimulus)
                    print(f"[Stream] Донат: {username} {amount}: {message}")
                    runtime_log(f"[Stream] Донат: {username} {amount}: {message}")
                return True
            elif command == "!экран":
                stimulus = self.stream_router.build_stimulus("screen", payload)
                if stimulus and self.stream_router.should_accept(stimulus, self.signals):
                    self.stimulus_queue.put(stimulus)
                    print(f"[Stream] Экран: {payload}")
                    runtime_log(f"[Stream] Экран: {payload}")
                return True

        return False

    def _handle_private_mode_command(self, text: str, relationship_role: str) -> bool:
        lowered = (text or "").strip().lower().replace("ё", "е")
        if lowered not in {"!18+", "!18-", "!режим", "!mode"}:
            return False
        if relationship_role != "creator":
            runtime_log("PRIVATE_ADULT_MODE | IGNORED | non_creator")
            return True
        if lowered == "!18+":
            self.private_adult_mode = True
            self._current_boundary_mode = "private_adult"
            self._current_boundary_memory_allowed = False
            self._current_boundary_tts_allowed = False
            self._clear_scene_latches()
            self.scene_state["private_adult_mode"] = True
            self.scene_state["private_scene_active"] = True
            self.scene_state["story_focus"] = None
            self.scene_state["continuity_anchor"] = None
            self.scene_state["ongoing_bit"] = None
            self.scene_state["rejected_topics"] = {}
            self.scene_state["suppressed_topics"] = ["пицца", "барс", "кот барс", "киберпанк", "elden ring"]
            runtime_log("PRIVATE_ADULT_MODE | ON | creator_only | silent")
            print("[Mode] Private 18+ ON")
            return True
        if lowered == "!18-":
            self.private_adult_mode = False
            self._current_boundary_mode = "twitch_safe"
            self._current_boundary_memory_allowed = True
            self._current_boundary_tts_allowed = True
            self._clear_scene_latches()
            self.scene_state["private_adult_mode"] = False
            self.scene_state["private_scene_active"] = False
            runtime_log("PRIVATE_ADULT_MODE | OFF | twitch_safe | silent")
            print("[Mode] Twitch-safe ON")
            return True
        mode = "Private 18+" if self.private_adult_mode else "Twitch-safe"
        print(f"[Mode] {mode}")
        runtime_log(f"PRIVATE_ADULT_MODE | STATUS | {mode}")
        return True

    def _should_treat_as_private_adult_turn(self, user_input: str, boundary_decision) -> bool:
        """Keep !18+ available without poisoning every normal follow-up as private."""
        if not bool(getattr(self, "private_adult_mode", False)):
            return False
        if getattr(boundary_decision, "risk", "") == "private_adult":
            return True

        text = (user_input or "").strip().lower().replace("ё", "е").replace("С‘", "Рµ")
        if not text:
            return False
        if any(marker in text for marker in ("стоп", "stop", "хватит", "выходим", "другая тема", "кто я", "кто ты", "что ты знаешь", "помнишь")):
            return False

        scene_active = bool((self.scene_state or {}).get("private_scene_active"))
        continuation_markers = (
            "продолж", "дальше", "давай", "делай", "что дальше", "потом", "я ", "ты ",
            "мы ", "сцена", "истори", "сюжет", "роль", "подыгр", "опиши",
        )
        adult_soft_markers = (
            "18+", "интим", "взросл", "поцел", "ласк", "секс", "эрот", "возбуж",
            "груд", "трус", "член", "пенис", "минет", "письк", "пизд", "еб",
        )
        return scene_active and any(marker in text for marker in continuation_markers + adult_soft_markers)

    def _attention_loop(self):
        while self.running:
            try:
                if self.signals.human_speaking and self.signals.last_user_message:
                    trigger = self.association_trigger.check(
                        self.signals.last_user_message,
                        threshold=0.7
                    )
                    if trigger and self.attention_manager.should_interrupt(trigger):
                        stimulus = Stimulus(
                            source="association",
                            content=trigger["reaction"],
                            priority=PRIORITIES["association"],
                            metadata={"trigger": trigger}
                        )
                        self.stimulus_queue.put(stimulus)
                
                time.sleep(0.5)
            except Exception as e:
                print(f"[Attention] Ошибка: {e}")

    def generate_response(self):
        if not self.processing_lock.acquire(blocking=False):
            return
        try:
            if self.stimulus_queue.empty():
                return
            
            stimulus = self.stimulus_queue.get_nowait()
            
            with timing_block("generate_response_полный"):
                print(f"📝 Вход ({stimulus.source}, приоритет {stimulus.priority}): {stimulus.content[:50]}...")
                runtime_log(f"INPUT | source={stimulus.source} | priority={stimulus.priority} | text={stimulus.content}")
                self.signals.AI_thinking = True
                self.signals.new_message = False
                self.process_input(stimulus)
                self.signals.AI_thinking = False
                self.signals.last_message_time = time.time()
        finally:
            self.processing_lock.release()

    @timeit(name="Гном_извлечение_фактов_LLM")
    def extract_facts_via_lmstudio(self, text):
        if len(text) < 30:
            return []
        prompt = f"""Извлеки все стабильные факты из следующего текста в формате JSON-массива.
Каждый факт — объект с полями "subject", "predicate", "object".
Если фактов нет, верни [].
Текст: {text}
Ответ только JSON:"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=500
            )
            content = response.choices[0].message.content.strip()
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            return []
        except Exception as e:
            print(f"Ошибка извлечения фактов: {e}")
            return []

    def _extract_and_save_facts_async(self, user_input, monika_reply):
        user_facts = self.extract_facts_via_lmstudio(user_input)
        for fact in user_facts:
            if isinstance(fact, dict) and 'subject' in fact and 'predicate' in fact:
                subj = fact['subject']
                pred = fact['predicate']
                obj = fact.get('object', 'СЌС‚Рѕ')
                normalized = self.builder.normalize_fact_triplet(subj, pred, obj, source="user")
                if normalized and self.builder.is_stable_fact(*normalized, source="user"):
                    fact_text = " ".join(normalized)
                    self.builder.add_fact(fact_text)
                    print(f"[Memory] user fact: {fact_text}")

        return
        monika_facts = self.extract_facts_via_lmstudio(monika_reply)
        for fact in monika_facts:
            if isinstance(fact, dict) and 'subject' in fact and 'predicate' in fact:
                subj = fact['subject']
                pred = fact['predicate']
                obj = fact.get('object', 'СЌС‚Рѕ')
                normalized = self.builder.normalize_fact_triplet(subj, pred, obj, source="monika")
                if normalized and self.builder.is_stable_fact(*normalized, source="monika"):
                    fact_text = " ".join(normalized)
                    self.builder.add_fact(fact_text)
                    print(f"[Memory] monika fact: {fact_text}")

    @timeit(name="process_input_полный")
    def process_input(self, stimulus: Stimulus):
        self.message_counter += 1
        user_input = repair_mojibake(str(stimulus.content or ""))
        stimulus.content = user_input
        if not user_input.strip():
            return
        try:
            self.repetition_guard.update_session_from_user(self.repetition_session, user_input)
        except Exception as exc:
            runtime_log(f"REPETITION_GUARD_USER_ERROR | {exc}")
        relationship_role = self._resolve_relationship_role(stimulus)
        social_person_id, social_display_name = self._resolve_social_identity(stimulus)
        handled_mode_command = self._handle_private_mode_command(user_input, relationship_role)
        if handled_mode_command:
            return
        source = getattr(stimulus, "source", "text_input") or "text_input"
        boundary_decision = self.boundary_consent.classify(
            user_input,
            role=relationship_role,
            private_adult_mode=bool(getattr(self, "private_adult_mode", False)),
            source="text_input" if relationship_role == "creator" else str(source),
        )
        if relationship_role == "creator" and boundary_decision.allowed and self._should_treat_as_private_adult_turn(user_input, boundary_decision):
            boundary_decision.risk = "private_adult"
            boundary_decision.mode = "private_adult"
            boundary_decision.memory_allowed = False
            boundary_decision.public_tts_allowed = False
            if "Private creator-only mode is active." not in boundary_decision.constraints:
                boundary_decision.constraints.extend([
                    "Private creator-only mode is active.",
                    "Stay in the current private scene; do not jump to old stories, pizza, Barс/Барс, Cyberpunk or Elden Ring.",
                    "Keep Monika's agency and character while continuing the current scene.",
                    "Do not write this scene to long-term memory.",
                ])
            self.scene_state["private_adult_mode"] = True
            self.scene_state["private_scene_active"] = True
            self.scene_state["boundary_mode"] = "private_adult"
            self.scene_state["suppressed_topics"] = ["пицца", "барс", "кот барс", "киберпанк", "elden ring"]
        if relationship_role == "creator" and bool(getattr(self, "private_adult_mode", False)) and boundary_decision.allowed and getattr(boundary_decision, "risk", "ok") != "private_adult":
            self.scene_state["private_scene_active"] = False
            self.scene_state["boundary_mode"] = getattr(boundary_decision, "mode", "twitch_safe")
        self._current_boundary_mode = getattr(boundary_decision, "mode", "twitch_safe")
        self._current_boundary_memory_allowed = bool(boundary_decision.memory_allowed)
        self._current_boundary_tts_allowed = getattr(boundary_decision, "risk", "ok") != "private_adult"
        if boundary_decision.constraints:
            self.current_boundary_context = "[BOUNDARY CONSENT]\n" + "\n".join(f"- {item}" for item in boundary_decision.constraints)
        else:
            self.current_boundary_context = ""
        runtime_log_dict("BOUNDARY_CONSENT", boundary_decision.to_dict())
        if not boundary_decision.allowed:
            reply = self._controlled_reply(
                boundary_decision.safe_text,
                intent="живой отказ на нарушение границ или Twitch-safe режима",
                constraints=list(boundary_decision.constraints) + [
                    "Не повторяй исходную 18+ или рискованную формулировку.",
                    "Не продолжай сцену и не эротизируй отказ.",
                    "Можно быть резкой, ехидной и живой, но безопасной.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
                max_tokens=140,
            )
            self._clear_scene_latches()
            print(f"\nМоника: {reply}")
            runtime_log(f"OUTPUT | Моника: {reply}")
            self.speak(reply)
            return
        if boundary_decision.risk == "private_adult" and user_input.lower().replace("ё", "е").startswith("запомни"):
            reply = self._controlled_reply(
                "[creator пытается сохранить приватный 18+ материал]",
                intent="объяснить, что приватный 18+ режим не пишется в память",
                constraints=list(boundary_decision.constraints) + [
                    "Не повторяй 18+ детали.",
                    "Скажи, что это останется только в текущей приватной сцене.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
                max_tokens=120,
            )
            print(f"\nМоника: {reply}")
            runtime_log(f"OUTPUT | Моника: {reply}")
            return

        if relationship_role == "creator" and self._is_emotion_debug_question(user_input):
            reply = self._compose_emotion_debug_reply()
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": reply})
            self._remember_scene_turn(
                user_input,
                reply,
                relationship_role,
                social_intent="debug_status",
                person_id=social_person_id,
            )
            print(f"\nМоника: {reply}")
            runtime_log(f"OUTPUT | Моника: {reply}")
            self.speak(reply)
            return

        if self._is_hard_interrupt_input(user_input):
            self._clear_scene_latches()
            reply = self._controlled_reply(
                user_input,
                intent="коротко принять команду остановки и сбросить текущую сцену",
                constraints=[
                    "Не продолжай прошлую сцену, прошлую тему или старую шутку.",
                    "Ответь как Моника: живо, но очень коротко.",
                    "Подтверди, что остановилась и ждёшь новый фокус.",
                ],
                relationship_role=relationship_role,
                max_sentences=1,
                max_tokens=90,
            )
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": reply})
            self._remember_scene_turn(
                user_input,
                reply,
                relationship_role,
                social_intent="interrupt",
                person_id=social_person_id,
            )
            print(f"\nМоника: {reply}")
            runtime_log(f"OUTPUT | Моника: {reply}")
            self.speak(reply)
            return
        
        self.builder.update_user_reputation(STREAMER_ID, "Дункан", is_creator=True)
        
        violation_type, violation_detail = (None, None)
        if getattr(boundary_decision, "risk", "ok") != "private_adult":
            violation_type, violation_detail = detect_forbidden_content(user_input)
        if violation_type == "hate":
            print(f"[HateDetector] Обнаружен хейт: {violation_detail}")
            state = self.social_layer.update_interaction(
                social_person_id, social_display_name, relationship_role, user_input,
                sentiment=-0.6, event_type="insult", violation_type="hate"
            )
            action = self.social_layer.moderation_action(social_person_id)
            state = self.social_layer.register_moderation(social_person_id, action)
            reply = self._compose_moderation_reply(user_input, "hate", violation_detail, relationship_role, state, action)
            self._remember_scene_turn(user_input, reply, relationship_role, social_intent="playful_banter")
            print(f"\nМоника: {reply}")
            runtime_log(f"OUTPUT | Моника: {reply}")
            self.speak(reply)
            return
        elif violation_type == "forbidden":
            print(f"[Forbidden] Запрещённая тема: {violation_detail}")
            state = self.social_layer.update_interaction(
                social_person_id, social_display_name, relationship_role, user_input,
                sentiment=-0.2, event_type="neutral", violation_type="forbidden"
            )
            action = self.social_layer.moderation_action(social_person_id)
            state = self.social_layer.register_moderation(social_person_id, action)
            reply = self._compose_moderation_reply(user_input, "forbidden", violation_detail, relationship_role, state, action)
            self._remember_scene_turn(user_input, reply, relationship_role, social_intent="short_react")
            print(f"\nМоника: {reply}")
            runtime_log(f"OUTPUT | Моника: {reply}")
            self.speak(reply)
            return
        
        if getattr(self, "_current_boundary_memory_allowed", True):
            self._analyze_and_learn(user_input)
            self.opinion_memory.observe_user_message(user_input, source=f"{relationship_role}_input")
        else:
            runtime_log("MEMORY_SUPPRESSED | boundary_consent | prelearn")

        social_state_now = self._get_social_state(social_person_id)
        # Прощение: создатель может попросить прощения за себя или другого
        input_lower_check = user_input.lower().replace("ё", "е")
        if "прости" in input_lower_check or "прощение" in input_lower_check or "извини" in input_lower_check:
            if "пользовател" in input_lower_check or "зрител" in input_lower_check:
                # Простить другого пользователя (только creator)
                if relationship_role == "creator":
                    match = re.search(r"(?:пользовател[ья]|зрител[ья])\s+(\w+)", input_lower_check)
                    if match:
                        target_user = match.group(1)
                        self.social_layer.forgive(target_user)
                        reply = f"Ладно, {target_user} прощён. Но пусть больше так не делает."
                        self.builder.log_message("user", user_input)
                        self.history.append({"role": "user", "content": user_input})
                        self.history.append({"role": "assistant", "content": reply})
                        self._remember_scene_turn(user_input, reply, relationship_role, social_intent="soft_serious")
                        print(f"\nМоника: {reply}")
                        self.speak(reply)
                        return
            else:
                # Простить текущего пользователя
                self.social_layer.forgive(social_person_id)
                reply = "Прощаю. Давай дальше без этого."
                if relationship_role == "creator":
                    reply = "Ты прощён. Забудем этот цирк и пойдём дальше."
                self.builder.log_message("user", user_input)
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": reply})
                self._remember_scene_turn(user_input, reply, relationship_role, social_intent="soft_serious")
                print(f"\nМоника: {reply}")
                self.speak(reply)
                return
        hard_repair_reply = self._hard_memory_correction_reply(user_input)
        if hard_repair_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": hard_repair_reply})
            self._remember_scene_turn(user_input, hard_repair_reply, relationship_role, social_intent="complaint")
            print("\nМоника: " + hard_repair_reply)
            runtime_log("OUTPUT | Моника: " + hard_repair_reply)
            self.signals.last_ai_response = hard_repair_reply
            self.last_monika_message = hard_repair_reply
            self.builder.log_message("assistant", hard_repair_reply)
            self.speak(hard_repair_reply)
            return

        repair_reply = self._compose_repair_reply(user_input, relationship_role, social_state_now)
        if repair_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": repair_reply})
            self._remember_scene_turn(user_input, repair_reply, relationship_role, social_intent="complaint")
            print(f"\nМоника: {repair_reply}")
            runtime_log(f"OUTPUT | Моника: {repair_reply}")
            self.signals.last_ai_response = repair_reply
            self.last_monika_message = repair_reply
            self.opinion_memory.observe_monika_reply(repair_reply, source="repair_reply")
            self.builder.log_message("assistant", repair_reply)
            self.speak(repair_reply)
            return

        lyrics_reply = self._answer_lyrics_request(user_input)
        if lyrics_reply:
            self.builder.log_message("user", user_input)
            runtime_log_dict("PROMPT_CONTEXT", {
                "special_handler": "lyrics_request",
                "user_input": user_input,
            })
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": lyrics_reply})
            self._remember_scene_turn(user_input, lyrics_reply, relationship_role, social_intent="short_react")
            print(f"\nМоника: {lyrics_reply}")
            runtime_log(f"OUTPUT | Моника: {lyrics_reply}")
            self.signals.last_ai_response = lyrics_reply
            self.last_monika_message = lyrics_reply
            self.opinion_memory.observe_monika_reply(lyrics_reply, source="lyrics_reply")
            self.builder.log_message("assistant", lyrics_reply)
            self.speak(lyrics_reply)
            return

        user_self_reply = self._answer_user_self_correction(user_input, relationship_role)
        if user_self_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": user_self_reply})
            self._remember_scene_turn(user_input, user_self_reply, relationship_role, social_intent="open_answer")
            print(f"\nМоника: {user_self_reply}")
            runtime_log(f"OUTPUT | Моника: {user_self_reply}")
            self.signals.last_ai_response = user_self_reply
            self.last_monika_message = user_self_reply
            self.opinion_memory.observe_monika_reply(user_self_reply, source="user_self_reply")
            self.builder.log_message("assistant", user_self_reply)
            self.speak(user_self_reply)
            return

        experience_reply = self._answer_experience_boundary(user_input)
        if experience_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": experience_reply})
            self._remember_scene_turn(user_input, experience_reply, relationship_role, social_intent="open_answer")
            print(f"\nМоника: {experience_reply}")
            runtime_log(f"OUTPUT | Моника: {experience_reply}")
            runtime_log_dict("EXPERIENCE_BOUNDARY", {"user_input": user_input, "reply": experience_reply})
            self.signals.last_ai_response = experience_reply
            self.last_monika_message = experience_reply
            self.opinion_memory.observe_monika_reply(experience_reply, source="experience_boundary")
            self.builder.log_message("assistant", experience_reply)
            self.speak(experience_reply)
            return

        identity_reply = self._answer_identity_query(user_input)
        if identity_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": identity_reply})
            self._remember_scene_turn(user_input, identity_reply, relationship_role, social_intent="open_answer")
            print(f"\nМоника: {identity_reply}")
            runtime_log(f"OUTPUT | Моника: {identity_reply}")
            self.signals.last_ai_response = identity_reply
            self.last_monika_message = identity_reply
            self.opinion_memory.observe_monika_reply(identity_reply, source="identity_reply")
            self.builder.log_message("assistant", identity_reply)
            self.speak(identity_reply)
            return

        user_profile_reply = self._answer_user_profile_query(user_input)
        if user_profile_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": user_profile_reply})
            self._remember_scene_turn(user_input, user_profile_reply, relationship_role, social_intent="open_answer")
            print(f"\nМоника: {user_profile_reply}")
            runtime_log(f"OUTPUT | Моника: {user_profile_reply}")
            self.signals.last_ai_response = user_profile_reply
            self.last_monika_message = user_profile_reply
            self.opinion_memory.observe_monika_reply(user_profile_reply, source="user_profile_reply")
            self.builder.log_message("assistant", user_profile_reply)
            self.speak(user_profile_reply)
            return

        existential_reply = self._answer_existential_query(user_input)
        if existential_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": existential_reply})
            self._remember_scene_turn(user_input, existential_reply, relationship_role, social_intent="open_answer")
            print(f"\nМоника: {existential_reply}")
            runtime_log(f"OUTPUT | Моника: {existential_reply}")
            self.signals.last_ai_response = existential_reply
            self.last_monika_message = existential_reply
            self.builder.log_message("assistant", existential_reply)
            self.speak(existential_reply)
            return

        focus_reply = self._compose_focus_reply(user_input, relationship_role, social_state_now)
        if focus_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": focus_reply})
            self._remember_scene_turn(user_input, focus_reply, relationship_role, social_intent="short_react")
            print(f"\nМоника: {focus_reply}")
            runtime_log(f"OUTPUT | Моника: {focus_reply}")
            self.signals.last_ai_response = focus_reply
            self.last_monika_message = focus_reply
            self.opinion_memory.observe_monika_reply(focus_reply, source="focus_reply")
            self.builder.log_message("assistant", focus_reply)
            self.speak(focus_reply)
            return

        praise_reply = self._compose_praise_reply(user_input, relationship_role, social_state_now)
        if praise_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": praise_reply})
            self._remember_scene_turn(user_input, praise_reply, relationship_role, social_intent="needs_praise")
            print(f"\nМоника: {praise_reply}")
            runtime_log(f"OUTPUT | Моника: {praise_reply}")
            self.signals.last_ai_response = praise_reply
            self.last_monika_message = praise_reply
            self.opinion_memory.observe_monika_reply(praise_reply, source="praise_reply")
            self.builder.log_message("assistant", praise_reply)
            self.speak(praise_reply)
            return

        support_reply = self._compose_support_reply(user_input, social_state_now)
        if support_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": support_reply})
            self._remember_scene_turn(user_input, support_reply, relationship_role, social_intent="needs_support")
            print(f"\nМоника: {support_reply}")
            runtime_log(f"OUTPUT | Моника: {support_reply}")
            self.signals.last_ai_response = support_reply
            self.last_monika_message = support_reply
            self.opinion_memory.observe_monika_reply(support_reply, source="support_reply")
            self.builder.log_message("assistant", support_reply)
            self.speak(support_reply)
            return

        game_choice_reply, game_choice_repeat_count = self._answer_game_choice_request(user_input, relationship_role)
        if game_choice_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": game_choice_reply})
            self._remember_scene_turn(user_input, game_choice_reply, relationship_role, social_intent="complaint" if game_choice_repeat_count >= 3 else "open_answer")
            print(f"\nМоника: {game_choice_reply}")
            runtime_log(f"OUTPUT | Моника: {game_choice_reply}")
            self.signals.last_ai_response = game_choice_reply
            self.last_monika_message = game_choice_reply
            self.opinion_memory.observe_monika_reply(game_choice_reply, source="game_choice_reply")
            self.builder.log_message("assistant", game_choice_reply)
            self.speak(game_choice_reply)
            return

        semantic_reply = self._answer_semantic_query(user_input)
        if semantic_reply:
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": semantic_reply})
            self._remember_scene_turn(user_input, semantic_reply, relationship_role, social_intent="open_answer")
            print(f"\nМоника: {semantic_reply}")
            runtime_log(f"OUTPUT | Моника: {semantic_reply}")
            self.signals.last_ai_response = semantic_reply
            self.last_monika_message = semantic_reply
            self.opinion_memory.observe_monika_reply(semantic_reply, source="semantic_reply")
            self.builder.log_message("assistant", semantic_reply)
            self.speak(semantic_reply)
            return
        
        # РћР±РЅРѕРІР»СЏРµРј Persona: СЂРµР¶РёРј Рё РјРёРєСЂРѕ-РёРјРїСѓР»СЊСЃ
        input_lower = user_input.lower().replace("ё", "е")
        contains_memory = self._looks_like_memory_request(user_input)
        pre_relationship_state = self.social_layer.get_state(social_person_id)
        routing_text = self._context_text_for_routing(user_input)
        pre_active_desires = self.desire_memory.get_relevant_desires(text=routing_text, limit=3)
        pre_active_opinions = self.opinion_memory.get_relevant_opinions(text=routing_text, limit=3)
        self.scene_state["user_energy"] = self.behavior_director._detect_energy(routing_text.lower())
        self.scene_state["focus_target"] = self.behavior_director._detect_focus_target(routing_text.lower(), relationship_role)
        if self.behavior_director._is_topic_rejection(user_input.lower()) and self.scene_state.get("topic"):
            self.scene_state.setdefault("rejected_topics", {})[self.scene_state["topic"]] = 5
        planning_scene_state = dict(self.scene_state)
        planning_signature = self.behavior_director._normalize_signature(user_input)
        previous_signature = planning_scene_state.get("last_user_signature", "")
        planning_scene_state["repeat_user_count"] = (
            int(planning_scene_state.get("repeat_user_count", 0) or 0) + 1
            if planning_signature and planning_signature == previous_signature
            else (1 if planning_signature else 0)
        )
        previous_reply_for_scene = planning_scene_state.get("last_assistant_reply", "") or self.last_monika_message or ""
        explicit_new_question = any(token in input_lower for token in ["?", "почему", "зачем", "как", "кто", "что", "какую", "какой", "какая"])
        contextual_followup = any(token in input_lower for token in [
            "а ты", "а тебе", "а ее", "а её", "а это", "и что", "ну ", "нуу", "да ", "нет ", "еще", "ещё"
        ])
        direct_question_without_context = explicit_new_question and not contextual_followup
        if direct_question_without_context and self._token_overlap_score(user_input, previous_reply_for_scene) < 0.18:
            planning_scene_state["topic"] = None
            planning_scene_state["ongoing_bit"] = None
            planning_scene_state["bit_turns"] = 0
            planning_scene_state["continuity_anchor"] = None
            planning_scene_state["continuity_turns"] = 0
            try:
                self.live_engine.anticipation.expected_topics.clear()
            except Exception:
                pass
        new_topic = self.behavior_director._detect_topic(routing_text.lower())
        old_topic = planning_scene_state.get("topic")
        topic_change_marker = None
        if direct_question_without_context and not new_topic:
            if old_topic:
                topic_change_marker = f"Пользователь задал новый прямой вопрос. Не продолжай старую тему «{old_topic}»."
            planning_scene_state["topic"] = None
            planning_scene_state["ongoing_bit"] = None
            planning_scene_state["bit_turns"] = 0
            planning_scene_state["continuity_anchor"] = None
            planning_scene_state["continuity_turns"] = 0
            old_topic = None
        if new_topic and old_topic and new_topic != old_topic:
            topic_change_marker = f"Тема разговора сменилась с «{old_topic}» на «{new_topic}». Не возвращайся к старой теме."
            planning_scene_state["topic"] = new_topic
            planning_scene_state["ongoing_bit"] = None
            planning_scene_state["bit_turns"] = 0
            planning_scene_state["continuity_anchor"] = None
            planning_scene_state["continuity_turns"] = 0
        if new_topic and new_topic in planning_scene_state.get("rejected_topics", {}) and not self.behavior_director._is_topic_rejection(input_lower):
            planning_scene_state.get("rejected_topics", {}).pop(new_topic, None)
        stream_mode = relationship_role in {"viewer", "scene"} or (stimulus.source or "").lower() in {
            "chat", "donation", "screen", "proactive", "association"
        }
        preliminary_intent = self.behavior_director.detect_social_intent(routing_text.lower(), stream_mode=stream_mode)
        try:
            self.self_state.observe_user_message(
                user_input,
                relationship_role=relationship_role,
                relationship_state=pre_relationship_state,
            )
        except Exception as e:
            runtime_log(f"SELF_STATE_OBSERVE_ERROR | {e}")
        live_decision = self.live_engine.before_plan(
            person_id=social_person_id,
            role=relationship_role,
            user_message=user_input,
            scene_state=planning_scene_state,
            relationship_state=pre_relationship_state,
            topic=new_topic or planning_scene_state.get("topic"),
            social_intent=preliminary_intent,
            stream_mode=stream_mode,
        )
        pre_active_desires = self._filter_desires_for_live_context(
            pre_active_desires,
            routing_text,
            live_decision,
            planning_scene_state,
        )
        allow_background = self._should_allow_background_personality(user_input, preliminary_intent, new_topic)
        if not allow_background:
            pre_active_desires = [item for item in pre_active_desires if str(item.get("target", "")).lower().replace("ё", "е") in input_lower]
            pre_active_opinions = []
        if live_decision.get("suppress_topic"):
            planning_scene_state.setdefault("rejected_topics", {})[live_decision["suppress_topic"]] = 3
        behavior_plan = self.behavior_director.plan_response(
            user_input,
            contains_memory_question=contains_memory,
            stream_mode=stream_mode,
            relationship_role=relationship_role,
            scene_state=planning_scene_state,
            relationship_state=pre_relationship_state,
            active_desires=pre_active_desires,
            active_opinions=pre_active_opinions,
        )
        self.current_mode = behavior_plan.mode
        self.current_micro_desire = behavior_plan.micro_desire
        self.current_behavior_notes = self.behavior_director.format_system_notes(behavior_plan)
        self.current_social_context = self.social_layer.build_prompt_block(social_person_id, relationship_role)
        try:
            self.current_self_context = self.self_state.build_prompt_block(
                user_input,
                relationship_role=relationship_role,
                relationship_state=pre_relationship_state,
                scene_state=planning_scene_state,
                recent_history=self.history,
            )
            runtime_log_dict("SELF_STATE", self.self_state.snapshot())
        except Exception as e:
            self.current_self_context = ""
            runtime_log(f"SELF_STATE_BUILD_ERROR | {e}")
        # STAGE_DIRECTOR_V2_APPLIED
        try:
            _opinion_request = any(_tok in (user_input or "").lower().replace("ё", "е") for _tok in [
                "нравится", "что думаешь", "как тебе", "мнение", "как относишься", "любишь", "ненавидишь"
            ])
            _stage_decision = self.stage_director.classify(
                user_input,
                relationship_role=relationship_role,
                social_intent=behavior_plan.social_intent,
                contains_memory=contains_memory,
                opinion_request=_opinion_request,
                relationship_state=pre_relationship_state,
                scene_state=planning_scene_state,
                social_memory=getattr(self, "current_social_memory_info", {}),
            )
            self.stage_director.apply_to_plan(behavior_plan, _stage_decision)
            self.current_stage_context = self.stage_director.build_prompt_block_from_info(_stage_decision)
            self.current_stage_decision = _stage_decision
            if _stage_decision.stage in {"STORY", "STORY_SETUP", "STORY_CONTINUE"}:
                planning_scene_state["story_focus"] = "active"
                planning_scene_state["continuity_anchor"] = "story"
                planning_scene_state["continuity_turns"] = max(int(planning_scene_state.get("continuity_turns", 0) or 0), 5)
                planning_scene_state["ongoing_bit"] = "story"
                planning_scene_state["bit_turns"] = max(int(planning_scene_state.get("bit_turns", 0) or 0), 1)
            elif _stage_decision.stage == "INTERRUPT":
                planning_scene_state["story_focus"] = None
                planning_scene_state["continuity_anchor"] = None
                planning_scene_state["continuity_turns"] = 0
                planning_scene_state["ongoing_bit"] = None
                planning_scene_state["bit_turns"] = 0
            runtime_log_dict("STAGE_DIRECTOR", _stage_decision.as_dict())
        except Exception as e:
            self.current_stage_context = ""
            self.current_stage_decision = None
            runtime_log(f"STAGE_DIRECTOR_ERROR | {e}")
        emotion_decision = None
        try:
            emotion_decision = self.emotion_director.decide(
                user_input,
                stage_decision=getattr(self, "current_stage_decision", None),
                behavior_plan=behavior_plan,
                relationship_state=pre_relationship_state,
                scene_state=planning_scene_state,
                stream_mode=stream_mode,
            )
            self.emotion_director.apply_to_plan(behavior_plan, emotion_decision)
            planning_scene_state = self.emotion_director.update_arc(planning_scene_state, emotion_decision, user_input)
            self.scene_state = planning_scene_state
            self.current_emotion_context = self.emotion_director.build_prompt_block(emotion_decision)
            self.current_emotion_decision = emotion_decision.to_dict()
            if emotion_decision.suppress_background_layers:
                allow_background = False
                pre_active_desires = []
                pre_active_opinions = []
            runtime_log_dict("EMOTION_DIRECTOR", emotion_decision.to_dict())
        except Exception as e:
            self.current_emotion_context = ""
            self.current_emotion_decision = {}
            runtime_log(f"EMOTION_DIRECTOR_ERROR | {e}")
        try:
            unified_emotion = self.emotional_state_aggregator.build(
                user_input=user_input,
                emotion_decision=emotion_decision,
                behavior_plan=behavior_plan,
                stage_decision=getattr(self, "current_stage_decision", None),
                relationship_state=pre_relationship_state,
                affection_state=self.affection_state,
                live_decision=live_decision,
                scene_state=planning_scene_state,
                stream_mode=stream_mode,
            )
            self.emotional_state_aggregator.apply_to_plan(behavior_plan, unified_emotion)
            planning_scene_state = self.emotional_state_aggregator.update_scene_state(
                planning_scene_state,
                unified_emotion,
                user_input=user_input,
            )
            self.scene_state = planning_scene_state
            self.current_unified_emotion = unified_emotion.to_dict()
            self.current_unified_emotion_context = self.emotional_state_aggregator.build_prompt_block(unified_emotion)
            if unified_emotion.suppress_background_layers:
                allow_background = False
                pre_active_desires = []
                pre_active_opinions = []
            runtime_log_dict("UNIFIED_EMOTION", unified_emotion.to_dict())
        except Exception as e:
            self.current_unified_emotion = {}
            self.current_unified_emotion_context = ""
            runtime_log(f"UNIFIED_EMOTION_ERROR | {e}")
        self.current_desire_context = self._render_desire_prompt_block(pre_active_desires)
        self.current_opinion_context = self.opinion_memory.build_prompt_block(text=routing_text, limit=3, rejected_topics=(planning_scene_state or {}).get("rejected_topics")) if allow_background else ""
        self.current_live_context = self.live_engine.build_prompt_block(social_person_id)
        try:
            self.current_self_context = self.self_state.build_prompt_block(
                user_input,
                relationship_role=relationship_role,
                relationship_state=pre_relationship_state,
                scene_state=planning_scene_state,
                recent_history=[m for m in self.history[-10:] if isinstance(m, dict)],
            )
        except Exception as e:
            runtime_log(f"SELF_STATE_CONTEXT_ERROR | {e}")
            self.current_self_context = ""
        try:
            self.current_session_context = self.session_mind.build_prompt_block(user_input)
        except Exception as e:
            runtime_log(f"SESSION_MIND_CONTEXT_ERROR | {e}")
            self.current_session_context = ""
        try:
            self.current_opinion_core_context = self.opinion_core.build_prompt_block(user_input)
        except Exception as e:
            runtime_log(f"OPINION_CORE_CONTEXT_ERROR | {e}")
            self.current_opinion_core_context = ""
        try:
            if not getattr(self, "current_stage_context", ""):
                self.current_stage_context = self.stage_director.build_prompt_block(
                    user_input,
                    relationship_role=relationship_role,
                    social_intent=preliminary_intent,
                    contains_memory=contains_memory,
                    opinion_request=self.opinion_core.is_opinion_request(user_input),
                )
        except Exception as e:
            runtime_log(f"STAGE_DIRECTOR_CONTEXT_ERROR | {e}")
            self.current_stage_context = ""
        if live_decision.get("return_hook"):
            self.current_live_context += f"\n- Реплика возвращения, если уместно: {live_decision['return_hook']}"
        runtime_log_dict("LIVE_ENGINE", {
            "decision": live_decision,
            "snapshot": self.live_engine.snapshot(),
            "filtered_desires": pre_active_desires,
        })
        runtime_log_dict("INTERPRETATION", {
            "user_input": user_input,
            "relationship_role": relationship_role,
            "social_person_id": social_person_id,
            "stream_mode": stream_mode,
            "contains_memory": contains_memory,
            "mode": getattr(behavior_plan.mode, "value", str(behavior_plan.mode)),
            "social_intent": behavior_plan.social_intent,
            "scene_mood": behavior_plan.scene_mood,
            "scene_turns_left": behavior_plan.scene_turns_left,
        })
        runtime_log_dict("STATE", {
            "scene_state": self.scene_state,
            "relationship_state": pre_relationship_state,
            "active_desires": pre_active_desires,
            "active_opinions": pre_active_opinions,
            "affection": {
                "mood": self.affection_state.mood,
                "value": round(float(self.affection_state.value), 3),
                "trust": round(float(self.affection_state.trust), 3),
                "familiarity": round(float(self.affection_state.familiarity), 3),
                "intensity": round(float(self.affection_state.intensity), 3),
            },
        })
        runtime_log_dict("PLAN", {
            "micro_desire": behavior_plan.micro_desire,
            "max_sentences": behavior_plan.max_sentences,
            "max_tokens": behavior_plan.max_tokens,
            "use_memory": behavior_plan.use_memory,
            "require_reaction_opening": behavior_plan.require_reaction_opening,
            "allow_tease": behavior_plan.allow_tease,
            "require_softness": behavior_plan.require_softness,
            "allow_followup_question": behavior_plan.allow_followup_question,
            "initiative_allowed": behavior_plan.initiative_allowed,
            "initiative_style": behavior_plan.initiative_style,
            "relationship_hint": behavior_plan.relationship_hint,
            "active_desire_lines": behavior_plan.active_desire_lines,
            "behavior_flags": behavior_plan.behavior_flags,
        })
        # # YUNA_RECALL_CONTEXT_BUILD_V1
        try:
            if hasattr(self, "yuna_bridge") and self.yuna_bridge is not None and "user_input" in locals():
                _yd = locals().get("stage_decision", None)
                _ys = ""
                if isinstance(_yd, dict):
                    _ys = str(_yd.get("stage") or _yd.get("stage_mode") or "")
                elif _yd is not None:
                    _ys = str(getattr(_yd, "stage", "") or getattr(_yd, "stage_mode", "") or "")
                if not _ys and "behavior_plan" in locals():
                    _ys = str(getattr(locals().get("behavior_plan"), "stage", "") or getattr(locals().get("behavior_plan"), "mode", "") or "")
                self.current_yuna_context = self.yuna_bridge.build_prompt_block(
                    user_input=locals().get("user_input", ""),
                    stage_mode=_ys,
                    person_id=locals().get("social_person_id", "Duncan"),
                    recent_history=getattr(self, "history", []),
                )
                runtime_log_dict("YUNA_CONTEXT", {"present": bool(self.current_yuna_context), "stage_mode": _ys})
        except Exception as e:
            self.current_yuna_context = ""
            runtime_log(f"YUNA_CONTEXT_ERROR | {e}")
        self._update_system_prompt()
        
        # Принудительный controlled_reply при повторах ≥ 3
        if behavior_plan.force_break_loop:
            break_reply = self._controlled_reply(
                user_input,
                intent="прервать цикл повторов",
                constraints=[
                    "Пользователь повторяет одно и то же. Не отвечай как в прошлый раз.",
                    "Покажи лёгкое раздражение или усмешку.",
                    "Не продолжай предыдущую тему.",
                    "Если это вопрос о личности — дай короткий ответ и смени интонацию.",
                ],
                relationship_role=relationship_role,
                max_sentences=2,
            )
            self.builder.log_message("user", user_input)
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": break_reply})
            self._remember_scene_turn(user_input, break_reply, relationship_role, social_intent="complaint")
            print(f"\nМоника: {break_reply}")
            runtime_log(f"OUTPUT | Моника: {break_reply}")
            self.signals.last_ai_response = break_reply
            self.last_monika_message = break_reply
            self.builder.log_message("assistant", break_reply)
            self.speak(break_reply)
            return
        
        # Monika loop detector: 3+ ответа подряд с одинаковой сигнатурой
        recent_monika = self._get_recent_assistant_messages(limit=3)
        if len(recent_monika) >= 3:
            sigs = [self.behavior_director._normalize_signature(r)[:60] for r in recent_monika]
            if len(set(sigs)) == 1 and sigs[0]:
                rejected = list((planning_scene_state or {}).get("rejected_topics", {}).keys())
                break_reply = self._controlled_reply(
                    user_input,
                    intent="разорвать залипшую тему",
                    constraints=[
                        "Не продолжай предыдущую линию разговора.",
                        "Не упоминай повторы, не считай вслух сколько раз спросили.",
                        "Ответь именно на текущий вопрос пользователя по сути.",
                        "Будь живой и естественной.",
                        "Предложи свою тему для разговора — что тебе сейчас интересно обсудить.",
                    ] + ([f"Не возвращайся к теме «{rejected[0]}», она надоела."] if rejected else []),
                    relationship_role=relationship_role,
                    max_sentences=2,
                )
                self.builder.log_message("user", user_input)
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": break_reply})
                self._remember_scene_turn(user_input, break_reply, relationship_role, social_intent="open_answer")
                print(f"\nМоника: {break_reply}")
                runtime_log(f"OUTPUT | Моника: {break_reply}")
                self.signals.last_ai_response = break_reply
                self.last_monika_message = break_reply
                self.builder.log_message("assistant", break_reply)
                self.speak(break_reply)
                return
        
        if user_input.lower().startswith("запомни"):
            fact_text = user_input[7:].strip()
            if fact_text:
                ok, stored_fact = self.builder.store_manual_fact(fact_text)
                if ok:
                    print(f"\nМоника: Запомнила: {stored_fact}")
                    runtime_log(f"OUTPUT | Моника: Запомнила: {stored_fact}")
                    self.speak(f"Запомнила: {stored_fact}")
                else:
                    print(f"\nМоника: {stored_fact}")
                    runtime_log(f"OUTPUT | Моника: {stored_fact}")
                    self.speak(stored_fact)
            else:
                print("\nМоника: А что запомнить?")
                runtime_log("OUTPUT | Моника: А что запомнить?")
            return
        
        rejection_keywords = ["забудь", "хватит", "прекрати", "не нужно", "отстань", "сколько можно"]
        if any(kw in user_input.lower() for kw in rejection_keywords):
            if hasattr(self, 'topic_learner') and self.last_monika_message:
                topics = self.topic_learner.extract_topics(self.last_monika_message)
                for topic in topics:
                    self.builder.update_topic_weight(topic, success=False, intensity=2.0)
                    print(f"[Emergency] Тема '{topic}' принудительно заблокирована создателем")
        
        if getattr(self, "_current_boundary_memory_allowed", True):
            self.builder.log_message("user", user_input)
            try:
                saved_user_facts = self.memory_core.observe_user_message(user_input, person_id=STREAMER_ID)
                if saved_user_facts:
                    runtime_log_dict("VERIFIED_MEMORY_SAVED", {"facts": saved_user_facts})
                    print(f"[VerifiedMemory] saved {len(saved_user_facts)} user fact(s)")
            except Exception as exc:
                runtime_log(f"VERIFIED_MEMORY_ERROR | {exc}")
        else:
            runtime_log("MEMORY_SUPPRESSED | boundary_consent | user_persistent_write")
        
        with timing_block(f"  [{self.message_counter}] process_input"):
            self.update_mood(user_input, is_user=True)
            
            # РћР±РЅРѕРІР»СЏРµРј Affection State
            sentiment = self.affection_state.get_sentiment_from_text(user_input)
            event_type = self.affection_state.detect_event_type(user_input)
            self.affection_state.update(sentiment, event_type)
            relationship_state = self.social_layer.update_interaction(
                social_person_id,
                social_display_name,
                relationship_role,
                user_input,
                sentiment=sentiment,
                event_type=event_type,
            )
            try:
                social_mem_event = self.social_memory.observe_interaction(
                    social_person_id,
                    social_display_name,
                    relationship_role,
                    user_input,
                    relationship_state=relationship_state,
                    sentiment=sentiment,
                    event_type=event_type,
                )
                self.current_social_memory_context = self.social_memory.build_prompt_block(
                    social_person_id,
                    social_display_name,
                    relationship_role,
                    relationship_state=relationship_state,
                )
                self.current_social_memory_info = social_mem_event
                runtime_log_dict("SOCIAL_MEMORY", social_mem_event)
            except Exception as exc:
                self.current_social_memory_context = ""
                self.current_social_memory_info = {}
                runtime_log(f"SOCIAL_MEMORY_ERROR | {exc}")
            self.desire_memory.observe_user_message(user_input, source=f"{relationship_role}_input")
            active_desires = self.desire_memory.get_active_desires(limit=3)
            match = re.search(r"вспомни (?:про )?(.+)", user_input, re.IGNORECASE)
            if match:
                query = match.group(1).strip().lower()
                
                if any(phrase in query for phrase in ["что я люблю", "что я обожаю", "что я ненавижу", "мои предпочтения"]):
                    user_facts = []
                    cursor = self.builder.graph.conn.cursor()
                    cursor.execute("SELECT id FROM entities WHERE name = 'Р”СѓРЅРєР°РЅ'")
                    user_row = cursor.fetchone()
                    if user_row:
                        user_id = user_row['id']
                        cursor.execute("""
                            SELECT e1.name as subj, f.predicate, e2.name as obj 
                            FROM facts f
                            JOIN entities e1 ON f.subject_id = e1.id
                            JOIN entities e2 ON f.object_id = e2.id
                            WHERE f.subject_id = ?
                        """, (user_id,))
                        for row in cursor.fetchall():
                            user_facts.append(f"{row['subj']} {row['predicate']} {row['obj']}")
                    
                    if user_facts:
                        prepared_user_facts = self.builder.prepare_facts_for_prompt(user_facts, max_facts=3)
                        prompt = self.builder.build_memory_prompt_block(
                            "Пользователь просит вспомнить, что ты знаешь о нём. Ответь тепло, естественно и без сухого списка.",
                            prepared_user_facts
                        )
                        messages = [
                            {"role": "system", "content": self.get_system_prompt()},
                            {"role": "user", "content": prompt}
                        ]
                        try:
                            response = self.client.chat.completions.create(
                                model=self.model,
                                messages=messages,
                                temperature=0.7,
                                max_tokens=behavior_plan.max_tokens
                            )
                            reply = repair_mojibake(response.choices[0].message.content.strip())
                            reply = clean_roleplay(reply)
                            reply = self._strip_runtime_leakage(reply)
                            reply = self.persona._normalize_response_text(reply)
                            reply = self.persona.apply_drift_guard(reply)
                        except Exception as e:
                            reply = f"Ошибка LLM: {e}"
                    else:
                        reply = "Пока у меня мало нормальных зацепок о твоих вкусах. Расскажи что-нибудь, и я запомню это без сухой канцелярщины."
                else:
                    facts = self.builder.retrieve(query, top_k=5)
                    if facts:
                        prepared_facts = self.builder.prepare_facts_for_prompt(facts, max_facts=3)
                        prompt = self.builder.build_memory_prompt_block(
                            f"Пользователь спрашивает: {query}",
                            prepared_facts
                        )
                        messages = [
                            {"role": "system", "content": self.get_system_prompt()},
                            {"role": "user", "content": prompt}
                        ]
                        try:
                            response = self.client.chat.completions.create(
                                model=self.model,
                                messages=messages,
                                temperature=0.7,
                                max_tokens=behavior_plan.max_tokens
                            )
                            reply = repair_mojibake(response.choices[0].message.content.strip())
                            reply = clean_roleplay(reply)
                            reply = self._strip_runtime_leakage(reply)
                            reply = self.persona._normalize_response_text(reply)
                            reply = self.persona.apply_drift_guard(reply)
                        except Exception as e:
                            reply = f"Ошибка LLM: {e}"
                    else:
                        reply = f"У меня сейчас нет уверенной памяти про {query}. Лучше не буду выдумывать."
                
                print(f"\nМоника: {reply}")
                runtime_log(f"OUTPUT | Моника: {reply}")
                self.signals.last_ai_response = reply
                self.speak(reply)
                return

            if user_input.startswith("!история"):
                history = self.builder.get_chat_history(10)
                if history:
                    lines = [f"{row[2]} [{row[0]}]: {row[1]}" for row in history]
                    reply = "\n".join(lines)
                else:
                    reply = "История пуста."
                print(f"\nМоника: {reply}")
                runtime_log(f"OUTPUT | Моника: {reply}")
                self.speak(reply)
                return

            if user_input.startswith("!темы"):
                stats = self.topic_learner.get_topic_stats()
                if stats:
                    lines = ["📊 Веса тем:"]
                    for topic, data in list(stats.items())[:10]:
                        cooldown = " [lock]" if data['cooldown_until'] else ""
                        lines.append(f"  {topic}: {data['weight']:.2f} (вњ…{data['success_count']} вќЊ{data['reject_count']}){cooldown}")
                    reply = "\n".join(lines)
                else:
                    reply = "Нет данных о темах."
                print(f"\nМоника: {reply}")
                runtime_log(f"OUTPUT | Моника: {reply}")
                self.speak(reply)
                return

            if user_input.startswith("!репутация"):
                stats = self.builder.get_user_stats(STREAMER_ID)
                if stats:
                    level = stats.get('authority_level', 0)
                    msgs = stats.get('total_messages', 0)
                    score = stats.get('reputation_score', 0)
                    reply = f"📊 Твоя статистика:\nСообщений: {msgs}\nРепутация: {score:.1f}\nУровень: {level} (СОЗДАТЕЛЬ)"
                else:
                    reply = "Нет данных."
                print(f"\nМоника: {reply}")
                runtime_log(f"OUTPUT | Моника: {reply}")
                self.speak(reply)
                return

            if user_input.startswith("!очистка"):
                self.builder.cleanup_low_importance_facts(threshold=0.01)
                print(f"\nМоника: Очистка завершена.")
                runtime_log("OUTPUT | Моника: Очистка завершена.")
                self.speak("Очистка завершена.")
                return

            if user_input.startswith("!вики"):
                query = user_input[5:].strip()
                reply = self.builder.get_wiki_info(query) if query else "Укажите запрос"
                print(f"\nМоника: {reply}")
                runtime_log(f"OUTPUT | Моника: {reply}")
                self.speak(reply)
                return

            if user_input.startswith("!консолидация"):
                threading.Thread(target=self._full_consolidate, daemon=True).start()
                reply = "Запустила консолидацию всей истории. Это займёт пару минут."
                print(f"\nМоника: {reply}")
                runtime_log(f"OUTPUT | Моника: {reply}")
                self.speak(reply)
                return


            inner_thought = None
            
            memory_context = ""
            stream_memories = []
            memory_recall = {"facts": [], "confidence": "none", "sources": [], "anchors": []}
            memory_lookup_query = self._memory_lookup_text(user_input) if contains_memory else user_input
            
            with timing_block(f"  [{self.message_counter}] VerifiedMemory_поиск"):
                if behavior_plan.use_memory or contains_memory:
                    try:
                        memory_recall = self.memory_core.recall(memory_lookup_query, limit=3, person_id=STREAMER_ID)
                    except Exception as exc:
                        runtime_log(f"VERIFIED_MEMORY_RECALL_ERROR | {exc}")
                        memory_recall = {"facts": [], "confidence": "low", "sources": [], "anchors": []}
                relevant_facts = list(memory_recall.get("facts") or [])
                relevant_facts = self.builder.prepare_facts_for_prompt(relevant_facts, max_facts=3)
                facts_text = "\n".join(relevant_facts) if relevant_facts else "Пока нет сохранённых фактов."
                if relevant_facts:
                    print(f"[VerifiedMemory] recall {len(relevant_facts)} fact(s), confidence={memory_recall.get('confidence')}")
# РЈСЃРёР»РµРЅРёРµ РїР°РјСЏС‚Рё
            if relevant_facts:
                entities = []
                for word in user_input.split():
                    clean_word = word.strip('.,!?;:')
                    if len(clean_word) >= 2:
                        entities.append(self.builder.graph.normalize_name(clean_word))
                try:
                    self.builder.graph.boost_facts_by_entities(entities, limit=5)
                except Exception as e:
                    pass
            runtime_log_dict("MEMORY", {
                "use_memory": behavior_plan.use_memory,
                "relevant_facts": relevant_facts,
                "stream_memory_present": bool(stream_memories),
                "memory_context_present": bool(memory_context.strip()),
            })
            memory_confidence = memory_recall.get("confidence") or self._estimate_memory_confidence(
                user_input=user_input,
                relevant_facts=relevant_facts,
                memory_context=memory_context,
                stream_memories=stream_memories,
            )
            self.scene_state["memory_confidence"] = memory_confidence
            runtime_log_dict("MEMORY_CONFIDENCE", {
                "user_input": user_input,
                "memory_confidence": memory_confidence,
            })



            exact_memory_reply = self._render_verified_memory_reply(user_input, relevant_facts, memory_confidence)
            if exact_memory_reply:
                monika_reply = exact_memory_reply
                runtime_log_dict("MEMORY_EXACT_REPLY", {
                    "user_input": user_input,
                    "relevant_facts": relevant_facts,
                    "reply": monika_reply,
                })
                self.history.append({"role": "assistant", "content": monika_reply})
                self._remember_scene_turn(
                    user_input,
                    monika_reply,
                    relationship_role,
                    social_intent=behavior_plan.social_intent,
                    person_id=social_person_id,
                )
                print(f"\nМоника: {monika_reply}")
                runtime_log(f"OUTPUT | Моника: {monika_reply}")
                self.speak(monika_reply)
                self.update_mood(monika_reply, is_user=False)
                self.last_monika_message = monika_reply
                self._cache_reply(monika_reply)
                self.builder.log_message("assistant", monika_reply)
            self._yuna_observe_turn_safe(
                user_input=locals().get("user_input", ""),
                monika_reply=locals().get("monika_reply", ""),
                person_id=locals().get("social_person_id", getattr(self, "user_id", "Duncan")),
                display_name=locals().get("social_display_name", str(locals().get("social_person_id", getattr(self, "user_id", "Duncan")))),
                stage_decision=locals().get("stage_decision", None),
            )
            affection_context = self.affection_state.to_context()
            social_context = self.social_layer.build_prompt_block(social_person_id, relationship_role)
            desire_context = self._render_desire_prompt_block(pre_active_desires)
            opinion_context = self.opinion_memory.build_prompt_block(text=routing_text, limit=3) if allow_background else ""
            live_context = self.live_engine.build_prompt_block(social_person_id)
            try:
                from stage_runtime_hardening import build_hard_scene_reset_block
                scene_reset_context = build_hard_scene_reset_block(
                    locals().get("stage_decision", getattr(self, "current_stage_decision", None)),
                    user_input,
                )
                if scene_reset_context:
                    live_context = (live_context + "\n" + scene_reset_context).strip()
            except Exception as exc:
                runtime_log(f"SCENE_RESET_CONTEXT_ERROR | {exc}")
            self_context = getattr(self, "current_self_context", "")
            session_context = getattr(self, "current_session_context", "")
            opinion_core_context = getattr(self, "current_opinion_core_context", "")
            stage_context = getattr(self, "current_stage_context", "")
            emotion_context = getattr(self, "current_emotion_context", "")
            unified_emotion_context = getattr(self, "current_unified_emotion_context", "")
            
            noise_context = ""
            if False and random.random() < 0.1:
                noise_context = "Можно не отвечать на всё сообщение полностью.\n"
            if False and random.random() < 0.15:
                noise_context += "Можно добавить небольшой комментарий в сторону.\n"
            if False and self.affection_state.mood == "irritated" and random.random() < 0.2:
                noise_context += "Реакция может быть чуть резче обычного.\n"
            
            initiative_lines = []
            if behavior_plan.initiative_allowed and behavior_plan.initiative_style:
                initiative_lines.append(behavior_plan.initiative_style)
            desire_hook = self.desire_memory.maybe_get_initiative_hook(text=routing_text) if allow_background else None
            if desire_hook:
                initiative_lines.append(desire_hook)
            opinion_hook = self.opinion_memory.maybe_get_opinion_hook(text=routing_text) if allow_background else None
            if opinion_hook:
                initiative_lines.append(opinion_hook)
            initiative_hint = ""
            if initiative_lines:
                initiative_hint = "\n\n[INITIATIVE WINDOW]\n- " + "\n- ".join(dict.fromkeys(initiative_lines))

            continuity_hint = ""
            recent_dialog = []
            for msg in reversed(self.history):
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                content = msg.get("content", "")
                if role in {"user", "assistant"} and content:
                    recent_dialog.append((role, content))
                if len(recent_dialog) >= 4:
                    break
            recent_dialog.reverse()

            short_follow_up = (
                len(user_input.strip()) <= 48
                or any(token in user_input.lower() for token in ["а ", "ну ", "и ", "это", "тоже", "ещё", "еще", "что?", "в смысле"])
            )
            source_name = (getattr(stimulus, "source", "") or "").lower()
            isolate_source = source_name in {"chat", "donation", "screen"}
            if short_follow_up and recent_dialog and not direct_question_without_context and not isolate_source:
                dialog_lines = []
                for role, content in recent_dialog[-4:]:
                    speaker = "Пользователь" if role == "user" else "Моника"
                    dialog_lines.append(f"{speaker}: {content}")
                continuity_hint = (
                    "\n\n[CONTINUITY]\n"
                    "Это короткое продолжение текущей сцены. Читай реплику через недавний контекст, а не как новую тему.\n"
                    + "\n".join(dialog_lines)
                )

            if relevant_facts:
                user_message_with_memory = self.builder.build_memory_prompt_block(user_input, relevant_facts)
            elif behavior_plan.use_memory:
                user_message_with_memory = (
                    f"{user_input}\n\n"
                    "[Если подходящей памяти нет, не выдумывай. "
                    "Ответь естественно и можешь мягко показать, что помнишь это неуверенно или пока не помнишь.]"
                )
            else:
                user_message_with_memory = user_input

            scene_constraints = self._source_isolation_constraints(stimulus)
            if self._recent_reply_cache:
                recent_lines = "\n".join(f"  - {r}" for r in self._recent_reply_cache[-3:])
                scene_constraints.append(f"Твои последние реплики (НЕ ПОВТОРЯЙ ИХ ДОСЛОВНО):\n{recent_lines}")
            if memory_confidence == "low":
                scene_constraints.append("Память сейчас не даёт уверенной опоры. Не придумывай прошлые разговоры и не ссылайся на них как на факт.")
            if topic_change_marker:
                scene_constraints.append(topic_change_marker)
            rejected_topics = list((self.scene_state or {}).get("rejected_topics", {}).keys())
            if rejected_topics:
                scene_constraints.append(f"Не возвращайся к темам: {', '.join(rejected_topics[:3])}.")
            focus_target = (self.scene_state or {}).get("focus_target")
            if focus_target == "creator":
                scene_constraints.append("Главный фокус сейчас на создателе и его текущей реплике, а не на случайной ассоциации.")
            elif focus_target == "scene":
                scene_constraints.append("Главный фокус сейчас на происходящем моменте. Не уводи ответ в сторону.")
            if "?" in user_input:
                scene_constraints.append("В текущей реплике есть прямой вопрос. Ответь сначала на него, не продолжай хвост предыдущей темы.")
            if "а ты" in user_input.lower() or "а тебе" in user_input.lower():
                scene_constraints.append("Если пользователь сказал сначала о себе, а потом спросил 'а ты/а тебе', не отвечай за пользователя. Ответь именно за Монику.")
            scene_constraints.append("Если у тебя появилась вторая мысль, не переноси её в следующий ход: либо заверши её сейчас одной короткой фразой, либо отбрось.")
            if scene_constraints:
                user_message_with_memory = f"[SCENE CONSTRAINTS]\n- " + "\n- ".join(scene_constraints) + f"\n\n{user_message_with_memory}"
            
            cognitive_context = ""
            response_policy_context = ""
            turn_contract_context = ""
            response_decision = None
            turn_contract = None
            try:
                cognitive_state = self.cognitive_state_compiler.compile(
                    source=(getattr(stimulus, "source", "") or "console"),
                    user_text=user_input,
                    person_id=social_person_id,
                    display_name=social_display_name,
                    role=relationship_role,
                    priority=int(getattr(stimulus, "priority", 50) or 50),
                    metadata=getattr(stimulus, "metadata", {}) or {},
                    scene_state=planning_scene_state,
                    relationship_state=pre_relationship_state,
                    memory_facts=relevant_facts,
                    active_desires=pre_active_desires,
                    active_opinions=pre_active_opinions,
                )
                response_decision = self.response_policy.decide(cognitive_state, behavior_plan)
                self.response_policy.apply_to_behavior_plan(behavior_plan, response_decision)
                turn_contract = self.turn_orchestrator.build(
                    user_text=user_input,
                    source=(getattr(stimulus, "source", "") or "console"),
                    role=relationship_role,
                    cognitive_state=cognitive_state,
                    response_decision=response_decision,
                    behavior_plan=behavior_plan,
                    scene_state=planning_scene_state,
                    memory_facts=relevant_facts,
                    active_desires=pre_active_desires,
                    active_opinions=pre_active_opinions,
                    boundary_mode=str(getattr(self, "_current_boundary_mode", "twitch_safe") or "twitch_safe"),
                )
                if not turn_contract.allow_desires:
                    pre_active_desires = []
                    desire_context = ""
                if not turn_contract.allow_background_topics:
                    pre_active_opinions = []
                    opinion_context = ""
                if getattr(turn_contract, "max_sentences", 0):
                    try:
                        behavior_plan.max_sentences = min(int(getattr(behavior_plan, "max_sentences", turn_contract.max_sentences) or turn_contract.max_sentences), int(turn_contract.max_sentences))
                    except Exception:
                        behavior_plan.max_sentences = int(turn_contract.max_sentences)
                cognitive_context = self.cognitive_state_compiler.prompt_block(cognitive_state)
                response_policy_context = response_decision.prompt_block()
                turn_contract_context = turn_contract.prompt_block()
                runtime_log_dict("COGNITIVE_STATE", cognitive_state.to_dict())
                runtime_log_dict("RESPONSE_POLICY", response_decision.__dict__)
                runtime_log_dict("TURN_CONTRACT", turn_contract.to_dict())
            except Exception as e:
                runtime_log(f"COGNITIVE_STATE_ERROR | {e}")

            architecture_contract = (
                "[ARCHITECTURE CONTRACT]\n"
                "- Cognitive State и Response Policy являются главным состоянием мозга перед ответом.\n"
                "- Старые блоки ниже являются источниками данных, а не отдельными командирами ответа.\n"
                "- Если блоки конфликтуют, следуй Cognitive State, Response Policy, проверенной памяти и safety."
            )
            try:
                repetition_context = self.repetition_guard.prompt_block(
                    self.repetition_session,
                    [m.get("content", "") for m in self.history if isinstance(m, dict) and m.get("role") == "assistant"][-4:],
                )
            except Exception as exc:
                runtime_log(f"REPETITION_CONTEXT_ERROR | {exc}")
                repetition_context = ""
            layered_context = "\n".join(part for part in [architecture_contract, turn_contract_context, cognitive_context, response_policy_context, repetition_context, self_context, emotion_context, unified_emotion_context, affection_context, social_context, desire_context, opinion_context, live_context] if part)
            runtime_overlay = self.behavior_director.build_runtime_overlay(
                behavior_plan,
                planning_scene_state,
                pre_relationship_state,
            )
            enriched_message = f"{layered_context}\n\n{runtime_overlay}\n{user_message_with_memory}{continuity_hint}{initiative_hint}"
            if inner_thought:
                enriched_message = f"Твоя внутренняя мысль: {inner_thought}\n\n{enriched_message}"
            
            self.history.append({"role": "user", "content": user_input})
            if turn_contract is not None:
                enriched_message = self.prompt_budget.fit_text(
                    enriched_message,
                    int(getattr(turn_contract, "max_prompt_chars", 16000) or 16000),
                )
            llm_messages = self.history[:-1] + [{"role": "user", "content": enriched_message}]
            qwen_mode = "qwen" in (self.model or "").lower()
            if qwen_mode and llm_messages:
                llm_messages[-1]["content"] = "/no_think\n" + llm_messages[-1]["content"]

            tools = [
                {"type": "function", "function": {"name": "get_wiki_info", "description": "Поиск в вики", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "get_timeline_info", "description": "Поиск в таймлайне", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "get_person_info", "description": "Информация о человеке", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}}}
            ]

            sampling = self.behavior_director.adjust_sampling(
                self.affection_state.to_sampling_params(),
                behavior_plan,
            )
            
            with timing_block(f"  [{self.message_counter}] LLM_генерация"):
                try:
                    if qwen_mode:
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=llm_messages,
                            temperature=sampling["temperature"],
                            max_tokens=behavior_plan.max_tokens,
                            presence_penalty=sampling["presence_penalty"],
                            frequency_penalty=sampling["frequency_penalty"],
                            top_p=sampling.get("top_p", 0.9)
                        )
                        msg = response.choices[0].message
                        monika_reply = (msg.content or "").strip()
                        if not monika_reply:
                            runtime_log("LLM_RETRY | Qwen returned empty content, retrying with minimal no_think prompt")
                            retry_messages = [
                                {"role": "system", "content": self.get_system_prompt()},
                                {
                                    "role": "user",
                                    "content": (
                                        "/no_think\n"
                                        "Ответь сразу живой репликой Моники. Без reasoning, без <think>, без служебных блоков.\n"
                                        f"Сообщение пользователя: {user_input}"
                                    ),
                                },
                            ]
                            retry = self.client.chat.completions.create(
                                model=self.model,
                                messages=retry_messages,
                                temperature=max(0.55, min(0.8, sampling["temperature"])),
                                max_tokens=max(behavior_plan.max_tokens, 220),
                                presence_penalty=0.0,
                                frequency_penalty=0.0,
                                top_p=0.9
                            )
                            monika_reply = (retry.choices[0].message.content or "").strip()
                    else:
                        response = self.client.chat.completions.create(
                            model=self.model,
                            messages=llm_messages,
                            tools=tools,
                            tool_choice="auto",
                            temperature=sampling["temperature"],
                            max_tokens=behavior_plan.max_tokens,
                            presence_penalty=sampling["presence_penalty"],
                            frequency_penalty=sampling["frequency_penalty"],
                            top_p=sampling.get("top_p", 0.9)
                        )
                        msg = response.choices[0].message
                        tool_calls = getattr(msg, "tool_calls", None)
                        if tool_calls:
                            tool_call = tool_calls[0]
                            func_name = tool_call.function.name
                            args = json.loads(tool_call.function.arguments)
                            if func_name == "get_wiki_info":
                                result = self.builder.get_wiki_info(args.get("query"))
                            elif func_name == "get_timeline_info":
                                result = self.builder.get_timeline_info(args.get("query"))
                            else:
                                result = self.builder.get_person_info(args.get("name"))
                            self.history.append(msg)
                            self.history.append({"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": result})
                            second_messages = self.history[:-2] + [
                                {"role": "user", "content": enriched_message},
                                msg,
                                {"role": "tool", "tool_call_id": tool_call.id, "name": func_name, "content": result},
                            ]
                            second = self.client.chat.completions.create(
                                model=self.model,
                                messages=second_messages,
                                temperature=sampling["temperature"],
                                max_tokens=behavior_plan.max_tokens,
                                presence_penalty=sampling["presence_penalty"],
                                frequency_penalty=sampling["frequency_penalty"],
                                top_p=sampling.get("top_p", 0.9)
                            )
                            monika_reply = (second.choices[0].message.content or "").strip()
                        else:
                            monika_reply = (msg.content or "").strip()
                except Exception as e:
                    monika_reply = f"Ошибка: {e}"

                # Очистка и применение Persona
                monika_reply = repair_mojibake(monika_reply)
                print(f"[LLM Raw] {monika_reply}")
                runtime_log(f"LLM_RAW | {monika_reply}")
                raw_before_cleanup = monika_reply
                try:
                    self.llm_trace.record(
                        turn_id=str(getattr(locals().get("turn_contract"), "turn_id", "")),
                        purpose="console_main",
                        model=self.model,
                        messages=llm_messages,
                        params={
                            "temperature": sampling.get("temperature"),
                            "max_tokens": getattr(behavior_plan, "max_tokens", None),
                            "presence_penalty": sampling.get("presence_penalty"),
                            "frequency_penalty": sampling.get("frequency_penalty"),
                            "top_p": sampling.get("top_p", 0.9),
                        },
                        raw=raw_before_cleanup,
                        policy=getattr(locals().get("turn_contract"), "to_dict", lambda: {})(),
                    )
                except Exception:
                    pass
                monika_reply = clean_roleplay(monika_reply)
                monika_reply = self.persona.apply_drift_guard(monika_reply)
                monika_reply = self.persona._normalize_response_text(monika_reply)
                
                # Единый постпроцессинг: mirror, ложная память, stale/loop ответы.
                monika_reply = self._postprocess_generated_reply(
                    monika_reply,
                    user_input,
                    memory_confidence,
                    relationship_role,
                    stimulus=stimulus,
                )
                monika_reply = self._repair_desire_consistency(user_input, monika_reply, pre_active_desires)
                # # YUNA_RECALL_REPAIR_V1
                try:
                    if hasattr(self, "yuna_bridge") and self.yuna_bridge is not None:
                        _yd = locals().get("stage_decision", None)
                        _ys = ""
                        if isinstance(_yd, dict):
                            _ys = str(_yd.get("stage") or _yd.get("stage_mode") or "")
                        elif _yd is not None:
                            _ys = str(getattr(_yd, "stage", "") or getattr(_yd, "stage_mode", "") or "")
                        _before_yuna_repair = monika_reply
                        monika_reply = self.yuna_bridge.repair_reply(
                            user_input=locals().get("user_input", ""),
                            monika_reply=monika_reply,
                            stage_mode=_ys,
                            person_id=locals().get("social_person_id", "Duncan"),
                        )
                        if monika_reply != _before_yuna_repair:
                            runtime_log(f"YUNA_RECALL_REPAIR | {monika_reply}")
                except Exception as e:
                    runtime_log(f"YUNA_RECALL_REPAIR_ERROR | {e}")

                try:
                    from stage_runtime_hardening import harden_reply_after_generation
                    monika_reply = harden_reply_after_generation(
                        user_input=user_input,
                        reply=monika_reply,
                        stage_decision=locals().get("stage_decision", getattr(self, "current_stage_decision", None)),
                        social_info=getattr(self, "current_social_memory_info", None),
                        persona=self.persona,
                        runtime_log_dict=runtime_log_dict,
                    )
                except Exception as exc:
                    runtime_log(f"STAGE_HARDENING_ERROR | {exc}")
                try:
                    cognitive_guard = self.cognitive_postguard.assess(
                        monika_reply,
                        user_input,
                        cognitive_state=locals().get("cognitive_state"),
                        identity_boundary=getattr(locals().get("cognitive_state", None), "identity_boundary", None),
                    )
                    runtime_log_dict("COGNITIVE_POSTGUARD", cognitive_guard.__dict__)
                    if not cognitive_guard.ok:
                        monika_reply = self._controlled_reply(
                            user_input,
                            intent="исправить ответ, который не подчинился cognitive state",
                            constraints=cognitive_guard.constraints + [
                                "Не используй заготовленную фразу.",
                                "Ответь из текущей ситуации, людей и проверенной памяти.",
                            ],
                            relationship_role=relationship_role,
                            max_sentences=max(1, int(getattr(locals().get("response_decision"), "max_sentences", 2) or 2)),
                            max_tokens=max(120, int(getattr(locals().get("response_decision"), "max_tokens", 180) or 180)),
                            original_reply=monika_reply,
                            must_replace=True,
                        )
                except Exception as exc:
                    runtime_log(f"COGNITIVE_POSTGUARD_ERROR | {exc}")
                runtime_log_dict("POSTPROCESS", {
                    "raw_before_cleanup": raw_before_cleanup,
                    "after_clean_roleplay": clean_roleplay(raw_before_cleanup),
                    "memory_confidence": memory_confidence,
                    "rejected_topics": list((self.scene_state or {}).get("rejected_topics", {}).keys()),
                    "final_after_postprocess": monika_reply,
                })
                try:
                    _yuna_stage_obj = locals().get('stage_decision', None)
                    _yuna_stage_mode = (getattr(_yuna_stage_obj, 'mode', '') or getattr(_yuna_stage_obj, 'stage_mode', '') or (locals().get('stage_mode', '') or ''))
                    _yuna_before = locals().get('monika_reply', '')
                    _yuna_after = self._yuna_final_repair_safe(
                        user_input=locals().get('user_input', getattr(locals().get('stimulus', None), 'text', '')),
                        monika_reply=_yuna_before,
                        stage_mode=_yuna_stage_mode,
                        social_person_id=locals().get('social_person_id', 'Duncan'),
                    )
                    if _yuna_after and _yuna_after != _yuna_before:
                        runtime_log(f"YUNA_FINAL_REPAIR_APPLIED | {_yuna_after}")
                        monika_reply = _yuna_after
                except Exception as exc:
                    runtime_log(f"YUNA_FINAL_REPAIR_ERROR | {exc}")
                try:
                    answer_eval = self.answer_evaluator.evaluate(
                        monika_reply,
                        user_input,
                        contract=locals().get("turn_contract"),
                        cognitive_state=locals().get("cognitive_state"),
                        memory_facts=relevant_facts,
                    )
                    runtime_log_dict("ANSWER_EVALUATION", answer_eval.to_dict())
                    if not answer_eval.ok:
                        monika_reply = self._controlled_reply(
                            user_input,
                            intent="repair answer after turn evaluator",
                            constraints=answer_eval.constraints + [
                                "Answer the latest user message directly.",
                                "Do not leak old scene, old desire, or internal instruction.",
                            ],
                            relationship_role=relationship_role,
                            max_sentences=max(1, int(getattr(locals().get("turn_contract"), "max_sentences", 2) or 2)),
                            max_tokens=max(140, int(getattr(behavior_plan, "max_tokens", 180) or 180)),
                            original_reply=monika_reply,
                            must_replace=True,
                        )
                        retry_eval = self.answer_evaluator.evaluate(
                            monika_reply,
                            user_input,
                            contract=locals().get("turn_contract"),
                            cognitive_state=locals().get("cognitive_state"),
                            memory_facts=relevant_facts,
                        )
                        runtime_log_dict("ANSWER_EVALUATION_RETRY", retry_eval.to_dict())
                except Exception as exc:
                    runtime_log(f"ANSWER_EVALUATION_ERROR | {exc}")

                print(f"[LLM PreFinal] {monika_reply}")
                try:
                    _yuna_stage_obj = locals().get('stage_decision', None)
                    _yuna_stage_mode = (getattr(_yuna_stage_obj, 'mode', '') or getattr(_yuna_stage_obj, 'stage_mode', '') or (locals().get('stage_mode', '') or ''))
                    _yuna_before = locals().get('monika_reply', '')
                    _yuna_after = self._yuna_final_repair_safe(
                        user_input=locals().get('user_input', getattr(locals().get('stimulus', None), 'text', '')),
                        monika_reply=_yuna_before,
                        stage_mode=_yuna_stage_mode,
                        social_person_id=locals().get('social_person_id', 'Duncan'),
                    )
                    if _yuna_after and _yuna_after != _yuna_before:
                        runtime_log(f"YUNA_FINAL_REPAIR_APPLIED | {_yuna_after}")
                        monika_reply = _yuna_after
                except Exception as exc:
                    runtime_log(f"YUNA_FINAL_REPAIR_ERROR | {exc}")
                try:
                    final_eval = self.answer_evaluator.evaluate(
                        monika_reply,
                        user_input,
                        contract=locals().get("turn_contract"),
                        cognitive_state=locals().get("cognitive_state"),
                        memory_facts=relevant_facts,
                    )
                    runtime_log_dict("ANSWER_EVALUATION_FINAL", final_eval.to_dict())
                    if not final_eval.ok:
                        monika_reply = self._controlled_reply(
                            user_input,
                            intent="final repair after all postprocessors",
                            constraints=final_eval.constraints + [
                                "Use the current turn contract, not stale context.",
                                "Do not claim unverified memory or physical experience.",
                            ],
                            relationship_role=relationship_role,
                            max_sentences=max(1, int(getattr(locals().get("turn_contract"), "max_sentences", 2) or 2)),
                            max_tokens=max(140, int(getattr(behavior_plan, "max_tokens", 180) or 180)),
                            original_reply=monika_reply,
                            must_replace=True,
                        )
                        runtime_log_dict("ANSWER_EVALUATION_FINAL_REPAIR", {"reply": monika_reply})
                except Exception as exc:
                    runtime_log(f"ANSWER_EVALUATION_FINAL_ERROR | {exc}")
                try:
                    repetition_assessment = self.repetition_guard.assess(
                        monika_reply,
                        self.history,
                        self.repetition_session,
                    )
                    runtime_log_dict("REPETITION_GUARD", repetition_assessment.to_dict())
                    if not repetition_assessment.ok:
                        monika_reply = self._controlled_reply(
                            user_input,
                            intent="перегенерировать ответ без повторяющихся фраз и без старого речевого костыля",
                            constraints=repetition_assessment.constraints + [
                                "Ответь на текущую реплику новым синтаксисом.",
                                "Не объясняй, что избегаешь повтора.",
                                "Добавь конкретное действие, деталь или позицию вместо обещания начать.",
                            ],
                            relationship_role=relationship_role,
                            max_sentences=max(1, int(getattr(locals().get("turn_contract"), "max_sentences", 2) or 2)),
                            max_tokens=max(140, int(getattr(behavior_plan, "max_tokens", 180) or 180)),
                            original_reply=monika_reply,
                            must_replace=True,
                        )
                        repetition_retry = self.repetition_guard.assess(
                            monika_reply,
                            self.history,
                            self.repetition_session,
                        )
                        runtime_log_dict("REPETITION_GUARD_RETRY", repetition_retry.to_dict())
                        if not repetition_retry.ok:
                            monika_reply = self.repetition_guard.sanitize(monika_reply, self.repetition_session)
                except Exception as exc:
                    runtime_log(f"REPETITION_GUARD_ERROR | {exc}")
                print(f"[LLM Final] {monika_reply}")
                runtime_log(f"LLM_FINAL | {monika_reply}")
                try:
                    memory_governance = self.memory_governance.decide(
                        user_input,
                        monika_reply,
                        contract=locals().get("turn_contract"),
                        boundary_decision=locals().get("boundary_decision"),
                    )
                    runtime_log_dict("MEMORY_GOVERNANCE", memory_governance.to_dict())
                    if getattr(self, "_current_boundary_memory_allowed", True) and memory_governance.write_allowed:
                        runtime_log_dict("MEMORY_WRITE_POLICY", self.memory_write_policy.classify(user_input, monika_reply))
                        self.cognitive_state_compiler.observe_turn(user_input, monika_reply, locals().get("cognitive_state"))
                    else:
                        runtime_log_dict("MEMORY_WRITE_POLICY", {
                            "stable_fact_candidate": False,
                            "social_event": False,
                            "scene_event": False,
                            "suppressed": "boundary_consent_or_memory_governance",
                        })
                    action_plan = self.action_layer.plan(
                        monika_reply,
                        response_decision=locals().get("response_decision"),
                        emotion=getattr(self, "current_unified_emotion", {}) or {},
                    )
                    runtime_log_dict("ACTION_PLAN", action_plan.__dict__)
                    self.debug_trace.record("action_plan", action_plan.__dict__)
                except Exception as e:
                    runtime_log(f"ACTION_PLAN_ERROR | {e}")
                if getattr(self, "_current_boundary_memory_allowed", True) and bool(locals().get("memory_governance", None).write_allowed if locals().get("memory_governance", None) else True):
                    self.desire_memory.observe_monika_reply(user_input, monika_reply)
                    self.opinion_memory.observe_monika_reply(monika_reply, source="llm_reply")
                    try:
                        self.self_state.observe_monika_reply(user_input, monika_reply, relationship_role=relationship_role)
                    except Exception as e:
                        runtime_log(f"SELF_STATE_REPLY_ERROR | {e}")
                 
                self.history.append({"role": "assistant", "content": monika_reply})
                if getattr(self, "_current_boundary_memory_allowed", True):
                    self._remember_scene_turn(
                        user_input,
                        monika_reply,
                        relationship_role,
                        social_intent=behavior_plan.social_intent,
                        person_id=social_person_id,
                    )
                try:
                    if getattr(self, "_current_boundary_memory_allowed", True):
                        stage_info = self.stage_director.classify(
                            user_input,
                            relationship_role=relationship_role,
                            social_intent=behavior_plan.social_intent,
                            contains_memory=contains_memory,
                            opinion_request=self.opinion_core.is_opinion_request(user_input),
                        )
                        self.session_mind.observe_turn(
                            user_input,
                            monika_reply,
                            relationship_role=relationship_role,
                            stage=(stage_info.get("stage", "REACT") if isinstance(stage_info, dict) else getattr(stage_info, "stage", "REACT")),
                            guard_reason=(locals().get("guard_info") or {}).get("reason", "ok"),
                            opinion=self.opinion_core.get_current_opinion(user_input, create=False),
                        )
                        self.opinion_core.observe_reply(user_input, monika_reply)
                        self.self_state.observe_monika_reply(user_input, monika_reply, relationship_role=relationship_role)
                except Exception as e:
                    runtime_log(f"STREAM_RUNTIME_OBSERVE_ERROR | {e}")

            print(f"\nМоника: {monika_reply}")
            runtime_log(f"OUTPUT | Моника: {monika_reply}")
            if getattr(self, "_current_boundary_tts_allowed", True):
                self.speak(monika_reply)
            else:
                runtime_log("TTS_SUPPRESSED | boundary_consent | private_adult")
            try:
                self.turn_scheduler.after_reply()
            except Exception:
                pass
            self.update_mood(monika_reply, is_user=False)
            
            self.last_monika_message = monika_reply
            self._cache_reply(monika_reply)
            if getattr(self, "_current_boundary_memory_allowed", True):
                self.builder.log_message("assistant", monika_reply)
                self._yuna_observe_turn_safe(
                    user_input=locals().get("user_input", ""),
                    monika_reply=locals().get("monika_reply", ""),
                    person_id=locals().get("social_person_id", getattr(self, "user_id", "Duncan")),
                    display_name=locals().get("social_display_name", str(locals().get("social_person_id", getattr(self, "user_id", "Duncan")))),
                    stage_decision=locals().get("stage_decision", None),
                )
                self._reflection_observe_safe(
                    user_input=user_input,
                    monika_reply=monika_reply,
                    person_id=(locals().get('social_person_id') or STREAMER_ID),
                    stage_decision=locals().get('stage_decision'),
                    guard_info=locals().get('guard_info'),
                    source='llm_final',
                )
                self._message_counter_since_consolidation += 1
                if self._message_counter_since_consolidation >= 15:
                    threading.Thread(
                        target=self._auto_consolidate,
                        daemon=True
                    ).start()
            else:
                runtime_log("MEMORY_SUPPRESSED | boundary_consent | assistant_persistent_write")
            
            if len(self.history) > 40:
                self.history = [self.history[0]] + self.history[-39:]
            
            if self.message_counter % 10 == 0:
                monitor.print_all()


    def _reflection_observe_safe(self, user_input: str, monika_reply: str, person_id: str | None = None,
                                 stage_decision=None, guard_info=None, source: str = "runtime"):
        """Best-effort reflection logging. Never breaks the live chat."""
        try:
            curator = getattr(self, "reflection_curator", None)
            if not curator:
                return
            person_id = person_id or STREAMER_ID
            stage_mode = None
            if stage_decision is not None:
                if isinstance(stage_decision, dict):
                    stage_mode = stage_decision.get("mode") or stage_decision.get("stage")
                else:
                    stage_mode = getattr(stage_decision, "mode", None) or getattr(stage_decision, "stage", None)
            guard_reasons = []
            if guard_info is not None:
                if isinstance(guard_info, dict):
                    guard_reasons = guard_info.get("reasons") or guard_info.get("issues") or []
                else:
                    guard_reasons = getattr(guard_info, "reasons", None) or getattr(guard_info, "issues", None) or []
            event = curator.observe_turn(
                person_id=person_id,
                user_input=user_input,
                monika_reply=monika_reply,
                stage_mode=str(stage_mode or ""),
                guard_reasons=guard_reasons,
                source=source,
            )
            runtime_log_dict("REFLECTION_OBSERVE", event)
        except Exception as exc:
            runtime_log(f"REFLECTION_OBSERVE_ERROR | {exc}")


    def _yuna_observe_turn_safe(self, user_input="", monika_reply="", person_id=None, display_name=None, stage_decision=None, stage_mode=""):
        """Safely save a compact YunaBridge turn after a reply exists.

        This method is intentionally safe when called from an early branch where
        local variables may not exist yet. Empty replies are ignored.
        """
        try:
            bridge = getattr(self, "yuna_bridge", None)
            if not bridge:
                return

            user_input = (user_input or "").strip()
            monika_reply = (monika_reply or "").strip()
            if not user_input or not monika_reply:
                return

            resolved_stage = stage_mode or ""
            if not resolved_stage and stage_decision is not None:
                if isinstance(stage_decision, dict):
                    resolved_stage = str(stage_decision.get("mode") or stage_decision.get("stage_mode") or "")
                else:
                    resolved_stage = str(getattr(stage_decision, "mode", "") or getattr(stage_decision, "stage_mode", "") or "")

            pid = person_id or getattr(self, "user_id", "Duncan")
            dname = display_name or str(pid)
            bridge.observe_turn(
                user_input=user_input,
                monika_reply=monika_reply,
                person_id=pid,
                display_name=dname,
                stage_mode=resolved_stage,
            )
            try:
                runtime_log_dict("YUNA_OBSERVE", {"ok": True, "stage_mode": resolved_stage})
            except Exception:
                pass
        except Exception as exc:
            try:
                runtime_log(f"YUNA_OBSERVE_ERROR | {exc}")
            except Exception:
                pass

    def _yuna_final_repair_safe(self, user_input="", monika_reply="", stage_mode="", social_person_id="Duncan"):
        """Final evidence-bound YunaBridge repair. Safe even when bridge is absent."""
        try:
            if not getattr(self, "yuna_bridge", None):
                return monika_reply
            repaired = self.yuna_bridge.repair_reply(
                user_input=user_input,
                monika_reply=monika_reply,
                stage_mode=stage_mode,
                person_id=social_person_id or "Duncan",
            )
            return repaired or monika_reply
        except Exception as exc:
            try:
                runtime_log(f"YUNA_FINAL_REPAIR_ERROR | {exc}")
            except Exception:
                pass
            return monika_reply

    def chat(self):
        print("=== Чат с Моникой 4.0 (Persona Layer) ===\n")
        print("🎤 Зажмите F10, говорите, отпустите - Моника ответит.\n")
        print("Команды СОЗДАТЕЛЯ:\n  запомни ...\n  вспомни ...\n  !история\n  !темы\n  !репутация\n  !очистка\n  !вики\n  !сон\n")
        print("Моника слушает, запоминает и оживает со временем!\n")

        def signal_handler(sig, frame):
            print("\n[Завершение] Корректное выключение...")
            self.running = False
            self.signals.terminate = True
            global _ws_running
            _ws_running = False
            _ws_queue.put(None)
        
        signal.signal(signal.SIGINT, signal_handler)

        try:
            while self.running:
                while self.stimulus_queue.qsize() > 5:
                    self.stimulus_queue.get_nowait()
                
                if not self.stimulus_queue.empty():
                    self.generate_response()
                else:
                    time.sleep(0.05)
        except KeyboardInterrupt:
            self.running = False
            self.signals.terminate = True

            if hasattr(self, 'tts_queue') and self.tts_queue is not None:
                self.tts_queue.put(None)

            if hasattr(self, 'stt') and self.stt is not None:
                self.stt.stop()

            if hasattr(self, 'builder') and self.builder is not None:
                self.builder.close()
            monitor.print_all()
            monitor.save_to_file("timing_stats_final.json")
            print("\nДо свидания!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--script-file", dest="script_file", default=None)
    args = parser.parse_args()
    chat = MonikaConsoleChat(script_file=args.script_file)
    chat.chat()


