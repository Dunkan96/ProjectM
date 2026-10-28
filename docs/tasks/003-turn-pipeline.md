# Task 003 — Вынести process_input в TurnPipeline

## Цель

Разбить `MonikaConsoleChat.process_input` (~1700 строк) на этапы
без изменения поведения. Убрать `locals()`-магию и сделать ход
тестируемым по частям.

Это задача архитектора + одного кодера. Параллельные кодеры
в `console_chat.py` запрещены.

## Предусловия

- Task 002 выполнен: есть fake LLM и temp DB.
- Есть golden-диалоги, по которым можно сравнивать поведение.
- Архитектор согласовал `TurnContext` / `TurnPlan` / `TurnResult`.

## Разрешённые файлы

- Новые:
  - `MonikaBrain/turn_pipeline.py`
  - `MonikaBrain/turn_contracts.py`
  - `MonikaBrain/tests/test_turn_pipeline.py`
- `MonikaBrain/console_chat.py` — только:
  - вызов нового pipeline из `process_input`;
  - удаление перенесённых участков;
  - точечные импорты.

## Запрещено

- Менять промпты и поведенческие правила.
- Менять схему БД.
- Добавлять новые когнитивные слои.
- Переписывать `behavior_director` / `stage_director` / `emotion_director`.
- Менять TTS/аватар.

## Этапы pipeline

```text
1. normalize          # mojibake, ё→е, обрезка
2. safety             # boundary consent, stream safety
3. route              # stream command / special request
4. cognitive_state    # сборка состояния
5. plan               # behavior + stage + emotion + response policy
6. prompt             # сборка system prompt и контекста
7. llm                # вызов через LLMGateway
8. validate           # answer_evaluator, repetition, postguard
9. output             # TTS, аватар, история
10. memory            # запись через MemoryPolicy
```

Каждый этап:

- получает `TurnContext`;
- возвращает `TurnContext` или результат этапа;
- не читает `locals()`;
- не ходит в глобальные переменные;
- логирует вход/выход в `debug_trace`.

## Контракты

```python
@dataclass
class TurnContext:
    turn_id: str
    user_text: str
    source: str
    person_id: str
    role: str
    history: list[dict]
    scene_state: dict
    memory_facts: list[str]
    plan: TurnPlan | None = None
    ...

@dataclass
class TurnPlan:
    mode: str
    max_sentences: int
    max_tokens: int
    temperature: float
    use_memory: bool
    constraints: list[str]
    ...

@dataclass
class TurnResult:
    reply: str
    emotion: str
    tts_allowed: bool
    memory_write: dict | None
    debug: dict
```

## Порядок работы

1. Архитектор фиксирует список этапов и поля `TurnContext`.
2. Кодер переносит **один** этап за коммит.
3. После каждого этапа — запуск golden-тестов.
4. Если поведение изменилось — откат этапа, а не подгонка тестов.
5. В конце — `process_input` становится тонкой обёрткой:

```python
def process_input(self, stimulus):
    ctx = TurnContext.from_stimulus(stimulus, self)
    ctx = self.turn_pipeline.run(ctx)
    self.apply_result(ctx)
```

## Критерии приёмки

- `process_input` меньше 100 строк.
- В `console_chat.py` не осталось `locals()` в основном пути.
- Golden-тесты проходят.
- Один ход с fake LLM даёт тот же `TurnPlan`, что и до рефакторинга
  (сравнение по ключевым полям, не по тексту).
- Нет изменений в `knowledge.db` при тестах.

## Отчёт

```text
Task: 003-turn-pipeline
Changed: ...
Checks: pytest -q — N passed; golden — N passed
Not done: ...
Risks: ...
```

## Вне scope

- Единый runtime для Telegram (`monika_text_runtime`).
- Замена ChromaDB.
- Агентные инструменты.
