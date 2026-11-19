# config.py
import os

# Пути
BASE_DIR = r"F:\МоnikaVtuber"
BRAIN_DIR = os.path.join(BASE_DIR, "MonikaBrain")
DB_PATH = os.path.join(BRAIN_DIR, "monika_memory.db")
TTS_CACHE_DIR = r"F:\МоnikaVtuber\TTS"
TTS_PLAYBACK_SPEED = 1.0  # 1.0 = нормальная скорость, 1.2 = на 20% быстрее
STT_TEMP_DIR = r"F:\STT"

# Настройки памяти
HALF_LIFE_DAYS = 7
IMPORTANCE_DECAY_FACTOR = 0.95

# Пользователь
STREAMER_ID = "Duncan"

# LLM
LLM_API_BASE = "http://localhost:1234/v1"
LLM_MODEL_NAME = "Mistral 7B Instruct v0.3"
# Ключевое слово для активации (если не push-to-talk)
KEYWORD = "моника"

# Telegram (отдельный проект)
TELEGRAM_BOT_TOKEN = ""
CREATOR_TELEGRAM_ID = 
TELEGRAM_PROXY_URL = None
BOT_MODE = "telegram"

# Twitch (для будущей интеграции)
TWITCH_BOT_NICK = "MonikaBot"
TWITCH_OAUTH_TOKEN = "oauth:заглушка"
TWITCH_CHANNEL = "dunkanlive"

# STT настройки
STT_MODEL_SIZE = "base"
STT_COMPUTE_TYPE = "int8"
STT_LANGUAGE = "ru"
STT_SAMPLE_RATE = 16000
STT_PTT_KEY = "f10"
STT_DEVICE_INDEX = 1
STT_VAD_MODE = 2
STT_VAD_FRAMES = 30
STT_BUFFER_SECONDS = 5
STT_OVERFLOW_WARNING = False

# Prompter
PATIENCE = 300 # секунд молчания перед проактивным сообщением

# ========== ПРИОРИТЕТЫ ДЛЯ ATTENTION MANAGER ==========
PRIORITIES = {
    "streamer_voice": 100,      # Голос стримера — высший приоритет
    "streamer_text": 95,        # Текст от стримера
    "stream_event": 90,         # Рейд, подписка, донат
    "direct_question": 80,      # Прямой вопрос к Монике
    "hater_attack": 75,         # Хейтер — надо ответить резко
    "association": 70,          # Ассоциативный триггер (вклиниться)
    "interesting_topic": 50,    # Интересная тема в чате
    "general_chat": 20,         # Обычный чат
    "proactive": 10,            # Проактивная мысль
}

# ========== НАСТРОЙКИ ATTENTION MANAGER ==========
ATTENTION_CONFIG = {
    "min_interruption_interval": 30,    # Минимум секунд между прерываниями
    "max_pending_triggers": 3,          # Сколько триггеров копить перед выбором
    "trigger_threshold": 0.7,           # Порог срабатывания ассоциаций
    "natural_pause_duration": 2.0,      # Длительность паузы для вклинивания
    "long_silence_duration": 5.0,       # Длительность тишины для проактива
}

# ========== НАСТРОЙКИ ЭМОЦИОНАЛЬНОЙ ПАМЯТИ ==========
EMOTIONAL_MEMORY_CONFIG = {
    "decay_rate": 0.01,         # Скорость забывания в день
    "forgiveness_threshold": 3,  # Сколько раз попросить прощения
    "max_intensity": 1.0,
    "min_intensity": 0.0,
}

# ========== НАСТРОЙКИ ПОТРЕБНОСТЕЙ ==========
NEEDS_CONFIG = {
    "social": {"initial": 0.5, "decay": 0.01, "gain_per_chat": 0.05},
    "entertainment": {"initial": 0.6, "decay": 0.02, "gain_per_fun": 0.1},
    "recognition": {"initial": 0.7, "decay": 0.01, "gain_per_sub": 0.2},
    "mischief": {"initial": 0.4, "decay": 0.01, "gain_per_hate": 0.15},
    "rest": {"initial": 0.3, "decay": 0.0, "gain_per_minute": 0.01},
}
