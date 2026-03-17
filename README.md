====
Бот ответов CourseVibe

Overview
Этот репозиторий содержит Telegram-бота и небольшой веб-админ-интерфейс для управления пользовательскими заявками и рассылкой сообщений. В качестве хранилища используется MongoDB, а для очередей — Redis. Оба сервиса запускаются через Docker Compose.

Components

* Bot (aiogram): Обрабатывает взаимодействия в Telegram, очереди и уведомления.
* Web (FastAPI): Предоставляет админ-интерфейс с аутентификацией и базовыми страницами.
* MongoDB: Основное хранилище данных.
* Redis: Очереди и эфемерное состояние.

Requirements

* Docker и Docker Compose
* Python 3.11+ (только для локальной разработки вне Docker)

Environment Configuration
Переменные окружения загружаются из dotenv-файла. Укажите либо .env (похоже на прод), либо .env.dev (локально/для разработки). Файл compose использует ENV_FILE, если он задан, иначе по умолчанию берет .env.

Важно: не коммитьте секреты. Держите .env и .env.dev в секрете.

Скопируйте пример и подстройте значения:

1. Создайте .env на основе текущих открытых файлов в корне репозитория.

   * .env предназначен для серверных/прод-подобных значений
   * .env.dev — для локальной разработки

2. Обзор обязательных ключей (имена менять нельзя):

* BOT_NAME
* TELEGRAM_BOT_TOKEN
* TARGET_CHAT_ID (опционально)
* WEB_PORT
* WEB_APP_HOST
* WEB_SECRET_KEY
* MODERATOR_USERNAME
* MODERATOR_PASSWORD
* MONGO_DB_NAME
* REDIS_DB
* REDIS_QUEUE_NAME
* AUTO_MODERATION_QUEUE_NAME
* GOOGLE_GEMINI_API_KEY (опционально; LLM удален, оставлено для совместимости)
* AUTO_MODERATION_DAILY_LIMIT
* AUTO_MODERATION_PROMPT
* WEB_BASE_URL
* MASTER_USER_IDS
* BROADCAST_QUEUE_NAME

Running with Docker

1. Выбор env-файла

   * Для dev: установите переменную окружения при запуске compose:

     * Windows PowerShell:
       $env:ENV_FILE=".env.dev"; docker compose up -d --build
   * Для прод-подобного: опустите ENV_FILE или установите .env

2. Запуск сервисов
   docker compose up -d --build

3. Доступ к веб-интерфейсу
   [http://localhost:WEB_PORT](http://localhost:WEB_PORT)

Local Development Without Docker (optional)

1. Создайте виртуальное окружение и установите зависимости:
   python -m venv .venv
   ..venv\Scripts\Activate.ps1
   pip install -r requirements.txt

2. Экспортируйте окружение (PowerShell):

   * Используйте значения из .env.dev, чтобы задать переменные окружения перед запуском процессов

3. Запустите MongoDB и Redis локально или отдельными контейнерами Docker.

4. Запуск бота:
   python -m bot.main

5. Запуск веба:
   uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload

Notes

* Docker Compose теперь читает переменные напрямую из env-файла, а сервисы находят друг друга по именам (mongo, redis).
* Устаревший модуль LLM удален. GOOGLE_GEMINI_API_KEY остается опциональным для совместимости.

## Руководство (RU)

### Требования

* Установленный Docker + Docker Compose
* Windows PowerShell (рекомендуется для команд)
* Python 3.11+ (только для локального запуска без Docker)

### Установка Docker

* Windows: установите [Docker Desktop](https://www.docker.com/products/docker-desktop/), включите WSL2 при необходимости, перезагрузите систему. Затем проверьте в PowerShell:

  ```powershell
  docker --version
  docker compose version
  ```
* macOS: установите [Docker Desktop](https://www.docker.com/products/docker-desktop/), затем проверьте версии аналогично.
* Linux: установите Docker Engine и плагин Compose из официальной документации вашей дистрибуции.

### Переменные окружения

1. Скопируйте значения в файлы в корне репозитория:

   * `.env` — для прод/серверного окружения
   * `.env.dev` — для локальной разработки
2. В качестве примера ориентируйтесь на существующие `.env` и `.env.dev` в репозитории (или `.env.example`).
3. Критично: не коммитьте секреты. Держите `.env` и `.env.dev` в секрете.


### Запуск в Docker

1. Dev-вариант (использует `.env.dev`):

```powershell
$env:ENV_FILE = ".env.dev"; docker compose up -d --build
```

2. Prod/сервер (использует `.env` по умолчанию):

```powershell
# Явно указать .env

#dev
docker compose --env-file .env.dev up -d --build
#prod
docker compose --env-file .env up -d --build

# или просто без ENV_FILE (compose возьмёт .env по умолчанию)
docker compose up -d --build
```

3. Доступ к веб-интерфейсу:

```text
http://localhost:<WEB_PORT>
```

4. Полезные команды:

```powershell
# Просмотр логов
docker compose logs -f web
docker compose logs -f bot

# Остановка без удаления
docker compose stop

# Полная остановка с удалением контейнеров/сетей, + удаление томов (данные Mongo будут удалены)
docker compose down -v
```

Примечания:

* Внутри Docker сервисы доступны по именам `mongo` и `redis`. Соединения по умолчанию уже настроены.

### Локальная разработка без Docker (опционально)

1. Создать и активировать виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Запуск с подхватом переменных из `.env.dev` (через python-dotenv):

```powershell
# Бот
python -m dotenv -f .env.dev run -- python -m bot.main

# Веб
python -m dotenv -f .env.dev run -- uvicorn web.main:app --host 0.0.0.0 --port 8000 --reload
```

3. Отключение venv:

```powershell
deactivate
```
