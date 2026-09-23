# PromptAgents — умный подбор event-подрядчиков

Сервис для заказчиков мероприятий в Казахстане: помогает выбрать до трёх
подрядчиков из каталога по условиям заказа и получить проверяемое объяснение
каждой рекомендации. Полное задание — [TASK.md](TASK.md), уточнённый контракт
с фактически предоставленным CSV — [docs/api-contract.md](docs/api-contract.md).

## Текущий этап

Подготовлен общий каркас для трёх инженеров. Работают FastAPI, health, options,
валидация CSV и входных параметров, React-форма и шесть кнопок демо.
**Подбор в API и объяснения пока не реализованы:** POST возвращает HTTP 501 с
понятным сообщением. Демокнопки заполняют форму и отправляют настоящий запрос,
а не подставляют готовые результаты.

Шесть реальных сценариев уже проверены отдельным алгоритмом фильтрации и
тестами на исходном CSV. Это проверка данных и ожидаемого поведения, а не
завершённый пользовательский сценарий. Результаты — [docs/demo.md](docs/demo.md).

## Технологии и архитектура

React 19.3 + TypeScript 7 + Vite 8; Python 3.11 + FastAPI + Pydantic; pytest.
Данные читаются стандартным csv.DictReader в память при старте. Базы данных нет.
Зависимости закреплены в backend/requirements.txt и frontend/package-lock.json.

Браузер → Vite proxy /api → FastAPI → проверенный CSV в памяти.
Будущий модуль подбора выполняет жёсткие фильтры и ранжирование, затем вызывает
explain() для карточек. AI-компонент — будущий отдельный скрипт подготовки
признаков в data/derived/. Модель и провайдер ещё не выбраны; AI-ключ для
локального запуска не требуется. Сетевых AI-вызовов в пользовательском запросе нет.

| Путь | Назначение |
| --- | --- |
| backend/app/models.py | Схемы запросов, ответов, evidence и prepared-признаков |
| backend/app/catalog.py | Прямой импорт CSV, валидация, значения для формы |
| backend/app/main.py | HTTP API; recommend явно помечен как незавершённый |
| backend/app/explanations.py | Зафиксированный интерфейс инженера №3 |
| frontend/ | Форма, API-клиент, типы и входные параметры демокнопок |
| scripts/ | Проверка импорта и независимый аудит сценариев |
| tests/ | Проверки каркаса и реальные ожидаемые множества ID |
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

## Как проверить каркас

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -q
.\.venv\Scripts\python.exe -X utf8 -m scripts.check_demos
npm.cmd --prefix frontend run build
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/options
```

На Linux/macOS используйте .venv/bin/python и npm вместо путей Windows.
Ожидается health с dataset_status=ready, profile_count=66 и
recommendation_implemented=false. Options возвращает реальные значения и
окно дат. Нажатие любой демокнопки вызывает /api/recommend и пока показывает
честную ошибку 501. Неверные параметры дают 422; отсутствующий или повреждённый
CSV — 503, не no_match.

Проверки recommend как готового API, карточек, доказательности объяснений и
AI-fallback предстоят инженерам. Чек-лист — [docs/tasks.md](docs/tasks.md).

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
не подтверждает соответствие. Внешние API пока не подключены.

## Ограничения

- Нет реализации recommend, карточек результата, объяснений и AI-экстрактора.
- Доступность подтверждается только внутри 2026-09-23 — 2026-12-31.
- Цена стартовая: окончательную стоимость нужно уточнять у подрядчика.
- Исходные синтетические и восстановленные значения помечаются флагами;
  их отображение в будущих карточках закреплено контрактом.
- Изменение файла требует перезапуска backend; бронирование, авторизация,
  платежи, админка и БД не входят в объём проекта.

## Совместная работа

Правила и владение файлами — [AGENTS.md](AGENTS.md).
Три независимых задания и критерии готовности — [docs/tasks.md](docs/tasks.md).
Одна общая версия каркаса → отдельные ветки codex/backend-matching,
codex/frontend, codex/explanations-tests → интеграция инженером №1.

## Развёрнутая версия

Ссылка пока не указана.

## Команда

- Biloshchytskyi Yevhenii
- Batyr Nursaya
- Biloshchytskyi Artem
