# Архитектура Monika / ProjectM

## 1. Кратко

Моника — локальный AI-VTuber: Python-бэкенд + браузерный Live2D-аватар.
Идея архитектуры — многослойная когнитивная система:

```text
стимул → безопасность → внимание → когнитивное состояние → поведение
→ промпт → LLM → пост-валидация → TTS/аватар → запись в память
```

Концепция сильная, но реализация монолитная: `console_chat.py` — около
4900 строк, `process_input` — около 1700 строк, 130 методов, 75 обращений
к `locals()`. Это главный технический долг.

## 2. Компоненты

### Точки входа

| Файл | Назначение |
|---|---|
| `MonikaBrain/console_chat.py` | основной runtime: консоль, память, TTS, WebSocket аватара |
| `MonikaBrain/monika_text_runtime.py` | второй runtime для Telegram |
| `MonikaBrain/telegram_bot.py` | Telegram-адаптер |
| `MonikaBrain/streamerbot_attention_bridge.py` | отдельный мост к Streamer.bot (Windows-only) |
| `MonikaBrain/webviewer/viewer.html` | Live2D-аватар, WebSocket `ws://localhost:8080` |

### Память

- `monika_memory.db` — граф знаний: `entities`, `facts`.
- `knowledge.db` — оперативная память: `chat_history`, отношения, желания,
  мнения, эмоциональные события, сессии, рефлексия.
- `chroma_engram/` — ChromaDB, коллекция `dialogue_memory`.
- Эмбеддинги: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.

Фактическое наполнение на момент анализа:

- 4243 сообщения в `chat_history`;
- 34 документа в ChromaDB;
- 15 сущностей и 29 фактов в графе.

То есть векторная память почти не используется, а граф маленький.
Семантический поиск включается только по ключевым словам вроде «помнишь».

### Поведение и когнитивные слои

- `persona.py` — личность, стиль, запреты.
- `behavior_director.py` — режим, длина, тон, микро-желания.
- `stage_director.py` — стадия сцены (чат, история, прерывание).
- `emotion_director.py` — эмоция и эмоциональная арка.
- `response_policy.py` — режим ответа и лимиты.
- `turn_orchestrator.py` — контракт хода.
- `cognitive_state_compiler.py` — сборка когнитивного состояния.
- `attention_*` — внимание, приоритеты, safety.
- `memory_core.py`, `social_layer.py`, `social_memory.py`,
  `desire_memory.py`, `opinion_memory.py`, `opinion_core.py`,
  `emotional_memory.py`, `monika_self_state.py`, `reflection_curator.py`.

Проблема: шесть слоёв по очереди меняют `behavior_plan` / ограничения ответа.
Порядок вызовов определяет результат, единого владельца итогового плана нет.

### Интеграции

- LLM: OpenAI-совместимый API, сейчас `http://localhost:1234/v1`.
- TTS: Silero v5 (`torch.hub`), голос `kseniya`, 48 кГц.
- STT: `faster-whisper` + `keyboard` (F10), но `STT_PTT` нигде не создаётся.
- Аватар: WebSocket-сервер в отдельном потоке, порт 8080.
- Telegram: `aiogram`.
- Twitch/Streamer.bot: только через Windows-мост.

## 3. Главные проблемы

### P0 — reliability

1. **Монолит `console_chat.py`.** 4900 строк, `process_input` ~1700 строк,
   75 `locals()`. В `crash_log.txt` уже есть `UnboundLocalError` из-за этого.
2. **Два разных runtime.** `console_chat` и `monika_text_runtime` дублируют
   `_controlled_reply`, `_strip_false_memory_claims`, сборку промпта и
   используют разные opinion-модули (`opinion_memory` vs `opinion_core`).
3. **Несколько процессов пишут в одну память.** Консоль, Telegram и
   Streamer.bot bridge могут одновременно открывать `knowledge.db` и ChromaDB.
   SQLite WAL не спасает от нескольких писателей; Chroma multi-process хрупкая.
