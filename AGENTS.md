# AGENTS.md — Monika / ProjectM

Этот файл читают все агенты и разработчики **до** любых изменений.
Цель проекта: перенести AI-VTuber «Монику» с Windows на macOS и постепенно
упростить архитектуру без потери личности, памяти и поведения.

## 1. Что это за проект

- `MonikaBrain/` — Python-бэкенд: память, поведение, эмоции, внимание, TTS,
  Telegram, WebSocket для Live2D-аватара.
- `MonikaBrain/webviewer/` — браузерный Live2D-аватар (`viewer.html`).
- `TTS/` — временные WAV и неиспользуемые ChatTTS-ассеты.
- `Streamer.bot/`, `Speaker.bot/` — Windows-only приложения. На macOS не запускаются.
- `STT/` — тестовые аудиофайлы.

Главная точка входа: `MonikaBrain/console_chat.py`.
Второй runtime: `MonikaBrain/monika_text_runtime.py` (Telegram).
Подробная карта — `docs/ARCHITECTURE.md`.
Текущее состояние и решения — `docs/STATE.md`.

## 2. Текущий статус

- Проект — бэкап с Windows. На macOS ещё не запускался.
- Python, Homebrew и зависимости на Mac mini M1 пока не установлены.
- Локальная LLM не используется: планируется OpenAI-совместимый облачный API.
- В проекте есть Windows-пути `F:\...`, `.bat`-файлы и Windows-venv.
- Реальная память: `MonikaBrain/knowledge.db`, `MonikaBrain/monika_memory.db`,
  `MonikaBrain/chroma_engram/`.

## 3. Железные правила

1. **Не писать в реальную память во время тестов.**
   Использовать `MONIKA_DATA_DIR` и временную копию БД. Если изоляции ещё нет —
   не запускать `MonikaConsoleChat`, `Builder`, `telegram_bot` и скрипты,
   которые открывают `knowledge.db` / `chroma_engram`.
2. **Одна задача — один бранч.**
   Не смешивать Mac port, рефакторинг и новые фичи в одном diff.
3. **Не добавлять новые когнитивные слои.**
   Сначала использовать существующие: `behavior_director`, `stage_director`,
   `emotion_director`, `response_policy`, `turn_orchestrator`.
   Новый слой — только через ADR в `docs/adr/`.
4. **Не раздувать `console_chat.py`.**
   Файл уже ~4900 строк. Новый код — в отдельный модуль, затем тонкий вызов.
5. **Не удалять файлы и БД без явного разрешения.**
   Особенно `*.db`, `chroma_engram/`, `TTS/voice_refs/`.
6. **Секреты — только в env.**
   Никаких токенов в `config.py`, логах и коммитах.
7. **Не коммитить большие файлы.**
   Модели, venv, WAV, `node_modules`, БД — в `.gitignore`.
8. **Перед сдачей — проверка.**
   Импорты, линтер, тесты, smoke. Если тестов ещё нет — явно написать, что проверено.

## 4. Рабочий цикл агента

1. Прочитать `AGENTS.md`, `docs/STATE.md`, свою task card из `docs/tasks/`.
2. Проверить `git status` и текущую ветку.
3. Работать только в файлах, разрешённых task card.
4. Запустить проверки из task card.
5. Отчитаться:
   - что изменено;
   - какие файлы затронуты;
   - что проверено и чем;
   - что осталось вне scope.

Шаблон отчёта:

```text
Task: 001-macos-port
Changed: MonikaBrain/config.py, MonikaBrain/requirements.txt
Checks: python -c "import config" — ok; grep F:\\ — 0 matches
Not done: TTS refactor (out of scope)
Risks: model download needs internet on first run
```

## 5. Команды (после установки окружения)

```bash
cd MonikaBrain
source .venv/bin/activate

python -c "import config, builder, graph_engine"
pytest -q
ruff check .
python console_chat.py --help
```

Запуск аватара:

```bash
cd MonikaBrain/webviewer
python -m http.server 3000
# браузер: http://localhost:3000/viewer.html
```

## 6. Handoff в новый чат

Новый чат не помнит этот диалог. Перед началом работы дать ему:

```text
Прочитай AGENTS.md, docs/STATE.md и docs/tasks/<номер>.md.
Работай только в рамках task card.
Не запускай полный чат с реальной knowledge.db.
Сначала покажи план, потом правь код.
```

## 7. Приоритеты

1. Безопасный перенос на macOS и облачная LLM.
2. Тестовая изоляция и harness.
3. Разбиение `process_input` на этапы.
4. Единый runtime для консоли и Telegram.
5. Память, TTS, агентные инструменты — после стабилизации.
