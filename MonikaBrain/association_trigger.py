# association_trigger.py
import time
from typing import Optional, Dict, Any, List

class AssociationTrigger:
    """Проверяет, должна ли Моника отреагировать на услышанное."""
    
    def __init__(self, builder):
        self.builder = builder
        self.trigger_threshold = 0.7
        self.last_trigger_time = 0
        self.trigger_cooldown = 15  # секунд между триггерами
        
        # Ключевые слова личности (любит/ненавидит)
        self.personality_triggers = {
            "love": ["аниме", "игры", "фильмы", "марвел", "витубер", "подписчики", "захват"],
            "hate": ["лаги", "тормозит", "скучно", "политика", "религия", "мат"],
            "opinion": ["черепашки", "ниндзя", "наруто", "сакура", "винкс", "аватар"]
        }
        
    def check(self, text: str, threshold: float = None) -> Optional[Dict[str, Any]]:
        """
        Проверяет текст на триггеры.
        Возвращает словарь с реакцией или None.
        """
        if threshold is None:
            threshold = self.trigger_threshold
        
        # Проверка кулдауна
        if time.time() - self.last_trigger_time < self.trigger_cooldown:
            return None
        
        triggers = []
        
        # 1. Поиск в Engram (семантическая память)
        memories = self.builder.search_facts(text, top_k=3)
        for memory in memories:
            similarity = self._calculate_similarity(text, memory)
            if similarity > threshold:
                triggers.append({
                    "type": "memory",
                    "content": memory,
                    "similarity": similarity,
                    "priority": 60 + int(similarity * 20),
                    "reaction": self._generate_memory_reaction(memory)
                })
        
        # 2. Триггеры личности
        text_lower = text.lower()
        for trigger_type, keywords in self.personality_triggers.items():
            for keyword in keywords:
                if keyword in text_lower:
                    triggers.append({
                        "type": "personality",
                        "subtype": trigger_type,
                        "keyword": keyword,
                        "priority": 70 if trigger_type == "hate" else 50,
                        "reaction": self._generate_personality_reaction(trigger_type, keyword)
                    })
                    break
        
        # 3. Проверка на противоречие
        if self._detect_disagreement(text):
            triggers.append({
                "type": "disagreement",
                "priority": 65,
                "reaction": "А вот я считаю наоборот! Ты всё неправильно делаешь!"
            })
        
        if triggers:
            best_trigger = max(triggers, key=lambda t: t["priority"])
            self.last_trigger_time = time.time()
            return best_trigger
        
        return None
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Простая оценка схожести по словам."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union)
    
    def _generate_memory_reaction(self, memory: str) -> str:
        """Генерирует реакцию на основе воспоминания."""
        templates = [
            f"О, точно! Я же помню, что {memory}!",
            f"Кстати о этом — {memory}!",
            f"Вспомнила! {memory}.",
        ]
        import random
        return random.choice(templates)
    
    def _generate_personality_reaction(self, trigger_type: str, keyword: str) -> str:
        """Генерирует реакцию на основе личности."""
        if trigger_type == "love":
            templates = [
                f"О, {keyword}! Я обожаю это!",
                f"Кстати о {keyword} — это моя страсть!",
                f"Ты заговорил о {keyword}? Я могу часами об этом говорить!",
            ]
        elif trigger_type == "hate":
            templates = [
                f"Фу, {keyword}? Терпеть не могу!",
                f"Серьёзно? {keyword}? Это же полный отстой!",
                f"О нет, только не {keyword}!",
            ]
        else:
            templates = [
                f"У меня есть своё мнение о {keyword}!",
                f"Кстати, о {keyword} — я считаю иначе!",
            ]
        import random
        return random.choice(templates)
    
    def _detect_disagreement(self, text: str) -> bool:
        """Определяет, есть ли в тексте повод для несогласия."""
        disagreement_markers = [
            "моника не права", "моника ошибается", "ты не права",
            "не согласен", "это не так", "чушь", "ерунда"
        ]
        text_lower = text.lower()
        return any(marker in text_lower for marker in disagreement_markers)