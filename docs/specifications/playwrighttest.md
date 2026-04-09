Ниже — финальная редакция ТЗ, уже с встроенными решениями по verification code, auth setup, logout-policy, следующей фазе для reset-password и целевому docker-сервису `e2e-runner`. Основание для правок: в проекте уже есть `front-smoke`, `front-test`, `backend-test`, hash-routing с `ProtectedRoute`, frontend auth-context с `register/login/logout/verifyEmail`, а verification code отправляется через SMTP/email service.      

# ТЕХНИЧЕСКОЕ ЗАДАНИЕ

## Разработка и внедрение Playwright E2E/API-тестов для `front` + `web`

---

## 1. Общие сведения

| Параметр                    | Значение                                                                                                                                                                                                                                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Наименование задачи**     | Разработка единой архитектуры Playwright-тестов для frontend и backend с покрытием пользовательских сценариев, контрактов авторизации и smoke-регрессии                                                                                                                                                 |
| **Исполнитель**             | QA Automation Engineer / Fullstack Developer                                                                                                                                                                                                                                                            |
| **Целевой стек**            | Playwright, TypeScript, Node.js, Docker Compose, React/Vite, FastAPI                                                                                                                                                                                                                                    |
| **Контур внедрения**        | `front` + `web`                                                                                                                                                                                                                                                                                         |
| **Вне scope данной задачи** | Telegram-бот `bot` и его end-to-end автоматизация                                                                                                                                                                                                                                                       |
| **Текущее состояние**       | В проекте уже есть: frontend auth/unit tests на Vitest, backend auth tests на pytest, а также browser smoke-скрипт `front/scripts/browser-smoke.cjs`; отсутствует единый поддерживаемый Playwright-слой для cross-stack проверки `front` ↔ `web` и миграции browser smoke в управляемый test runner.    |
| **Целевое состояние**       | Выделенный Playwright-контур в корне репозитория, покрывающий API auth-contract, ключевые UI auth-flow, protected routes, базовую smoke-регрессию публичных страниц и интеграцию в Docker/CI                                                                                                            |

---

## 2. Цели задачи

1. Создать поддерживаемую и масштабируемую архитектуру Playwright-тестов для `front` и `web`.
2. Добавить недостающий интеграционный слой между frontend и backend без дублирования существующих Vitest и pytest тестов.
3. Перенести текущий browser smoke в Playwright Test Runner без потери фактического покрытия.
4. Проверить авторизацию, protected routes, сессионные cookie, logout и основные пользовательские маршруты.
5. Подготовить тесты к локальному запуску, запуску в Docker и использованию в CI.

---

## 3. Принципы проектирования тестового контура

### 3.1. Разделение по уровням тестирования

В проекте должны сохраняться разные уровни тестов с разной ответственностью:

* **Vitest/MSW** — быстрые frontend unit/integration тесты компонентов, контекстов и локальной роутинг-логики.
* **pytest** — глубокие backend-тесты бизнес-правил, негативных сценариев, ошибок, edge-cases и security-проверок.
* **Playwright API** — только контрактные и интеграционные проверки auth-цепочки через реальные HTTP-вызовы.
* **Playwright UI** — реальные пользовательские сценарии и cross-stack проверка связки `front` ↔ `web`.

### 3.2. Что Playwright не должен делать

Playwright не должен:

* становиться дублёром существующих pytest auth-матриц;
* дублировать весь слой frontend unit tests;
* заменять backend integration coverage там, где уже есть полноценный pytest-контур.

### 3.3. Основные архитектурные правила

* один корневой e2e-workspace;
* явное разделение API-, UI- и smoke-наборов тестов;
* отсутствие shared mutable state между независимыми тестами;
* отказ от `waitForTimeout`, кроме строго обоснованных технических исключений;
* переиспользование локаторов и сценариев только там, где это реально снижает хрупкость;
* возможность запуска как локально, так и внутри docker-compose;
* миграция текущего smoke без снижения покрытия;
* hash-router должен учитываться в URL assertions UI-тестов, так как приложение работает через `HashRouter`, а защищённые маршруты реализованы через `ProtectedRoute`.  

---

## 4. Scope работ

### 4.1. Входит в scope

