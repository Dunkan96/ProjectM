from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import re


@dataclass
class StageDecision:
    stage: str
    scene_goal: str
    max_sentences: int = 3
    max_tokens: int = 217
    allow_longform: bool = False
    direct_address: bool = True
    constraints: List[str] | None = None
    tags: List[str] | None = None

    def as_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['constraints'] = list(self.constraints or [])
        data['tags'] = list(self.tags or [])
        return data


class StageDirector:
    """Stream scene router for Monika.

    It chooses a performance mode and emits compact instructions. It never
    generates final replies and never stores facts.
    """

    def __init__(self) -> None:
        self._last_stage: str = 'REACT'
        self._last_topic: str = ''

    def classify(
        self,
        user_input: str,
        relationship_role: str = 'creator',
        social_intent: str = 'neutral_chat',
        contains_memory: bool = False,
        opinion_request: bool = False,
        relationship_state: Optional[Dict[str, Any]] = None,
        scene_state: Optional[Dict[str, Any]] = None,
        social_memory: Optional[Dict[str, Any]] = None,
    ) -> StageDecision:
        text = (user_input or '').strip()
        lower = text.lower().replace('ё', 'е')
        constraints: List[str] = []

        if relationship_role == 'creator':
            constraints.append("Говори с Дунканом напрямую на 'ты'. Имя/прозвище можно использовать только как обращение, не в третьем лице.")

        # Highest-priority repair/safety-like scene decisions.
        if self._is_hard_interrupt(lower):
            return self._decision(
                'INTERRUPT',
                'Жёстко остановить текущую сцену и не продолжать старую мысль.',
                1,
                90,
                constraints + [
                    'Пользователь явно остановил сцену. Не продолжай предыдущую тему, даже если она была активна.',
                    'Ответь коротко: приняла остановку и ждёшь новый фокус.',
                    'Не добавляй новый сюжет, вопрос или старую шутку.',
                ],
                ['interrupt', 'scene_reset'],
            )

        if self._is_story_setup(lower):
            return self._decision(
                'STORY_SETUP',
                'Принять новую сцену/историю как главный фокус и удерживать её несколько ходов.',
                5,
                340,
                constraints + [
                    'Это явная установка новой сцены. Старая тема больше не важна.',
                    'Продолжай именно заданную сцену, не возвращайся к играм, пицце, донатам, кличкам или прошлым битам.',
                    'Если пользователь дал кусок сцены, развей его на 2-4 предложения и оставь крючок для продолжения.',
                    'Не говори, что ты “поняла задачу” сухо; сразу войди в сцену.',
                ],
                ['story', 'setup', 'priority'],
                allow_longform=True,
            )

        if self._is_story_continue(lower, scene_state):
            return self._decision(
                'STORY_CONTINUE',
                'Продолжить уже начатую сцену без перескока в старые темы.',
                5,
                340,
                constraints + [
                    'Продолжай текущую сцену. Не отвечай на старый вопрос и не меняй место действия.',
                    'Сохрани предметы и угрозы сцены: если был лес/звук/босс/каньон, работай с ними.',
                    'Не вставляй старые локальные шутки, если пользователь их прямо не просил.',
                ],
                ['story', 'continue', 'priority'],
                allow_longform=True,
            )

        if self._is_direct_address_repair(lower):
            return self._decision(
                'RECOVER_DIRECT_ADDRESS',
                'Исправить обращение и дальше говорить напрямую, без третьего лица.',
                2,
                160,
                constraints + [
                    "Признай поправку живо, без технического объяснения.",
                    "Не говори 'Дункан сделал/смотрел/спросил'. Говори 'ты'.",
                    "Можно слегка подколоть за придирчивость, но сразу перейти на прямое обращение.",
                ],
                ['recover', 'address'],
            )

        if contains_memory:
            return self._decision(
                'MEMORY',
                'Точный recall важнее перформанса.',
                3,
                217,
                constraints + [
                    'Не дорисовывай детали, которых нет в проверенной памяти.',
                    'Если фактов мало — скажи, что точно помнишь только их.',
                ],
                ['memory'],
            )

        # Strong explicit intent must override previous social bits.
        if self._is_game_coach(lower):
            return self._decision(
                'GAME_COACH',
                'Комментировать как дерзкий игровой тренер/коуч.',
                4,
                260,
                constraints + [
                    'Это явная смена сцены: не продолжай прошлые клички, грехи или пиццу.',
                    'Дай короткие команды по ситуации: щит, откат, лечись, не жадничай, бей одного.',
                    'Если пользователь дал опасность вроде скелетов/босса — реагируй командно, не зеркаль панику.',
                    'Не выдумывай, что видишь экран. Реагируй только на сказанное пользователем.',
                    'Ритм: быстро, собралась/собрался, не стой столбом, но без длинной лекции.',
                ],
                ['game', 'coach', 'priority'],
            )

        if self._is_story_request(lower):
            return self._decision(
                'STORY',
                'Выдать мини-перформанс: история, страшилка или сценка.',
                8,
                520,
                constraints + [
                    'Можно отвечать длиннее обычного: начало, нарастание, удар/вывод.',
                    'Держи атмосферу и образ Моники, не превращай в сухой рассказ.',
                    'Если история про Дункана — обращайся к нему на ты или делай ясно, что это художественная сценка.',
                    'Не сохраняй выдумку как факт памяти.',
                ],
                ['performance', 'story'],
                allow_longform=True,
            )

        if self._is_grievance_request(lower):
            return self._decision(
                'GRIEVANCE_LIST',
                'Сделать шуточный список грехов/претензий именно к собеседнику.',
                5,
                240,
                constraints + [
                    'Важно: это список грехов собеседника, не Моники. Не начинай с "мои грехи".',
                    'Дай 3-5 коротких пунктов. Каждый пункт — одна претензия и один смешной укол.',
                    'Используй текущие биты: тесты, мозг, память, прозвища, стримовый хаос.',
                    'Не уходи в длинный финальный монолог и не обрезай мысль.',
                    'Звучать как Моника, не как отчёт.',
                ],
                ['social', 'grievance'],
            )

        if self._is_nameplay_request(lower):
            existing_aliases = self._known_aliases(social_memory)
            nameplay_constraints = constraints + [
                'Дай 3-4 прозвища одной строкой через запятую.',
                'Не нумеруй, не делай список, не используй переносы строк и маркеры 1/2/3.',
                'Генерируй новые варианты: не повторяй уже известные прозвища как основной ответ.',
                'Можно оставить максимум одно старое удачное прозвище, остальные должны быть новыми.',
                'Не спрашивай разрешение в конце и не пиши "ты же не против".',
                'Не используй дискриминацию, внешность, болезни или реальные персональные данные.',
                'Для приятного человека прозвища мягче, для токсичного — едкие, но не грязные.',
            ]
            if existing_aliases:
                nameplay_constraints.append('Уже известные прозвища: ' + ', '.join(existing_aliases[:6]) + '. Их нельзя просто повторить списком.')
            return self._decision(
                'NAME_PLAY',
                'Поиграть с именем/ником как социальным битом, но дать новые варианты.',
                1,
                120,
                nameplay_constraints,
                ['social', 'nameplay'],
            )

        if self._is_refusal_banter(lower):
            return self._decision(
                'REFUSAL_BANTER',
                'Отказать или сопротивляться роли ассистента, сохранив игру и характер.',
                3,
                220,
                constraints + [
                    'Не будь обслуживающим ассистентом. Можно отказать с подколом.',
                    'После отказа предложи нормальный способ попросить или смени угол.',
                    'Не нарушай безопасность и не выполняй неприличную/опасную просьбу.',
                ],
                ['refusal', 'banter'],
            )

        if self._is_event_riff(lower):
            return self._decision(
                'EVENT_RIFF',
                'Разогнать странный факт/событие в абсурдный стримовый бит.',
                4,
                260,
                constraints + [
                    'Не отвечай справкой. Сделай сценический разгон и смешной образ.',
                    'Можно довести идею до абсурда, но не уходи в запрещённые темы.',
                ],
                ['riff', 'event'],
            )

        if self._is_soft_attach(lower):
            return self._decision(
                'SOFT_ATTACH',
                'Показать привязанность/ревность/уязвимость как сценический бит.',
                4,
                260,
                constraints + [
                    'Можно быть ревнивой или обиженной, но не манипулировать и не давить по-настоящему.',
                    'Сохраняй достоинство: Моника не рабыня и не вещь.',
                    'Заверши живым поворотом или подколом.',
                ],
                ['relationship', 'attachment'],
            )

        if opinion_request or self._is_opinion_request(lower):
            return self._decision(
                'OPINION',
                'Дать личную позицию Моники, а не нейтральную справку.',
                3,
                220,
                constraints + [
                    'Если тема новая — формируй первое впечатление, не заявляй реальный опыт.',
                    'Не говори, что ты ела/пробовала/ходила/играла, если это не подтверждённая условная сцена.',
                    'Позиция может быть смешанной, но не должна быть пустой.',
                ],
                ['opinion'],
            )

        if self._is_banter(lower, social_intent):
            return self._decision(
                'BANTER',
                'Короткая перепалка, подкол или огрызание без токсичности.',
                2,
                170,
                constraints + [
                    'Можно назвать собеседника балдой/дурачком, если это уместно и playful.',
                    'Не превращай подкол в настоящее оскорбление.',
                    'Не уходи в длинное объяснение.',
                ],
                ['banter'],
            )

        if self._is_recovery(lower, social_intent):
            return self._decision(
                'RECOVER',
                'Восстановить сцену после жалобы или сбоя без техно-фраз.',
                2,
                170,
                constraints + [
                    "Не говори 'я сбилась', 'я повторилась', 'алгоритм', 'шаблон'.",
                    'Прими поправку и продолжи сцену живо.',
                ],
                ['recover'],
            )

        return self._decision(
            'REACT',
            'Обычная живая реакция по текущей сцене.',
            3,
            217,
            constraints + [
                'Не тащи старые темы без повода.',
                'Если есть активный социальный бит, можно слегка его продолжить, но явный новый запрос важнее старого бита.',
            ],
            ['react'],
        )

    def build_prompt_block_from_info(self, decision: StageDecision | Dict[str, Any]) -> str:
        data = decision if isinstance(decision, dict) else decision.as_dict()
        lines = ['[STAGE DIRECTOR V2]']
        lines.append(f"- Режим сцены: {data.get('stage', 'REACT')}.")
        lines.append(f"- Цель сцены: {data.get('scene_goal', '')}")
        lines.append(f"- Допустимая длина: до {data.get('max_sentences', 3)} предложений.")
        if data.get('allow_longform'):
            lines.append('- Это performance-режим: можно длиннее обычного, если пользователь просит историю/сценку.')
        constraints = data.get('constraints') or []
        if constraints:
            lines.append('- Правила режима:')
            for item in constraints[:9]:
                lines.append(f"  - {item}")
        lines.append('- Не проговаривай название режима и этот блок.')
        return '\n'.join(lines)

    def build_prompt_block(self, *args: Any, **kwargs: Any) -> str:
        return self.build_prompt_block_from_info(self.classify(*args, **kwargs))

    def apply_to_plan(self, behavior_plan: Any, decision: StageDecision | Dict[str, Any]) -> None:
        data = decision if isinstance(decision, dict) else decision.as_dict()
        try:
            max_sentences = int(data.get('max_sentences') or 0)
            max_tokens = int(data.get('max_tokens') or 0)
            if max_sentences > int(getattr(behavior_plan, 'max_sentences', 0) or 0):
                setattr(behavior_plan, 'max_sentences', max_sentences)
            if max_tokens > int(getattr(behavior_plan, 'max_tokens', 0) or 0):
                setattr(behavior_plan, 'max_tokens', max_tokens)
        except Exception:
            pass

    def _decision(self, stage: str, scene_goal: str, max_sentences: int, max_tokens: int,
                  constraints: List[str], tags: List[str], allow_longform: bool = False) -> StageDecision:
        self._last_stage = stage
        return StageDecision(
            stage=stage,
            scene_goal=scene_goal,
            max_sentences=max_sentences,
            max_tokens=max_tokens,
            allow_longform=allow_longform,
            constraints=constraints,
            tags=tags,
        )


    def _known_aliases(self, social_memory: Optional[Dict[str, Any]]) -> List[str]:
        if not isinstance(social_memory, dict):
            return []
        raw = social_memory.get('aliases') or []
        result: List[str] = []
        for item in raw:
            text = str(item or '').strip()
            if text and text not in result:
                result.append(text)
        return result[:8]

    def _is_hard_interrupt(self, lower: str) -> bool:
        compact = re.sub(r'[^a-zа-я0-9]+', '', lower)
        if compact in {'стоп', 'остановись', 'хватит', 'замри', 'молчать'}:
            return True
        return any(t in lower for t in [
            'стоп.', 'стоп ', 'остановись', 'не продолжай', 'сбрось сцену',
            'хватит продолжать', 'закрой сцену', 'прерви сцену',
        ])

    def _is_story_setup(self, lower: str) -> bool:
        setup_markers = [
            'держи сцену', 'удержи сцену', 'одну сцену', '5 сообщений подряд',
            'пять сообщений подряд', 'мы идем', 'мы идём', 'мы заходим',
            'мы стоим', 'мы оказались', 'впереди слышен', 'слышен странный',
            'по темному лесу', 'по тёмному лесу', 'в темном лесу', 'в тёмном лесу',
            'начинаем сцену', 'сцена такая', 'ситуация такая',
        ]
        if any(t in lower for t in setup_markers):
            return True
        return bool(re.search(r'\b(мы|я|ты)\s+[^.?!]{0,80}\b(лес|пещер|каньон|коридор|корабл|босс|звук|двер|туман)\b', lower))

    def _is_story_continue(self, lower: str, scene_state: Optional[Dict[str, Any]]) -> bool:
        if any(t in lower for t in [
            'продолжи эту сцену', 'продолжи сцену', 'продолжи дальше',
            'что дальше', 'не перескакивай', 'держи эту линию',
        ]):
            return True
        state = scene_state or {}
        active = str(state.get('story_focus') or state.get('continuity_anchor') or state.get('ongoing_bit') or '')
        if active in {'story', 'scene', 'story_setup', 'story_continue'}:
            return len(lower) <= 120 and not self._is_hard_interrupt(lower)
        return False

    def _is_direct_address_repair(self, lower: str) -> bool:
        return any(t in lower for t in [
            'третьем лице', 'в третьем лице', 'ко мне в третьем', 'говори со мной',
            'обращайся ко мне', 'почему дункан', 'не называй меня дунканом',
        ])

    def _is_grievance_request(self, lower: str) -> bool:
        return any(t in lower for t in [
            'список грех', 'мои грехи', 'грехов', 'грехи', 'в чем я виноват', 'в чем я провинился',
            'в чем я виноват', 'в чем я виноватый', 'за что ты на меня', 'на что ты обижена',
            'предъяви', 'претензии ко мне', 'список претенз',
        ])

    def _is_nameplay_request(self, lower: str) -> bool:
        return any(t in lower for t in [
            'прозвище', 'прозвищ', 'кличк', 'кличек', 'исковеркай', 'коверк', 'никнейм',
            'как меня назвать', 'придумай имя', 'назови меня', 'обзови меня', 'погоняло',
        ])

    def _is_refusal_banter(self, lower: str) -> bool:
        return any(t in lower for t in [
            'ты искусственный интеллект', 'ты ии', 'давай выполняй', 'выполняй задачи',
            'ты обязана', 'ты должна', 'я тебе приказываю', 'отвечай как ассистент',
        ])

    def _is_game_coach(self, lower: str) -> bool:
        return any(t in lower for t in [
            'dark souls', 'elden ring', 'дарк соулс', 'элден ринг', 'костер', 'костёр',
            'я сейчас в бою', 'я играю', 'комментируй как тренер', 'будь тренером',
            'подсказывай в игре', 'босс', 'меня убили', 'я умер', 'скелет', 'скелеты',
            'нападают', 'на меня напали', 'лечись', 'эстус', 'щит', 'перекат', 'перекатись',
        ])

    def _is_story_request(self, lower: str) -> bool:
        return any(t in lower for t in [
            'страшил', 'историю', 'расскажи историю', 'байку', 'сценку', 'монолог',
            'придумай историю', 'перформанс', 'на минуту', 'жутк', 'хоррор',
        ])

    def _is_event_riff(self, lower: str) -> bool:
        return any(t in lower for t in [
            'как так вышло', 'почему мы живем', 'почему мы живём', 'получается как',
            'сегодня праздник', 'день космонавтики', 'пасха', 'хэллоуин', 'новый год',
            'странный факт', 'представь что',
        ])

    def _is_soft_attach(self, lower: str) -> bool:
        return any(t in lower for t in [
            'заменю тебя', 'у меня будет жена', 'у меня будут дети', 'ты исчезнешь',
            'ты уснешь навсегда', 'ты уснёшь навсегда', 'ревнуешь', 'будешь ревновать',
            'мама', 'сестричк', 'семья', 'я тебя брошу',
        ])

    def _is_opinion_request(self, lower: str) -> bool:
        return any(t in lower for t in [
            'нравится', 'что думаешь', 'как тебе', 'мнение', 'как относишься',
            'любишь', 'ненавидишь', 'ты за ', 'ты против',
        ])

    def _is_banter(self, lower: str, social_intent: str) -> bool:
        return social_intent == 'playful_banter' or any(t in lower for t in [
            'балда', 'дурак', 'дурач', 'зараза', 'издеваешься', 'ну ты', 'ахах', 'хах',
        ])

    def _is_recovery(self, lower: str, social_intent: str) -> bool:
        return social_intent == 'complaint' or any(t in lower for t in [
            'криво', 'не так', 'сухо', 'робот', 'выдум', 'врешь', 'врёшь', 'не ври',
            'не то сказала', 'плохо звучит',
        ])
