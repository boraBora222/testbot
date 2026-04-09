Ниже — архитектурный разбор по загруженному архитектурному дампу, а не по полному проходу по исходникам. Уровень уверенности хороший, но не абсолютный: в дампе прямо указано, что часть ссылок на документацию отсутствует в snapshot. 

## 1) Архитектурный анализ текущего состояния

### Что это за система

Сейчас это переходный монорепозиторий: в одном кодовом дереве живут новый контур B2B crypto exchange demo и старый контур Telegram moderation/admin. Это не выглядит как “сломанная архитектура”; это выглядит как эволюция продукта, где новый домен уже доминирует, а legacy-контур еще не изолирован до конца. Дополнительно это подтверждается смешанным неймингом (`testbot`, `CourseVibe`, `reply-bot-front`).  

### Архитектурный стиль

По сути это **modular monorepo / modular monolith с выделенным shared-ядром**: `bot`, `web`, `front`, `shared`; runtime-сервисы — MongoDB, Redis, MinIO, bot, web, front. Коммуникация организована так: `bot` и `web` напрямую импортируют `shared`, фронт общается с backend по HTTP, а асинхронные сценарии идут через Redis queues. Это хороший прагматичный дизайн для инкрементального развития, но `shared` уже стал “центром гравитации”, то есть одновременно domain-layer и infrastructure-layer.  

### Слои

Слои читаются так:

* **Presentation layer**: aiogram bot, FastAPI JSON API, Jinja admin pages, React SPA.  
* **Application layer**: `shared.services.order_lifecycle`, `shared.services.security_settings`, `shared.services.documents`, плюс orchestration в web routers и bot FSM.  
* **Domain layer**: `exchange_logic`, `security_settings`, квоты, whitelist, order draft/repeat/timeline. 
* **Infrastructure layer**: MongoDB, Redis, MinIO/S3, SMTP, Caddy, Docker Compose.  

Главная проблема здесь не в отсутствии слоев, а в том, что **domain и infra частично спаяны внутри `shared`**. Для нового кода это уже риск: чем больше туда добавлять напрямую, тем дороже потом будет изолировать bounded contexts. 

### Паттерны, которые уже есть

В проекте уже читаются полезные паттерны:

* **Shared Kernel** между `bot` и `web`. 
* **Workflow/FSM** в Telegram bot для guided exchange flow. 
* **Queue-based async integration** через Redis для broadcast/status/manager notifications. 
* **Document metadata + object storage split**: данные в Mongo, файлы в MinIO, выдача через presigned URLs. 
* **Separate auth models** для website users и moderators. Это приемлемо, но требует четкой границы эксплуатации. 

### Где архитектурное напряжение

Самое заметное архитектурное напряжение — это **рассинхрон между backend-возможностями и frontend-интеграцией**. У backend уже есть orders API, order draft API, profile/deals/documents API, а SPA все еще использует `mockDeals` на overview/list, а new deal page сидит на локальной логике вместо live draft/order APIs. Это главный источник ложной сложности: продукт уже умеет больше, чем фронт показывает.  

Второй узкий момент — **два bounded contexts в одном кодовом поле**: `crypto_exchange_demo` и `legacy_submission_admin`. Пока они оба активны в одном репозитории и даже в одном наборе коллекций/админских страниц, любой новый код рискует случайно усиливать legacy-зависимости.  

Третий риск — **покрытие тестами не там, где сейчас бизнес-ценность**: auth покрыт лучше, чем exchange end-to-end flows. Для demo exchange платформы это значит, что наиболее ценные сценарии сейчас более хрупкие, чем выглядят. 

### Вывод по текущему состоянию

Итоговая характеристика: **переходная, рабочая, эволюционно развиваемая система**, где архитектурный фундамент в целом нормальный, но следующая стадия роста требует не “большого рефакторинга”, а отделения новых путей развития от legacy и доведения фронта до already-existing API. 

---

## 2) Quick Wins — быстрые улучшения без изменения API/контрактов

### 1. Подключить SPA к live order read-model

Сначала перевести **только чтение**: `/dashboard`, `/dashboard/deals`, `/dashboard/deals/:id` должны использовать `GET /orders` и `GET /orders/{order_id}` через новый фронтовый adapter, а `mockDeals` оставить как fallback через feature flag `USE_LIVE_ORDERS=false`. Это non-breaking, потому что backend API уже существует, а UI может откатиться на старое поведение при любой ошибке.  

### 2. Включить autosave/resume draft на new deal page

`/order-drafts/current` уже есть. Самый выгодный шаг — не переписывать форму, а добавить слой сохранения/восстановления черновика поверх текущей страницы создания сделки. При сбое backend форма продолжает жить в local state, как сейчас.  