* Playwright workspace в корне проекта;
* Playwright config, fixtures, helpers, test data factory;
* API auth-contract тесты;
* UI auth-flow тесты;
* protected route проверки;
* smoke-регрессия публичных страниц;
* docker integration;
* HTML/JUnit/trace отчёты;
* README для локального запуска и CI;
* mail-capture интеграция для verification flow.

### 4.2. Не входит в scope

* автоматизация Telegram-бота;
* переписывание существующих Vitest и pytest тестов без необходимости;
* полное покрытие всех backend endpoints через Playwright;
* визуальная регрессия;
* performance/load testing;
* reset-password flow в текущей фазе.

---

## 5. Фактические требования к логике тестов

### 5.1. Авторизация и регистрация

Архитектура тестов должна учитывать фактическую логику приложения:

* frontend использует hash-router, поэтому browser assertions должны проверять маршруты в формате `/#/...`; 
* `register`, `login`, `logout`, `sendVerificationCode`, `verifyEmail` и `refreshUser` уже заложены в `AuthProvider`; после `logout` frontend очищает auth-state, а после `verifyEmail` выполняет `refreshUser()`. 
* protected route при отсутствии авторизации ведёт на `/login` и сохраняет `state.from`; это уже отражено в существующих frontend тестах и должно быть покрыто на browser-уровне. 

### 5.2. Разделение happy-path сценариев

В рамках Playwright должны быть покрыты отдельные сценарии:

1. **Guest → protected route → login → dashboard**
2. **Existing user → login → dashboard**
3. **Register new user → verify-email → dashboard**
4. **Authenticated user → logout → protected route becomes unavailable**

### 5.3. Политика logout

В текущей фазе обязательным считается:

* очистка auth-state после logout;
* недоступность protected routes после logout;
* повторная проверка `/auth/me` или эквивалентной авторизационной проверки должна подтверждать потерю сессии.

**Необязательное требование:** мгновенный frontend redirect сразу после logout.
Достаточно сценария, в котором после logout защищённые маршруты больше недоступны и пользователь перенаправляется на login при следующей попытке доступа.

### 5.4. Сессии и cookie

Тесты должны проверять:

* установка auth-cookie после `register` и/или `login`;
* успешный вызов `/auth/me` при валидной сессии;
* отказ в доступе к `/auth/me` без сессии;
* удаление или инвалидирование сессии после `logout`;
* невозможность доступа к protected routes после logout;
* повторное открытие сессии в новом браузерном контексте через `storageState` для authenticated UI tests.

---

## 6. Целевая архитектура решения

### 6.1. Структура каталогов

```text
e2e/
├── package.json
├── tsconfig.json
├── playwright.config.ts
├── .env.example
├── README.md
├── .gitignore
├── artifacts/
│   └── .gitkeep
├── state/
│   └── .gitkeep
├── fixtures/
│   ├── test.ts
│   ├── api.ts
│   ├── auth.ts
│   └── dataFactory.ts
├── helpers/
│   ├── env.ts
│   ├── urls.ts
│   ├── waitForServices.ts
│   ├── authApi.ts
│   ├── mail.ts
│   └── assertions.ts
├── pages/
│   ├── LoginPage.ts
│   ├── RegisterPage.ts
│   ├── VerifyEmailPage.ts
│   ├── DashboardPage.ts
│   ├── ContactsPage.ts
│   └── ApiDocsPage.ts
├── tests/
│   ├── api/
│   │   └── auth.contract.spec.ts
│   ├── ui/
│   │   ├── auth.guest.spec.ts
│   │   ├── auth.login.spec.ts
│   │   ├── auth.register-verify.spec.ts
│   │   ├── auth.logout.spec.ts
│   │   └── protected-routes.spec.ts
│   └── smoke/
│       ├── public-pages.spec.ts
│       ├── lead-forms.spec.ts
│       └── dashboard-smoke.spec.ts
└── setup/
    ├── auth.setup.ts
    └── health.setup.ts
```

### 6.2. Логическое разделение наборов тестов

#### A. `tests/api`

Назначение: auth-contract и session-contract проверки без браузера.

Покрытие:

* `POST /auth/register`
* `POST /auth/login`
* `GET /auth/me`
* `POST /auth/logout`
* `POST /auth/send-verification-code`
* `POST /auth/verify-email`

Ограничение:

* глубокие негативные backend-матрицы не дублировать, если они уже покрыты pytest.

#### B. `tests/ui`

Назначение: пользовательские сценарии авторизации и защищённых роутов.

Покрытие:

