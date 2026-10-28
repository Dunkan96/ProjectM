# Task 001 — Mac port: пути, конфиг, запуск

## Цель

Сделать проект запускаемым на macOS без локальной LLM:
убрать Windows-пути, вынести LLM-настройки в env, добавить зависимости
и shell-запуск. Поведение Моники не менять.

## Предусловия

- Homebrew, Python 3.12, `portaudio`, `git` установлены.
- Создан `.venv`, установлены зависимости из `requirements.txt`.
- Есть облачный OpenAI-совместимый endpoint и API-ключ.

## Разрешённые файлы

- `MonikaBrain/config.py`
- `MonikaBrain/builder.py`
- `MonikaBrain/graph_engine.py`
- `MonikaBrain/console_chat.py` — **только**:
  - инициализация `OpenAI` (ключ, timeout, retries);
  - защита импорта `stt_ptt`, чтобы `keyboard` не валил запуск на macOS.
- `MonikaBrain/monika_text_runtime.py` — только инициализация `OpenAI`.
- `MonikaBrain/stt_ptt.py` — только безопасный импорт/инициализация.
- Новые файлы:
  - `MonikaBrain/requirements.txt`
  - `MonikaBrain/.env.example`
  - `MonikaBrain/start_monika.sh`

## Запрещено

- Менять схему БД.
- Трогать `process_input`, когнитивные слои, промпты.
- Удалять модели, БД, `TTS/voice_refs/`.
- Коммитить `.env`, `*.db`, `chroma_engram/`, venv, модели.
- Запускать полный чат с реальной `knowledge.db`.

## Что сделать

### 1. Пути

`config.py`:

- `BASE_DIR` — от `Path(__file__).resolve().parent.parent` (корень `ProjectM`).
- `BRAIN_DIR` — папка `MonikaBrain`.
- `DB_PATH` — `BRAIN_DIR / "monika_memory.db"`.
- `TTS_CACHE_DIR` — `BASE_DIR / "TTS"`.
- `STT_TEMP_DIR` — `BASE_DIR / "STT"`.
- Разрешить override через `MONIKA_DATA_DIR` (для тестов).
- Убрать `F:\...` полностью.

`builder.py`:

- `SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")`
  вместо виндового snapshot-пути.
- Chroma: `PersistentClient(path=str(BRAIN_DIR / "chroma_engram"))`,
  а не `./chroma_engram`.
- Желательно переиспользовать один encoder с `GraphEngine`
  (если это не меняет поведения; иначе — отдельной задачей).

`graph_engine.py`:

- Убрать `MODEL_PATH = r"F:\..."`.
- Использовать то же имя HF-модели или общий encoder.

### 2. LLM

`config.py`:

```python
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
LLM_MODEL_NAME = os.getenv("LLM_MODEL", "openai/gpt-4o-mini")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
```

`console_chat.py` и `monika_text_runtime.py`:

```python
OpenAI(
    base_url=LLM_API_BASE,
    api_key=LLM_API_KEY or "not-needed",
    timeout=30,
    max_retries=2,
)
```

Не хардкодить `/no_think` в `get_system_prompt`.
Оставить его только для моделей с `qwen` в имени (через `ModelAdapter`).

### 3. STT

- `import keyboard` не должен валить запуск, если библиотека недоступна
  или нет разрешений macOS.
- `STT_PTT` не создаётся — либо убрать импорт из `console_chat.py`,
  либо сделать ленивым.
- Убрать из консоли сообщение «Зажмите F10», если STT не активен.

### 4. requirements.txt

Минимум:

```text
openai
chromadb
sentence-transformers
pymorphy3
numpy
sounddevice
soundfile
websockets
requests
torch
torchaudio
aiogram
faster-whisper
```

После первого успешного запуска — зафиксировать точные версии.
`faster-whisper` можно не включать, если STT не нужен.

### 5. .env.example

```text
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=openai/gpt-4o-mini
LLM_API_KEY=
MONIKA_DATA_DIR=
```

### 6. start_monika.sh

Скрипт должен:

1. Проверить `.venv`.
2. Запустить `python -m http.server 3000` в `webviewer/`.
3. Запустить `python console_chat.py`.
4. Открыть `http://localhost:3000/viewer.html` через `open`.

Без `http-server` и Node.

## Критерии приёмки

- В разрешённых файлах нет `F:\`.
- `python -c "import config, builder, graph_engine"` — без ошибок.
- `grep -R "F:\\\\" MonikaBrain/config.py MonikaBrain/builder.py MonikaBrain/graph_engine.py` — пусто.
- Ключ LLM не захардкожен.
- Chroma создаётся в `MonikaBrain/chroma_engram`, а не в текущем каталоге.
- `bash -n MonikaBrain/start_monika.sh` — без ошибок.
- Импорт `console_chat` не требует `keyboard`/STT.
- Реальная `knowledge.db` не изменена во время проверок.

## Проверка

```bash
cd MonikaBrain
source .venv/bin/activate
python -c "import config, builder, graph_engine"
grep -R "F:\\\\" config.py builder.py graph_engine.py || true
bash -n start_monika.sh
```

## Отчёт

```text
Task: 001-macos-port
Changed: ...
Checks: ...
Not done: ...
Risks: ...
```

## Вне scope

- Рефакторинг `process_input`.
- Единый runtime для Telegram.
- Чистка памяти и TTS.
- Агентные инструменты.