### 3. Добавить contract tests на exchange flows

У вас уже есть Vitest, Testing Library, MSW, Playwright smoke и backend pytest, но зрелость тестов смещена в auth. Быстрый выигрыш — добавить минимум контрактных тестов на `orders`, `order-drafts`, `profile/whitelist`, `documents`, не меняя прод-код. Это уменьшит риск при постепенном подключении SPA к живому API.  

### 4. Ввести service facades внутри `shared` для нового кода

Не нужно срочно выносить логику из `shared`. Достаточно ввести канонические точки входа вроде `OrderService`, `ProfileService`, `DocumentService` и договориться, что новый код в `bot/web` идет только через них. Старые direct imports продолжают работать, то есть совместимость сохраняется полностью. 

### 5. Почистить нейминг и config aliasing

Смешанный нейминг сейчас не ломает систему, но ломает ментальную модель команды. Быстрый безопасный шаг — ввести **каноническое название продукта** и алиасы для старых env/config/README-упоминаний. Код и API не меняются, а стоимость сопровождения падает. 

### 6. Проверить и, если нужно, примонтировать `bot_info` router

В дампе есть наблюдение, что router существует, но не смонтирован в `web.main`. Если это реально забытый read-only endpoint, его можно вернуть как internal diagnostic/info route за существующей авторизацией или internal-only proxy rule. Если окажется лишним — явно задокументировать как deprecated. В обоих случаях это low-risk улучшение. 

### 7. Добавить correlation ID и queue envelope version

Для HTTP, bot-команд и Redis сообщений стоит ввести единый `correlation_id` и мягко версионированный envelope для новых queue-сообщений. Старые consumers продолжают читать старый формат, новые — понимают оба. Это не затрагивает публичный API и дает сильный прирост наблюдаемости. 

Рабочий контракт для текущего репозитория:

* HTTP использует `X-Correlation-Id` как канонический заголовок, а `X-Request-Id` держится как compatibility mirror.
* Redis tracing использует `_async_trace.correlation_id` как каноническое поле; legacy `trace_id` может оставаться только как mirror того же значения.

---

## 3) Новые фичи, которые естественно вписываются в текущую структуру

### 1. Таймлайн сделки в SPA

В `shared.services.order_lifecycle` уже заявлены status meta и timeline building, а у фронта уже есть detail route. Естественное расширение — показать на карточке сделки timeline статусов, не меняя контракт, а лишь добавив новые необязательные поля в response или отдельный read-model endpoint с backward-compatible расширением. При неуспехе UI просто скрывает блок timeline.   

### 2. “Resume incomplete deal” в web и Telegram

Система уже знает про drafts и repeat order flow. Поверх этого очень естественно ложится функция “продолжить незавершенную заявку” и в SPA, и в боте. Fallback — старое поведение без resume.   

### 3. Compliance readiness / checklist

У вас уже есть whitelist, limits, profile documents, deal documents. Значит можно собрать “готовность профиля к сделке”: документы загружены, whitelist одобрен, лимиты доступны, уведомления настроены. Это чистый read-model поверх существующих сущностей и API. При ошибке блок можно просто не показывать.   

### 4. Notification center / digest

Есть notification preferences, manager notifications и status queues. Логичное развитие — центр уведомлений в кабинете плюс простой digest “что изменилось по вашим сделкам/whitelist”. Начать можно с read-only inbox на базе уже существующих событий. Если новый контур падает, остаются старые каналы доставки.   

### 5. Support thread view с вложениями

`support_messages` уже есть в модели, бот уже умеет text/photo/document. Естественный next step — единая история обращения в веб-кабинете и у менеджера. Это добавляет ценность без вмешательства в критический путь создания заявок.   

### 6. Whitelist moderation UX improvements

Так как pending whitelist moderation уже есть в админке, можно добавить историю решений, причину отклонения и повторную отправку адреса. Это укладывается в текущую модель безопасности и не требует ломать существующий сценарий ручного approve/reject.  

---

## 4) Архитектурные улучшения по категориям

## A. Границы доменов

### Что улучшить

Нужно формально отделить `crypto_exchange_demo` от `legacy_submission_admin`: хотя бы на уровне пакетов, ownership и dependency rules. Не переносить код целиком, а объявить “новые изменения только в exchange-контуре; legacy — только bugfix/compatibility”. 

### Как внедрять

1. Ввести package-level namespaces/маршруты ownership.
2. Добавить линтерное правило или review-checklist: новый exchange-код не импортирует legacy-модули.
3. Старые точки входа остаются как есть.

Текущий рабочий договор зафиксирован в `docs/tasks/exchange_master_plan/01-domain-boundaries-and-service-facades.md`: `legacy = compatibility only`, а новый exchange-код идёт через фасады в `shared/services`.