* доступ гостя к защищённому роуту;
* логин существующего пользователя;
* регистрация нового пользователя;
* подтверждение email;
* logout;
* повторная загрузка auth-state.

#### C. `tests/smoke`

Назначение: перенос текущего `browser-smoke.cjs` в Playwright Test Runner.

Покрытие должно сохранить минимум текущее browser smoke-ядро:

* главная страница;
* FAQ;
* API docs;
* скачивание документации;
* форма контактов;
* модальная заявка;
* заявка из калькулятора;
* login и переход в dashboard. 

---

## 7. Playwright Projects

В `playwright.config.ts` должны быть заведены независимые projects:

```text
projects:
  - health-check
  - api-auth
  - ui-guest
  - setup-authenticated
  - ui-authenticated
  - smoke-public
```

### Назначение проектов

* **health-check** — проверка готовности `front` и `web`;
* **api-auth** — API contract tests;
* **ui-guest** — сценарии без авторизации;
* **setup-authenticated** — создание `storageState` для authenticated UI tests;
* **ui-authenticated** — сценарии с уже подготовленной сессией;
* **smoke-public** — публичная smoke-регрессия.

`ui-authenticated` должен зависеть от `setup-authenticated`, а не от общего глобального state-файла для всего test suite.

---

## 8. Подход к авторизации в тестах

### 8.1. Для API-тестов

Использовать отдельный `APIRequestContext` на тест или на describe-блок, в зависимости от сценария.

Базовый подход:

* выполнять login/register через Playwright API context;
* использовать встроенное состояние контекста и `storageState`, когда это уместно;
* ручной разбор `Set-Cookie` не использовать как основной паттерн;
* ручной разбор допускается только как fallback для диагностики cookie-contract или нестандартного поведения proxy.

### 8.2. Для UI-тестов

Использовать два режима:

* **anonymous context** — для guest/protected-route/login/register flow;
* **authenticated context** — через setup project и отдельный `storageState` файл.

### 8.3. Для logout-тестов

`logout` должен тестироваться в отдельном контексте, чтобы исключить влияние на другие authenticated tests.

### 8.4. Стратегия создания пользователя

Основной паттерн — **создание пользователя на лету** в setup project / fixture.

Это означает:

* постоянный seed-user не используется как базовый подход;
* для authenticated setup project создаётся уникальный пользователь через API;
* для login UI tests пользователь создаётся в precondition или fixture, затем логин выполняется через UI;
* тесты не должны зависеть от заранее существующего глобального аккаунта.

Такой подход лучше соответствует текущему frontend auth lifecycle и снижает риск параллельных конфликтов и загрязнения состояния. 

---

## 9. Паттерны проектирования тестов

### 9.1. Обязательные

* `fixtures` для общих зависимостей;
* test data factory для email, паролей и имён;
* helper-слой для API auth вызовов и ожидания готовности сервисов;
* route helper для hash-router URL.

### 9.2. Допустимые

* page objects для повторяемых экранов:

  * `LoginPage`
  * `RegisterPage`
  * `VerifyEmailPage`
  * `DashboardPage`

### 9.3. Нежелательные

* page objects для каждого экрана без повторного использования;
* один глобальный `global-setup.ts`, который создаёт shared-user для всего test suite;
* хардкод таймингов и слепые sleep-задержки.

---

## 10. Требования к инфраструктуре

### 10.1. Режимы запуска

#### Локальный режим

Playwright может использовать `webServer` для запуска приложений, если сервисы не подняты заранее.

#### Docker/CI режим

В docker-compose приложения поднимаются отдельно, а Playwright только ждёт их готовности и выполняет тесты.

#### Обязательное правило

Нельзя одновременно делать Playwright ответственным и за orchestration сервисов, и за docker lifecycle в одном и том же режиме запуска.

### 10.2. Переменные окружения

В `e2e/.env.example` должны быть описаны:

```text
PLAYWRIGHT_BASE_URL=http://localhost:5138
PLAYWRIGHT_API_URL=http://localhost:8000
PLAYWRIGHT_DOCKER_BASE_URL=http://front:5138
PLAYWRIGHT_DOCKER_API_URL=http://web:8000
MAIL_CAPTURE_URL=http://mailpit:8025
PW_ENV_MODE=local
CI=false
```

### 10.3. Health-check и readiness

Перед стартом тестов необходимо проверять готовность:

* `front` — по base URL;
* `web` — по `/openapi.json` или dedicated health endpoint.

В текущем frontend контейнере `/openapi.json` уже проксируется в `web`, поэтому этот путь допустим как один из вариантов readiness-проверки. 

---

## 11. Захват verification code

### 11.1. Принятое решение

Основной способ получения verification code в тестовой среде — **Mailpit/MailHog в docker-compose**.

### 11.2. Почему выбран именно этот вариант

* backend verification flow уже построен вокруг email-отправки;
* в `web` уже есть SMTP-конфиг и email-сервис для verification/reset flows;
* такой подход не требует debug-веток в auth API;
* такой подход не требует читать код напрямую из БД;
* такой подход проверяет реальную интеграцию: генерацию кода, сохранение, отправку письма и использование кода.  

### 11.3. Что требуется реализовать

* добавить `mailpit` или `mailhog` в `docker-compose` test profile;
* направить SMTP-настройки `web` test profile на mail-capture сервис;
* реализовать helper `helpers/mail.ts`, который:

  * получает последнее письмо по email тестового пользователя;
  * извлекает verification code;
  * отдаёт код UI/API тестам.

### 11.4. Что не используется как основной паттерн

* возврат verification code из debug API response;
* прямое чтение verification code из MongoDB.

---

## 12. Подробная матрица сценариев

### 12.1. API auth-contract

#### Обязательные тесты

1. `register` создаёт пользователя и открывает авторизованную сессию.
2. `login` авторизует существующего пользователя.
3. `me` возвращает текущего пользователя при валидной сессии.
4. `me` возвращает `401` без сессии.
5. `logout` инвалидирует сессию.
6. после `logout` вызов `me` возвращает `401`.
7. `send-verification-code` отдаёт успешный ответ.
8. `verify-email` подтверждает email корректным кодом.

#### Дополнительные контрактные тесты

1. проверка cookie attributes;
2. проверка повторного использования сессии в новом контексте;
3. проверка корректного поведения CORS/auth endpoints на базовом уровне, если это важно для среды запуска.

### 12.2. UI auth-flow

#### Гостевой доступ

1. гость открывает `/#/dashboard`;
2. происходит редирект на `/#/login`;
3. после успешного логина пользователь попадает в `/#/dashboard`.

#### Логин существующего пользователя

1. открыть `/#/login`;
2. ввести валидные credentials;
3. перейти в dashboard;
4. проверить ключевой элемент страницы.

#### Регистрация нового пользователя

1. открыть `/#/register`;
2. ввести email/password/confirm_password;
3. проверить переход в verify-email flow или эквивалентный фактической логике приложения экран;
4. запросить или использовать verification code;
5. завершить сценарий подтверждения email;
6. попасть в dashboard.

#### Подтверждение email

1. получить verification code через mail-capture;
2. открыть `/#/verify-email?email=...`;
3. ввести код;
4. перейти в dashboard или эквивалентное authenticated состояние.

#### Logout

1. открыть authenticated session;
2. выполнить logout;
3. проверить очистку auth-state;
4. попытка открыть protected route должна отправлять на login.

### 12.3. Smoke-регрессия

#### Публичные страницы

* главная страница;
* FAQ;
* API docs;
* загрузка документации.

#### Формы

* форма контактов;
* модальная заявка;
* заявка из калькулятора.

#### Auth smoke

* login;
* dashboard.

---

## 13. Требования к качеству реализации

### 13.1. Надёжность

* каждый тест независим;
* тесты не должны зависеть от порядка выполнения;
* уникальные email генерируются автоматически;
* состояние между тестами не разделяется без явного основания;
* flaky-паттерны должны быть исключены.

### 13.2. Поддерживаемость

* локаторы должны использовать `getByRole`, `getByLabelText` или устойчивые `data-testid`, если роль нестабильна;
* селекторы по CSS использовать только когда семантический локатор невозможен;
* helpers и page objects не должны скрывать важную бизнес-логику;
* README обязателен.

### 13.3. Наблюдаемость

В конфигурации Playwright должны быть включены:

* `trace: 'on-first-retry'`
* `screenshot: 'only-on-failure'`
* `video: 'retain-on-failure'`
* HTML report
* JUnit XML report для CI

### 13.4. Производительность

