# signals.py
import time
from collections import deque

class Signals:
    def __init__(self):
        # Флаги состояния
        self.stt_ready = True
        self.tts_ready = True
        self.human_speaking = False
        self.AI_thinking = False
        self.AI_speaking = False
        
        # Сообщения
        self.new_message = False
        self.last_user_message = ""
        self.last_ai_response = ""
        self.last_message_time = 0.0
        
        # Очередь сообщений Twitch (пока пустая, для будущей интеграции)
        self.recentTwitchMessages = deque(maxlen=20)
        
        # События стрима
        self.stream_event = None
        self.stream_active = False
        
        # Завершение
        self.terminate = False
    
    def add_twitch_message(self, username: str, message: str):
        """Добавляет сообщение из Twitch чата."""
        self.recentTwitchMessages.append({
            "username": username,
            "message": message,
            "timestamp": time.time()
        })
        self.new_message = True
        self.last_message_time = time.time()
    
    def set_stream_event(self, event_type: str, data: dict):
        """Устанавливает событие стрима (рейд, подписка, донат)."""
        self.stream_event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time()
        }
        self.new_message = True
        self.last_message_time = time.time()
    
    def clear_stream_event(self):
        """Очищает событие стрима после обработки."""
        self.stream_event = None
    
    def reset_for_new_message(self):
        """Сбрасывает флаги для нового сообщения."""
        self.new_message = False
    
    def is_anyone_speaking(self) -> bool:
        """Проверяет, говорит ли кто-то сейчас."""
        return self.human_speaking or self.AI_speaking
    
    def is_busy(self) -> bool:
        """Проверяет, занята ли Моника."""
        return self.AI_thinking or self.AI_speaking