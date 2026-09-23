# PromptAgents — умный подбор event-подрядчиков

Сервис для заказчиков мероприятий в Казахстане: помогает выбрать до трёх
подрядчиков из каталога по условиям заказа и получить проверяемое объяснение
каждой рекомендации. Полное задание — [TASK.md](TASK.md), уточнённый контракт
с фактически предоставленным CSV — [docs/api-contract.md](docs/api-contract.md).

## Что реализовано

FastAPI загружает и проверяет CSV, отдаёт настройки формы и подбирает до трёх
подрядчиков. Город и категория, занятость, бюджет, формат, язык и длительность
проверяются по структурированным полям. Ранжирование учитывает подтверждённую
специализацию, стартовую цену и ID. Ответ различает `matched`,
`category_absent` и `no_match`, показывает число всех подходящих и причины
исключений. Каждая карточка содержит объяснение и проверяемые evidence.

React-интерфейс показывает карточки, диагностику и шесть кнопок демо. Кнопки
подставляют параметры и отправляют настоящий запрос к API. Есть сравнение двух
дат по доказательствам календаря, обработка ошибок и отдельно обозначенный
режим учебных примеров `?examples=1`.

Все шесть реальных сценариев проверены отдельным аудитом, тестами движка и
HTTP-запросами к объединённой версии: [результаты и команды](docs/demo.md).

## Технологии и архитектура

React 19.3 + TypeScript 7 + Vite 8; Python 3.11 + FastAPI + Pydantic; pytest.
Данные читаются стандартным csv.DictReader в память при старте. Базы данных нет.
Зависимости закреплены в backend/requirements.txt и frontend/package-lock.json.

Браузер → Vite proxy `/api` → FastAPI → проверенный CSV в памяти. Модуль подбора
выполняет фильтры и ранжирование, затем вызывает `explain()` для карточек.
Объяснения работают без AI. Необязательный offline-скрипт может подготовить
признаки через OpenAI Responses API в `data/derived/`; при HTTP-запросе к модели
обращений нет. На момент интеграции ключ не был задан и AI-артефакт не создан.

| Путь | Назначение |
| --- | --- |
| backend/app/models.py | Схемы запросов, ответов, evidence и prepared-признаков |
| backend/app/catalog.py | Прямой импорт CSV, валидация, значения для формы |
| backend/app/main.py | HTTP API и загрузка подготовленных признаков при старте |
| backend/app/matching.py | Фильтры, ранжирование и диагностика |
| backend/app/explanations.py | Детерминированные объяснения и evidence |
| frontend/ | Форма, карточки, сравнение дат, API-клиент и демокнопки |
| scripts/ | Проверка CSV, аудит демо, HTTP-прогон и необязательная AI-подготовка |
| tests/ и frontend/tests/ | Проверки API, объяснений, данных, интерфейса и интеграции |
| docs/ | Контракт, задания, примеры ответов и демосценарии |
| index.html | Исходное HTML-превью каталога; не frontend-приложение |

## Установка и запуск

Проверено на Python 3.11 и Node.js 24.15.0 / npm 11.12.1.
Все команды ниже — из корня репозитория. Путь к CSV с пробелами сохранён намеренно.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -X utf8 -m scripts.validate_data
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Во втором терминале:

```powershell
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run dev
```

### Linux / macOS

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
cp .env.example .env
.venv/bin/python -m scripts.validate_data
.venv/bin/python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Во втором терминале:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Открыть [форму](http://127.0.0.1:5173), [health](http://127.0.0.1:8000/api/health)
или [Swagger](http://127.0.0.1:8000/docs). Vite перенаправляет /api на порт 8000.
Для npm preview также настроен proxy; облачный деплой пока не настроен.
Копирование .env необязательно: значения по умолчанию уже работают. Если .env
существует, сохраните настройки. DATA_PATH и DERIVED_PATH — пути относительно
корня; секретов в .env.example нет.

## Как проверить решение

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m pytest -q tests/integration_cases.py
.\.venv\Scripts\python.exe -X utf8 -m scripts.check_demos
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/options
.\.venv\Scripts\python.exe -X utf8 -m scripts.verify_api_demos
```

На Linux/macOS используйте .venv/bin/python и npm вместо путей Windows.
Ожидается `dataset_status=ready`, `profile_count=66` и
`recommendation_implemented=true`. Options возвращает реальные значения и
окно дат. Нажатие демокнопки вызывает `/api/recommend` с одним из трёх
бизнес-исходов. Неверные параметры дают 422; отсутствующий или повреждённый
CSV — 503. Отсутствие AI-артефакта даёт предупреждение и baseline-объяснения.

При недоступном системном npm-кеше на Windows используйте локальный:
`npm.cmd --prefix frontend ci --cache .npm-cache`. Папка исключена из Git.

## Данные и интеграции

Исходный [hackathon dataset anonymized .csv](<hackathon dataset anonymized .csv>)
сохранён без изменения байтов. Импорт: UTF-8 с возможным BOM, разделитель списков
|, флаги только True/False, цена int, пустой max_hours → None, описание дословно.
SHA-256: 6a724b6b7dfb5973343e68ba18dadb60fc807d87e3d78f03ee86fb26cb089f7d.

Подтверждены 66 уникальных профилей: Алматы — 50, Астана — 15, Зарубежье — 1;
13 synthetic, 18 price_imputed, 8 city_imputed; 13 записей с несколькими
категориями и 9 с пустым max_hours. Это характеристики текущего файла, а не
ограничения будущего размера. Дополнительных профилей в каталог не добавлено.

Структурированные поля имеют приоритет: description и AI не могут расширить
форматы, языки, длительность, изменить календарь или цену. Противоречивая цитата
не подтверждает соответствие. Внешний API используется только необязательным
offline-скриптом; [инструкция AI-подготовки](data/derived/README.md).

## Ограничения

- Реальный AI-артефакт не подготовлен: без ключа используется baseline.
- Подготовленные признаки и бонус специализации проверены на тестовых ответах,
  но не на реальном вызове модели.
- Доступность подтверждается только внутри 2026-09-23 — 2026-12-31.
- Цена стартовая: окончательную стоимость нужно уточнять у подрядчика.
- Исходные синтетические и восстановленные значения помечены в карточках.
- Браузерный прогон шести сценариев после слияния веток ещё не выполнен;
  отдельно проверены HTTP API, frontend-тесты и production-сборка.
- Изменение файла требует перезапуска backend; бронирование, авторизация,
  платежи, админка и БД не входят в объём проекта.

## Совместная работа

Правила и владение файлами — [AGENTS.md](AGENTS.md).
Три независимых задания и критерии готовности — [docs/tasks.md](docs/tasks.md).
Ветки `codex/backend-matching`, `codex/frontend` и
`codex/explanations-tests` объединены в `main`.

## Развёрнутая версия

Ссылка пока не указана.

## Команда

- Biloshchytskyi Yevhenii
- Batyr Nursaya
- Biloshchytskyi Artem