* API тесты должны выполняться отдельно от UI;
* smoke-набор должен быть быстрым и пригодным для каждого CI прогона;
* более тяжёлые auth-flow можно маркировать отдельно;
* workers/retries должны настраиваться через env.

---

## 14. Требования к миграции текущего smoke

1. `front/scripts/browser-smoke.cjs` не удалять до тех пор, пока новое Playwright smoke-покрытие не достигнет функционального паритета.
2. После достижения паритета:

   * либо удалить старый скрипт;
   * либо пометить deprecated и оставить как временный fallback.
3. Миграция считается завершённой только если новый Playwright smoke покрывает минимум:

   * главную;
   * FAQ;
   * API docs;
   * download;
   * contacts form;
   * modal lead;
   * calculator lead;
   * login → dashboard. 

---

## 15. Интеграция в Docker Compose

### 15.1. Принятое решение

Целевой вариант — **отдельный сервис `e2e-runner`**, а не переиспользование `front-smoke` как основного имени.

### 15.2. Обоснование

В текущем compose уже есть раздельные тестовые сервисы по ответственности: `front-test`, `backend-test`, `front-smoke`. Новый Playwright-контур будет покрывать не только frontend smoke, но и API auth, UI auth и regression smoke, поэтому отдельный `e2e-runner` лучше соответствует текущей архитектуре и будущему росту тестового набора. 

### 15.3. Целевой вариант

Рекомендуется выделить новый сервис:

```text
e2e-runner
```

который:

* запускается только под `profile: test`;
* ждёт готовности `front`, `web` и mail-capture сервиса;
* выполняет Playwright suite;
* возвращает корректный exit code.

### 15.4. Переходный компромисс

`front-smoke` может быть сохранён временно как legacy/fallback сервис на период миграции, но не является целевой архитектурой.

---

## 16. Этапы реализации

### Фаза 1. Подготовка инфраструктуры

**Приоритет:** Высокий

#### 1.1. Создать корневой `e2e/` workspace

**Результат:** отдельный package, playwright config, tsconfig, README, env-example.

#### 1.2. Настроить базовый Playwright config

**Результат:** projects, reporters, artifacts, retries/workers, base URL, storageState.

#### 1.3. Реализовать helpers и fixtures

**Результат:** генерация данных, API helper, route helper, service readiness helper, mail helper.

#### 1.4. Настроить setup projects

**Результат:** health-check setup и authenticated setup без глобального shared-user.

### Фаза 2. Реализовать API auth-contract тесты

**Приоритет:** Высокий

#### 2.1. Register/Login/Me/Logout

**Результат:** минимальный contract suite на реальные endpoints.

#### 2.2. Verification endpoints

**Результат:** send-verification-code и verify-email покрыты happy-path сценариями.

#### 2.3. Cookie/session contract

**Результат:** проверка открытия, использования и инвалидирования сессии.

### Фаза 3. Реализовать UI auth-flow тесты

**Приоритет:** Высокий

#### 3.1. Guest → protected route → login

**Результат:** сценарий покрыт через реальный браузер.

#### 3.2. Existing user login

**Результат:** логин и переход в dashboard покрыты.

#### 3.3. Register → verify-email → dashboard

**Результат:** сквозной сценарий регистрации и верификации работает через mail-capture.

#### 3.4. Logout flow

**Результат:** пользователь теряет доступ к protected pages после logout.

### Фаза 4. Перенести текущий browser smoke

**Приоритет:** Средний

#### 4.1. Публичные страницы

**Результат:** main/faq/api-docs перенесены в Playwright specs.

#### 4.2. Формы и калькулятор

**Результат:** contacts, modal lead, calculator lead перенесены.

#### 4.3. Auth smoke

**Результат:** login → dashboard перенесён из старого smoke.

#### 4.4. Вывести старый smoke в deprecated

**Результат:** старый скрипт отключён только после достижения паритета.

### Фаза 5. Docker и CI

**Приоритет:** Средний

#### 5.1. Добавить `e2e-runner`

**Результат:** запуск в docker profile `test`.

#### 5.2. Добавить mail-capture сервис

**Результат:** стабильное получение verification code в тестах.

#### 5.3. Добавить отчёты и артефакты

**Результат:** HTML, JUnit, trace, screenshots.

#### 5.4. Описать процесс запуска

**Результат:** README с локальным, docker и CI сценариями.

### Фаза 6. Следующая итерация

**Приоритет:** Низкий

