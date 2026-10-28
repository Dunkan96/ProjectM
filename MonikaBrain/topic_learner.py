# topic_learner.py
import re
from typing import Optional, Tuple, List

class TopicLearner:
    """Автономное обучение темам на основе реакций пользователя."""
    
    def __init__(self, builder):
        self.builder = builder
        
        self.topic_keywords = {
            "игры": ["игра", "dark souls", "rpg", "хоррор", "геймплей", "босс", "прохождение", "steam", "ps", "xbox", "elden ring", "скелет", "скелеты", "костер", "костёр", "щит", "откат", "лечись", "босс", "бонфаер"],
            "аниме": ["аниме", "наруто", "атака титанов", "сёнэн", "сериал", "персонаж", "манга", "студия", "гибли", "винкс"],
            "фильмы": ["фильм", "марвел", "кино", "dc", "супергерой", "боевик", "комедия", "драма", "актёр"],
            "еда": ["пицца", "еда", "вкусн", "готовить", "рецепт", "бургер", "суши", "роллы", "кофе", "чай", "чипсы"],
            "технологии": ["компьютер", "программа", "код", "ии", "нейросеть", "процессор", "видеокарта", "киберпанк"],
            "зрители": ["зритель", "подписчик", "аудитория", "чат", "фолловер", "публика"],
            "стримы": ["стрим", "трансляция", "эфир", "вебка", "микрофон", "озвучка"],
            "музыка": ["музыка", "песня", "трек", "альбом", "группа", "исполнитель", "саундтрек", "техно"],
            "природа": ["природа", "лес", "река", "озеро", "рыбалка", "погода", "закат", "птицы"],
            "отношения": ["любовь", "дружба", "друг", "подруга", "отношения", "чувства"],
            "интернет": ["мем", "мемы", "форум", "ютуб", "twitch", "твич", "реддит", "кринж", "интернет", "видос"],
        }
        
        self.rejection_phrases = [
            "не нужно про", "не надо про", "хватит про", "прекрати про", "забудь про",
            "отстань", "отвали", "заколебал", "надоело", "сколько можно",
            "мне не интересно", "это не интересно", "скучно про", "достало", "утомила",
            "смени тему", "давай не про", "закрой тему",
        ]
        
        self.interest_phrases = [
            "расскажи", "давай", "продолжай", "интересно", "круто", 
            "ого", "вау", "подробнее", "а что", "а как", "слушаю",
            "любопытно", "занятно", "прикольно", "класс", "супер"
        ]
    
    def extract_topics(self, text: str) -> List[str]:
        text_lower = text.lower()
        found_topics = []
        for topic, keywords in self.topic_keywords.items():
            for kw in keywords:
                if kw in text_lower:
                    found_topics.append(topic)
                    break
        return list(set(found_topics))
    
    def analyze_user_response(self, user_message: str, monika_previous_message: str = None) -> Optional[Tuple[str, bool, float]]:

        # STAGE_RUNTIME_GAME_OVERRIDE: panic/game commands should not be learned as food/relationships.
        text_probe = (user_message or "").replace("ё", "е").lower()
        if any(k in text_probe for k in [
            "dark souls", "дарк соул", "elden ring", "элден", "скелет", "костер", "костёр",
            "щит", "откат", "лечись", "босс", "бонфаер",
        ]):
            return ("игры", True, 0.3)
        user_topics = self.extract_topics(user_message)
        monika_topics = []
        if monika_previous_message:
            monika_topics = self.extract_topics(monika_previous_message)
        
        all_topics = user_topics + monika_topics
        if not all_topics:
            return None
        
        main_topic = all_topics[0]
        text_lower = user_message.lower()
        
        for phrase in self.rejection_phrases:
            if phrase in text_lower:
                intensity = 1.0
                if any(word in text_lower for word in ["совсем", "вообще", "полностью"]):
                    intensity = 1.5
                if "!" in user_message:
                    intensity += 0.3
                return (main_topic, False, min(2.0, intensity))
        
        for phrase in self.interest_phrases:
            if phrase in text_lower:
                intensity = 1.0
                if "!" in user_message or "?" in user_message:
                    intensity += 0.2
                if len(user_message.split()) > 10:
                    intensity += 0.3
                return (main_topic, True, min(1.5, intensity))
        
        return (main_topic, True, 0.3)
    
    def learn_from_interaction(self, user_message: str, monika_previous_message: str = None):
        result = self.analyze_user_response(user_message, monika_previous_message)
        if result:
            topic, success, intensity = result
            self.builder.update_topic_weight(topic, success, intensity)
            return topic, success, intensity
        return None, None, None
    
    def should_avoid_topic(self, topic: str) -> bool:
        cursor = self.builder.knowledge_conn.cursor()
        cursor.execute('''
            SELECT weight, cooldown_until FROM topic_weights 
            WHERE topic = ? AND (cooldown_until IS NULL OR cooldown_until < datetime('now'))
        ''', (topic,))
        row = cursor.fetchone()
        if not row:
            return False
        weight = row['weight']
        cooldown_until = row['cooldown_until']
        if cooldown_until:
            return True
        if weight < 0.3:
            return True
        return False
    
    def get_suggested_topic(self) -> str:
        return self.builder.get_best_topic()
    
    def get_topic_stats(self) -> dict:
        return self.builder.get_all_topic_weights()
