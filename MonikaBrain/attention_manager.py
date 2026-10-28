# attention_manager.py
import time
import queue
from typing import Optional, List
from stimulus import Stimulus
from config import PRIORITIES, ATTENTION_CONFIG

class AttentionManager:
    """Менеджер внимания Моники — выбирает самый важный стимул."""
    
    def __init__(self, signals, builder):
        self.signals = signals
        self.builder = builder
        self.pending_stimuli: List[Stimulus] = []
        self.last_response_time = 0
        self.min_interval = ATTENTION_CONFIG["min_interruption_interval"]
        self.max_pending = ATTENTION_CONFIG["max_pending_triggers"]
        self.natural_pause_duration = ATTENTION_CONFIG["natural_pause_duration"]
        
        # Статистика
        self.stats = {
            "total_stimuli": 0,
            "processed": 0,
            "ignored": 0,
            "interrupted": 0
        }
    
    def add_stimulus(self, stimulus: Stimulus) -> bool:
        """Добавляет стимул в очередь на рассмотрение."""
        self.stats["total_stimuli"] += 1
        self.pending_stimuli.append(stimulus)
        
        # Ограничиваем размер очереди
        if len(self.pending_stimuli) > self.max_pending * 2:
            # Удаляем самые старые с низким приоритетом
            self.pending_stimuli.sort(key=lambda s: (s.priority, -s.timestamp))
            self.pending_stimuli = self.pending_stimuli[-self.max_pending:]
        
        return True
    
    def select_best_stimulus(self) -> Optional[Stimulus]:
        """Выбирает лучший стимул для обработки прямо сейчас."""
        if not self.pending_stimuli:
            return None
        
        # Фильтруем по времени (не старше 30 секунд)
        current_time = time.time()
        fresh_stimuli = [s for s in self.pending_stimuli if current_time - s.timestamp < 30]
        
        if not fresh_stimuli:
            self.pending_stimuli.clear()
            return None
        
        # Сортируем по приоритету (чем выше число, тем важнее)
        fresh_stimuli.sort(key=lambda s: (s.priority, -s.timestamp), reverse=True)
        best = fresh_stimuli[0]
        
        # Проверяем, можно ли ответить сейчас
        if self.can_respond_now(best):
            self.pending_stimuli.remove(best)
            self.stats["processed"] += 1
            return best
        
        return None
    
    def can_respond_now(self, stimulus: Stimulus) -> bool:
        """Проверяет, можно ли ответить на стимул прямо сейчас."""
        # Не перебиваем, если Моника уже говорит или думает
        if self.signals.AI_speaking or self.signals.AI_thinking:
            return False
        
        # Проверяем интервал между ответами
        if time.time() - self.last_response_time < self.min_interval:
            # Но для критических приоритетов делаем исключение
            if stimulus.priority < PRIORITIES["streamer_voice"]:
                return False
        
        # Не перебиваем стримера, если приоритет не критический
        if self.signals.human_speaking and stimulus.priority < PRIORITIES["streamer_voice"]:
            return False
        
        return True
    
    def should_interrupt(self, trigger: dict) -> bool:
        """Решает, стоит ли прервать разговор из-за ассоциативного триггера."""
        # Не перебиваем слишком часто
        if time.time() - self.last_response_time < self.min_interval:
            return False
        
        # Не перебиваем, если Моника занята
        if self.signals.AI_speaking or self.signals.AI_thinking:
            return False
        
        # Проверяем приоритет триггера
        if trigger.get("priority", 0) < PRIORITIES["association"]:
            return False
        
        self.stats["interrupted"] += 1
        return True
    
    def mark_response_sent(self):
        """Отмечает, что ответ был отправлен."""
        self.last_response_time = time.time()
    
    def clear_old_stimuli(self, max_age: float = 60):
        """Очищает старые стимулы."""
        current_time = time.time()
        self.pending_stimuli = [
            s for s in self.pending_stimuli 
            if current_time - s.timestamp < max_age
        ]
    
    def get_stats(self) -> dict:
        """Возвращает статистику работы."""
        return {
            **self.stats,
            "pending_count": len(self.pending_stimuli)
        }
    
    def reset_stats(self):
        """Сбрасывает статистику."""
        self.stats = {
            "total_stimuli": 0,
            "processed": 0,
            "ignored": 0,
            "interrupted": 0
        }