#### 6.1. Reset-password flow

**Результат:** сценарии `forgot-password` / `reset-password` будут добавлены отдельной фазой после внедрения core auth E2E.

---

## 17. Команды запуска

### 17.1. Локально

```bash
cd e2e
npm ci
npx playwright test
```

### Выборочно

```bash
npx playwright test tests/api/auth.contract.spec.ts
npx playwright test tests/ui/auth.login.spec.ts
npx playwright test tests/smoke/public-pages.spec.ts
```

### 17.2. В Docker

```bash
docker compose --profile test up --build --exit-code-from e2e-runner e2e-runner
```

---

## 18. Критерии приёмки (Definition of Done)

* [ ] Создан отдельный `e2e/` workspace с Playwright Test Runner.
* [ ] Реализованы независимые наборы `api`, `ui`, `smoke`.
* [ ] Покрыты сценарии `register`, `login`, `me`, `logout`, `verify-email` на интеграционном уровне.
* [ ] Покрыт сценарий `guest → protected route → login → dashboard`.
* [ ] Покрыт сценарий `register → verify-email → dashboard`.
* [ ] После `logout` доступ к protected routes отсутствует.
* [ ] Новый Playwright smoke не уступает по покрытию текущему `browser-smoke.cjs`.
* [ ] Тесты проходят в headless режиме без ручного вмешательства.
* [ ] Тесты не используют shared mutable auth-state между независимыми spec-файлами.
* [ ] В тестовом docker profile используется mail-capture для verification flow.
* [ ] Нет необоснованных `waitForTimeout`.
* [ ] Доступны HTML report, JUnit report, traces на retry/failure.
* [ ] Тесты запускаются как локально, так и через docker profile `test`.
* [ ] `README.md` описывает запуск, отладку, артефакты и типовые причины падений.

---

## 19. Риски и стратегия снижения

| Риск                                                            | Влияние                        | Стратегия                                                        |
| --------------------------------------------------------------- | ------------------------------ | ---------------------------------------------------------------- |
| Отсутствует стабильный способ получить verification code        | Блокирует full E2E verify flow | Использовать Mailpit/MailHog как обязательную часть test profile |
| Попытка дублировать pytest негативные матрицы в Playwright      | Рост стоимости поддержки       | Ограничить Playwright API уровнем contract/integration           |
| Общий пользователь в setup ломает параллельность и logout tests | Flaky и межтестовая связность  | Использовать setup project и изолированные storage states        |
| Миграция smoke урежет существующее покрытие                     | Потеря контроля над продуктом  | Зафиксировать обязательный parity checklist                      |
| Hash-router assertions будут написаны как обычные path routes   | Ложные падения UI tests        | Ввести route helpers и явно проверять `/#/...`                   |
| Избыточный POM создаст сложность без выгоды                     | Замедление поддержки           | Использовать POM только для повторяемых auth/public экранов      |
| Docker и Playwright будут одновременно управлять сервисами      | Нестабильные прогоны           | Развести local orchestration и docker orchestration              |

---

## 20. Ожидаемые артефакты по результату работ

1. каталог `e2e/` с полной структурой;
2. Playwright config и setup projects;
3. API auth-contract suite;
4. UI auth-flow suite;
5. smoke suite;
6. docker-compose интеграция;
7. mail-capture интеграция;
8. README;
9. пример CI запуска;
10. deprecation plan для `browser-smoke.cjs`.

---

## 21. Остаточные открытые вопросы

1. Нужен ли отдельный публичный `GET /healthz` в `web`, или достаточно `/openapi.json`/существующих health-check механизмов через compose proxy?
2. Требуется ли обязательная очистка тестовых пользователей после прогона, или в рамках проекта достаточно стратегии уникальных email?
3. Нужна ли обратная совместимость CI по имени старого smoke job/service на переходный период?

---

## 22. Итоговое решение

В рамках данной задачи необходимо не просто “добавить Playwright”, а внедрить отдельный интеграционный слой тестирования между уже существующими Vitest и pytest наборами.

Этот слой должен:

* проверять реальную работу авторизации;
* покрывать protected routes и пользовательские auth-flow;
* сохранять текущее smoke-покрытие публичной части;
* запускаться локально и в Docker;
* использовать mail-capture для verify-email flow;
* быть пригодным для CI без ручного вмешательства и без хрупких time-based ожиданий.