4. **Нет таймаутов и ретраев LLM.** 15 мест с `chat.completions.create`,
   клиент создаётся без `timeout`/`max_retries`.
5. **TTS течёт.** WAV пишется в `TTS/`, читается обратно и не удаляется.
   Уже 86 файлов / 67 МБ. TTS грузится на старте, даже если не нужен.
6. **Память почти мертва.** 34 документа Chroma на 4243 сообщения;
   `_extract_and_save_facts_async` нигде не вызывается.
7. **STT не работает.** `STT_PTT` не создаётся, но консоль пишет «Зажмите F10».
8. **Промпт раздут и противоречив.** 15+ блоков, до 16 тыс. символов;
   `PromptBudgetManager` режет только сообщение пользователя, не system prompt.
   `[QWEN OUTPUT RULE]` зашит для всех моделей.

### P1 — maintainability

9. **73 `CREATE TABLE` в 21 файле.** `StateMigration` только пишет версию,
   реальных миграций нет.
10. **Нет зависимостей и CI.** Нет `requirements.txt`/`pyproject.toml`;
    5 файлов тестов на 24,7 тыс. строк; `run_tests.bat` запускает чат.
11. **Мёртвый код и мусор.** `builder_бэкап без кеша.py` (644 строки),
    `opinion_core (1).py`, `$body`, `.pyc`, `.lnk`.
12. **Логи без ротации.** Новый файл на запуск, 12 МБ за несколько дней.
13. **Секреты в коде.** Токен Telegram в `config.py`.
14. **Два экземпляра SentenceTransformer.** `Builder` и `GraphEngine`
    каждый грузят модель — лишние ~470 МБ на 8 ГБ RAM.

## 4. Целевая архитектура

```text
monika/
  app/
    cli.py            # консоль
    telegram.py       # Telegram-адаптер
    twitch.py         # Twitch/EventSub (позже)
  core/
    engine.py         # оркестратор хода
    turn_pipeline.py  # этапы обработки
    contracts.py      # TurnContext, TurnPlan, TurnResult
  cognition/
    attention.py
    behavior.py
    stage.py
    emotion.py
    policy.py
  memory/
    schema.py
    migrations/
    repositories.py
    vector.py
  integrations/
    llm.py            # timeout, retry, streaming, token accounting
    tts.py            # Silero, без temp-файлов, lazy init
    stt.py
    avatar_ws.py
    twitch.py
    obs.py
  config.py
tests/
  fixtures/
  golden/
  test_pipeline.py
```

Правила:

- Один `TurnContext` проходит по этапам; каждый этап возвращает новый state.
- Один `PromptBuilder` собирает секции с приоритетами и жёстким лимитом токенов.
- Один `ResponseValidator` вместо шести чистящих слоёв.
- Один `LLMGateway` с таймаутом, ретраями и логом токенов.
- Один `MemoryRepository`; схема и миграции — в одном месте.
- Адаптеры (консоль, Telegram, Twitch) не знают, как устроен «мозг».

## 5. Агенты

Текущий tool calling: три read-only инструмента (`get_wiki_info`,
`get_timeline_info`, `get_person_info`), один вызов и один follow-up.
Нет реестра инструментов, лимита шагов, прав и аудита.

Целевой минимум:

```text
agent/
  tools.py       # ToolRegistry + JSON-схемы
  runner.py      # цикл до 2-3 шагов
  policies.py    # права, rate limit, audit
```

Read-only инструменты — первыми. Мутирующие (память, OBS, Twitch, TTS) —
только через политику и аудит. Ролевой чат и «оператор стрима» не смешивать.

## 6. Что не делать

- Не переписывать всё сразу.
- Не запускать параллельных кодеров в `console_chat.py`.
- Не добавлять LangGraph/CrewAI поверх текущих слоёв.
- Не тестировать на реальной `knowledge.db`.
- Не коммитить модели, venv, WAV и БД.
