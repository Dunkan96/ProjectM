# Task 002 — Test harness и изоляция данных

## Цель

Сделать безопасную среду для тестов и агентов:
временная БД, fake LLM, отсутствие сети, TTS и записи в реальную память.

Без этого нельзя запускать тестер-агента и параллельных кодеров.

## Предусловия

- Task 001 выполнен: пути и `MONIKA_DATA_DIR` уже поддерживаются.
- Установлены `pytest`, `pytest-cov`.

## Разрешённые файлы

- Новые: `MonikaBrain/tests/`, `MonikaBrain/tests/conftest.py`,
  `MonikaBrain/tests/fake_llm.py`, `MonikaBrain/tests/test_smoke.py`.
- `MonikaBrain/config.py` — только чтение `MONIKA_DATA_DIR`.
- `MonikaBrain/builder.py` — только путь к данным/Chroma, если ещё не доделано.
- `pyproject.toml` или `pytest.ini` — конфигурация тестов.

## Запрещено

- Писать в `knowledge.db`, `monika_memory.db`, `chroma_engram/`.
- Делать реальные сетевые вызовы.
- Запускать Silero TTS, `sounddevice`, `keyboard`.
- Менять поведение Моники и промпты.
- Коммитить тестовые БД и WAV.

## Что сделать

### 1. Изоляция данных

- `MONIKA_DATA_DIR` указывает на `tmp_path` в тестах.
- `Builder` и `GraphEngine` должны создавать БД/Chroma только внутри этого каталога.
- В тестах копировать схему, а не реальные данные.
- Добавить fixture `temp_brain`:
  - создаёт временный каталог;
  - выставляет env;
  - возвращает путь;
  - после теста удаляет.

### 2. Fake LLM

`tests/fake_llm.py`:

- объект с `chat.completions.create(...)`, возвращающий заранее заданный ответ;
- поддержка `tool_calls` для проверки tool-loop;
- запись вызовов: модель, сообщения, параметры;
- возможность вернуть ошибку/таймаут.

Не использовать `unittest.mock` там, где нужен сценарий из нескольких ответов.

### 3. Smoke-тест

`tests/test_smoke.py`:

- импорт ключевых модулей;
- создание `Builder` на temp-каталоге;
- один вызов `MonikaTextRuntime.answer` с fake LLM;
- проверка, что реальная `knowledge.db` не изменилась (mtime/size).

### 4. Golden-диалоги

Папка `tests/golden/`:

- 10–20 сценариев: `input.txt`, `expected.json`;
- проверять не дословный ответ, а свойства:
  - длина в предложениях;
  - отсутствие meta-leak (`<think>`, «turn contract»);
  - отсутствие RP-формата;
  - наличие/отсутствие памяти;
  - эмоция/режим.

### 5. Команды

```bash
cd MonikaBrain
source .venv/bin/activate
pytest -q
pytest -q tests/test_smoke.py
```

## Критерии приёмки

- `pytest -q` проходит без сети и без TTS.
- Ни один тест не открывает реальные `knowledge.db` / `monika_memory.db`.
- Есть тест, который специально проверяет изоляцию данных.
- Fake LLM умеет возвращать обычный ответ, tool call и ошибку.
- Есть минимум 10 golden-сценариев.
- `pytest --collect-only -q` показывает все тесты.

## Отчёт

```text
Task: 002-test-harness
Changed: ...
Checks: pytest -q — N passed
Isolation: real DB untouched (mtime check)
Not done: ...
Risks: ...
```

## Вне scope

- Рефакторинг `process_input`.
- Новые когнитивные слои.
- Полный e2e с реальным облачным LLM.
