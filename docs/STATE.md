# Состояние проекта — 2026-10-28

Этот файл — краткая память проекта между чатами и агентами.
Читать перед началом любой задачи.

## 1. Машина и цель

- Mac mini M1, arm64, **8 ГБ RAM**, **96 ГБ свободно**, macOS 27.0.1.
- Проект — бэкап с Windows, 5,4 ГБ.
- Python, Homebrew и зависимости пока не установлены.
- Цель: запустить Монику на macOS **без локальной LLM**, через
  OpenAI-совместимый облачный API.

## 2. Принятые решения

1. **Локальную Qwen3-14B не используем.** На 8 ГБ RAM она не помещается.
   LLM — облачная, через `LLM_API_BASE` / `LLM_MODEL_NAME` / `LLM_API_KEY`.
2. **Streamer.bot и Speaker.bot нативно на macOS не запускаем.**
   Это Windows-приложения. Для старта достаточно консоли, TTS, аватара и Telegram.
   Twitch-интеграцию решаем позже: нативный Python-мост или отдельная Windows-машина.
3. **Сначала стабилизация, потом фичи.** Новые когнитивные слои не добавляем.
4. **Одна задача — один чат/бранч.** Параллельные кодеры — только после
   разбиения `console_chat.py` и появления тестового harness.
5. **Тесты не трогают реальную память.** Нужен `MONIKA_DATA_DIR`, temp DB,
   fake LLM и `--dry-run`.

## 3. Факты о проекте

- 102 Python-файла, 24 741 строка.
- `console_chat.py` — 4914 строк, `process_input` — ~1700 строк.
- `monika_text_runtime.py` — второй runtime для Telegram, 1246 строк.
- 73 `CREATE TABLE` в 21 файле.
- 15 мест с `chat.completions.create`.
- 5 файлов с тестами/проверками.
- `knowledge.db`: 4243 сообщения.
- `monika_memory.db`: 15 сущностей, 29 фактов.
- ChromaDB: 34 документа.
- TTS: 86 WAV / 67 МБ, файлы не удаляются.
- В проекте есть Windows-venv (2,3 ГБ), ChatTTS-ассеты (1,1 ГБ),
  vosk-модель (948 МБ) — кодом не используются.

## 4. Что уже сделано в этом чате

- Проведён анализ проекта и архитектуры.
- Определены блокеры macOS и варианты запуска без локальной LLM.
- Создан `.gitignore`.
- Создан `AGENTS.md`.
- Созданы `docs/ARCHITECTURE.md` и `docs/STATE.md`.
- Созданы task cards:
  - `docs/tasks/001-macos-port.md`
  - `docs/tasks/002-test-harness.md`
  - `docs/tasks/003-turn-pipeline.md`
- Инициализирован git, создан baseline-коммит `3b85a46`.
- `MonikaBrain/webviewer/pixi-live2d-display/` оставлен на диске, но не в git
  (это вложенный сторонний репозиторий с node_modules). Для работы viewer
  он должен оставаться на месте.

## 5. Следующие задачи по порядку

1. **001 — Mac port.** Пути, конфиг, requirements, start script.
2. **002 — Test harness.** Temp DB, fake LLM, smoke, golden-диалоги.
3. **003 — Turn pipeline.** Вынести `process_input` в этапы.
4. **004 — Single runtime.** Консоль и Telegram через один engine.
5. **005 — Memory cleanup.** Один opinion-модуль, реальная индексация или отказ от Chroma.
6. **006 — TTS/STT cleanup.** Без temp-файлов, lazy init, убрать мёртвый STT.
7. **007 — Agent tools.** ToolRegistry + bounded loop + permissions.

## 6. Открытые вопросы

- Какой LLM-провайдер: OpenRouter, OpenAI, DeepSeek, Gemini, Yandex?
- Нужен ли Twitch/Streamer.bot в первой версии?
- Нужен ли голосовой ввод (F10) или пока только текст?
- Оставлять ли ChatTTS-ассеты для будущего или удалить?
- Нужна ли отдельная Windows-VM для Streamer.bot/Speaker.bot?

## 7. Безопасность

- Git baseline уже создан: `3b85a46`.
- Перед каждой задачей: отдельный бранч `bionic/<task>`.
- Реальные БД: `MonikaBrain/knowledge.db`, `monika_memory.db`,
  `MonikaBrain/chroma_engram/` — не коммитить, не перезаписывать в тестах.
- Токен Telegram лежит в `config.py` открытым текстом. Если бэкап куда-то
  передавался — перевыпустить через BotFather.
- `.env` в проекте не читается: `python-dotenv` не подключён.

## 8. Handoff для нового чата

```text
Прочитай AGENTS.md, docs/STATE.md и docs/tasks/<номер>.md.
Работай только в рамках task card.
Не запускай полный чат с реальной knowledge.db.
Сначала покажи план, потом правь код.
```