### Почему это safe

Нет изменения контрактов, только организационная и модульная изоляция.

### Fallback

Если правило мешает релизу, его можно временно ослабить для конкретного модуля, не откатывая код.

---

## B. Application layer и зависимость от `shared`

### Что улучшить

Сейчас `bot` и `web` напрямую тянут shared DB/domain services. Это быстро, но со временем рождает тесную связность. Следующий правильный шаг — **не выносить домен**, а ввести тонкий application layer поверх `shared`, чтобы новые use-cases вызывались через стабильные сервисы.  

### Как внедрять

* Для каждого нового сценария сначала писать `use_case/service facade`.
* Старые роуты и handlers не переписывать массово.
* Новые фичи подключать только через новый слой.

### Почему это safe

Старые imports продолжают жить. Изменение инкрементальное.

### Fallback

Любой use-case можно временно переключить обратно на старый direct path.

---

## C. Frontend integration

### Что улучшить

Фронт сейчас самый явный “архитектурный долг”: часть кабинета живая, часть моковая. Нужен не rewrite, а **adapter layer**: `DealsDataSource = Mock | Live`. Это позволит подключать реальные данные по страницам. 

### Как внедрять

1. Сначала read-only details page.
2. Затем deals list.
3. Затем dashboard overview.
4. Затем create flow через drafts/submit.

### Почему это safe

UI и маршруты не меняются; меняется только источник данных.

### Fallback

Флагом вернуть mock provider.

---

## D. Асинхронность и фоновые процессы

### Что улучшить

Redis queues уже есть, но дамп оставляет вопрос о worker-архитектуре открытым. Я бы не вводил тяжелую очередь/оркестратор, а стандартизировал текущий подход: единый envelope, retry policy, DLQ для новых consumer’ов, backlog metrics.  

### Как внедрять

* Новые сообщения публиковать в envelope v2.
* Consumers читают и старый, и новый формат.
* DLQ только для новых очередей.

### Почему это safe

Публичные API не меняются, существующие producers/consumers можно не трогать сразу.

### Fallback

Новые consumers отключаются флагом, старый queue path остается.

---

## E. Данные и хранилища

### Что улучшить

Модель уже разумно разделяет Mongo metadata и MinIO objects. Следующий шаг — усилить read/write устойчивость: проверить индексы на `orders`, `order_drafts`, `whitelist_addresses`, `support_messages`, `sessions`, а также добавить аудит критичных переходов статусов и whitelist-решений в side-collection. 

### Как внедрять

* Сначала read-only audit writes best-effort.
* Индексы добавлять отдельно через миграции без изменения схемы API.
* TTL — только для явно временных сущностей вроде auth/session/reset flows, если они еще не настроены.  

### Почему это safe

Не ломает существующие документы и маршруты.

### Fallback

Любой новый аудит можно отключить без влияния на основной поток.

---

## F. Безопасность и эксплуатация

### Что улучшить

Есть раздельная auth-модель для users и moderators, uploads, presigned downloads, SMTP flows. Наиболее полезные безопасные улучшения без контракта:

* correlation/audit по скачиваниям документов,
* более строгая серверная валидация MIME + extension + size,
* отделение moderator surface на уровне proxy/network policy,
* rate limit на auth/public forms.   

### Почему это safe

Это либо infra-hardening, либо ужесточение внутренней проверки без изменения внешнего контракта.

### Fallback

Политики можно включать поэтапно и rollback’ить настройками proxy/app.

---

## G. Тестирование и observability

### Что улучшить

Сейчас тесты лучше покрывают auth, чем exchange-domain. Для эволюционной архитектуры это опасно: вы будете бояться трогать как раз тот слой, который нужно развивать. Минимальный правильный сдвиг — добавить:

* contract tests на API обмена,
* smoke сценарий “register → verify → login → create draft → submit → list orders”,
* интеграционный тест “upload document → presigned download”,
* сквозной request/queue correlation ID в логах.  

### Почему это safe

Это добавление гарантий, а не изменение поведения.

### Fallback

Тесты и telemetry можно катить независимо от фич.

---

## Что я бы делал первым

1. Убрал бы зависимость фронта от `mockDeals` через adapter + feature flag. 
2. Подключил бы `/order-drafts/current` для autosave/resume. 
3. Добавил бы contract tests на orders/profile/documents. 
4. Зафиксировал бы правило: новый код идет только в exchange-контур и только через service facades в `shared`. 
5. После этого уже добавлял бы timeline, compliance checklist и notification center.  

Если нужен, следующим сообщением подготовлю это в виде **пошагового roadmap на 30/60/90 дней** с приоритетами, рисками и примером структуры каталогов без breaking changes.
