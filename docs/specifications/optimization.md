Ниже — hypothesis-driven performance audit по вашему JSON-снимку архитектуры. Он опирается на то, что фронтенд — это React 19 + TypeScript + Vite SPA с React Router, Tailwind, Radix UI, глобальными `AuthProvider` / `ThemeProvider` / `I18nProvider`, lazy loading и protected dashboard-маршрутами вроде `/dashboard`, `/dashboard/deals`, `/dashboard/deals/:id`, `/dashboard/settings`, `/dashboard/new-deal`. Также в проекте есть формы сделок, документы, whitelist/limits и auth-flows. 

## Ключевой вывод

Наибольший ожидаемый выигрыш здесь даст не “микрооптимизация React”, а снижение количества лишних commit/render wave на уровне app shell и dashboard-flow:

1. стабилизация глобальных providers;
2. разбиение Suspense/lazy boundaries по маршрутам и крупным секциям;
3. локализация горячего state внутри форм и таблиц;
4. устранение forced reflow в анимациях, sticky/layout-компонентах и upload/status UI;
5. CSS containment + `content-visibility` для тяжёлых dashboard-секций.

Это соответствует ограничениям: без изменения публичных API компонентов, без смены state/routing/data fetching, без потери анимаций и без Big Bang рефакторинга.

---

## Где здесь с наибольшей вероятностью рождается jank

С учётом структуры SPA и доменной модели, я бы ранжировал риски так:

### 1) Глобальные provider-driven rerender cascades

В приложении уже есть cross-cutting слой из `AuthProvider`, `ThemeProvider`, `I18nProvider` и route guard. В таких схемах главный риск — изменение одного value в provider триггерит лишний ререндер большой части дерева, включая dashboard/layout/sidebar/forms. 

**Типичные симптомы**

* лаг при login/logout/refresh session;
* дёргание dashboard shell при смене языка/темы;
* повторные renders protected routes при любой auth-related проверке;
* “вроде всё мемоизировано, но страницы всё равно тяжёлые”.

**Что делать**

* сделать `value` каждого provider referentially stable через `useMemo`;
* не передавать в context каждый render новые object/function literals;
* разделить context по частоте обновления: session / permissions / ui prefs / i18n readiness;
* в provider убрать тяжёлые derived values из render path;
* если внутри есть polling/refresh token/status checks — выносить их обновления из широкого дерева в более узкие подписки.

Это не меняет внешний API компонентов, только внутреннюю организацию provider values.

---

### 2) Dashboard-маршруты как главная зона long tasks

По набору маршрутов видно, что горячий путь — это deal list, deal detail, settings, new deal, плюс связанные списки/документы/лимиты. Такие экраны обычно страдают от:

* одновременного mount большого количества карточек/таблиц;
* синхронных derived calculations;
* modal/popover/dropdown из Radix;
* прогресса загрузок/статусов, который слишком часто обновляет родительский layout. 

**Что делать в первую очередь**

* поставить отдельные `Suspense` boundaries на route shell, основную контентную колонку и вторичные панели;
* не монтировать тяжёлые секции “на всякий случай”, а lazy-load по route/intent;
* в списках сделок мемоизировать row/card components и стабилизировать callbacks;
* throttle для upload/status/progress updates до 80–120 мс;
* второстепенные вычисления переводить в `startTransition`, а фильтры/поиск — через `useDeferredValue`.

---

### 3) New deal / settings формы — вероятный источник input latency

В домене есть whitelist, quotas, warnings, documents, reset/verification и draft/submit сценарии. Это типичный профиль формы, где при каждом `onChange` легко получить:

* полную перерисовку всей формы;
* мгновенный пересчёт предупреждений/лимитов;
* layout shift из-за динамических helper/error blocks;
* forced layout при auto-resize textareas, step transitions, accordion sections. 

**Что делать**

* локализовать state по секциям формы, а не держать всё в одном верхнем контейнере;
* expensive validation считать отложенно;
* helper/error areas резервировать по высоте, чтобы не было CLS;
* для auto-grow textarea разделить read/write по кадрам: сначала measurement, потом style write через `requestAnimationFrame`;
* draft autosave не привязывать к каждому keystroke напрямую: debounce + cancel stale work.

---

### 4) Анимации и переходы: риск layout thrashing, не сами анимации

У вас есть жёсткое требование сохранить все текущие анимации и transitions. Значит цель — не убирать motion, а перевести его в compositor-friendly path.

**Что почти наверняка стоит проверить**

* анимации `height`, `width`, `top`, `left`, `margin`, `box-shadow`, `filter`;
* аккордеоны/expand panels;
* sticky headers с синхронным измерением размеров;
* Radix Dialog/Popover/Dropdown при открытии/закрытии;
* scroll-lock и компенсация scrollbar width.

**Целевое правило**

* анимировать `transform` и `opacity`;
* где нужен “рост по высоте” — делать single-measure FLIP-style sequence, а не читать/писать layout несколько раз за тик;
* `will-change` включать только на короткое время перед анимацией, не держать глобально;
* backdrop blur и тяжёлые shadows применять очень избирательно.

---

### 5) Rendering cost ниже fold-а

Dashboard/settings/detail pages почти наверняка содержат секции, которые видны не сразу: истории, документы, вторичные карточки, support/activity blocks.

**Быстрый выигрыш**

* `content-visibility: auto;`
* `contain-intrinsic-size: ...`
* `contain: layout paint;` для изолированных виджетов/карточек/панелей

Это один из лучших способов уменьшить initial render cost без изменения UX. Особенно полезно для long dashboards и details pages.

---

## Приоритетный план внедрения

## Этап 0. Измерение до изменений

Без этого легко “оптимизировать” не то.

Ввести:

* Web Vitals: LCP, CLS, INP;
* route-transition marks: `route:start`, `route:data-ready`, `route:paint`;
* interaction marks для:

  * open deal details,
  * typing in new deal form,
  * add/remove whitelist row,
  * upload document,
  * open modal/dropdown;
* React Profiler на:

  * App shell,
  * dashboard layout,
  * deal list,
  * new deal form,
  * settings/document sections.

**Минимальные целевые бюджеты**

* INP на dashboard < 200 мс;
* long task > 50 мс во время typing — стремиться к нулю;
* route transition до meaningful paint < 150–250 мс на тёплом кэше;
* CLS < 0.05;
* не более 1 forced reflow на пользовательское действие в горячих сценариях.

---

## Этап 1. Самые дешёвые high-ROI улучшения

Это можно внедрить почти без риска.

### A. Stabilize provider values

* `useMemo` / `useCallback` для provider values;
* убрать inline object/function creation из provider render;
* разнести редко и часто меняющиеся поля по разным contexts.

### B. Route-level isolation

* отдельные `Suspense` boundaries по protected routes;
* skeleton с фиксированной геометрией вместо “прыгающих” loaders;
* preload вероятных следующих роутов:

  * после login;
  * при hover/focus на sidebar nav;
  * при idle.

### C. CSS containment

* `contain: layout paint` на deal cards, side panels, settings sections;
* `content-visibility: auto` на ниже-fold секциях;
* `contain-intrinsic-size` чтобы не было резкого схлопывания/всплытия.

### D. Progress/status throttling

* upload progress и фоновые статусы обновлять не чаще ~10 раз/сек;
* не поднимать progress state слишком высоко по дереву.

---

## Этап 2. Горячие интерактивные места

### A. Формы

* разделить форму на memoized section components;
* derived quota/warning logic вычислять отложенно;
* второстепенные обновления — в transition;
* сохранять стабильный DOM footprint для error/help blocks.

### B. Списки

* memo row/card;
* стабильные `key`;
* не пересоздавать formatter/mapper/callback chains внутри render;
* если список реально большой — windowing/virtualization только за внутренним фасадом текущего компонента, чтобы не ломать API и UX.

### C. Документы/preview

* image decode вне критического пути;
* previews lazy-mount;
* progress bar/metadata updates не должны вызывать перерасчёт всей страницы.

---

## Этап 3. Motion pipeline cleanup

### Проверить и заменить

* `height` animations → measured FLIP/open-close sequence;
* animated shadows/filters → opacity/transform equivalents;
* sticky calculations in scroll handlers → passive listeners + rAF batching;
* read/write DOM access смешанные в одном effect/handler → сначала все reads, потом all writes.

### Практическое правило

Если компонент:

1. читает `offsetHeight/getBoundingClientRect`,
2. потом пишет `style/class`,
3. потом снова читает layout
   — это почти гарантированный кандидат на thrash.

---

## Что я бы сделал по конкретным зонам приложения

### App shell

* sidebar/header/dashboard layout обернуть в более стабильные memoized boundaries;
* theme switch должен менять только root-class/data-attribute, не прокидывать тяжёлые style-объекты вниз;
* i18n: не создавать новый `t` wrapper на каждый render, кешировать namespace lookups.

### `/dashboard/deals`

* карточки/строки изолировать через memo + contain;
* фильтрацию/сортировку делать отложенно;
* badges/status chips не должны триггерить full-list rerender;
* если есть expandable rows — анимировать transform/opacity, не layout на каждом кадре.

### `/dashboard/deals/:id`

* secondary panes (history, docs, support) загружать/монтировать отдельно;
* ниже-fold контент — через `content-visibility`;
* download/upload UI изолировать, чтобы прогресс не перерисовывал весь detail view.

### `/dashboard/new-deal`

* по секциям: реквизиты / whitelist / limits / docs / review;
* warnings и quota indicators считать асинхронно относительно typing;
* textarea/upload widgets — особый аудит на forced reflow.

### `/dashboard/settings`

* tabs/sections lazy-mount;
* whitelist rows memoized;
* подтверждения/modals на Radix — проверить scroll-lock и mount cost.

---

## Что даст заметный perceived-performance эффект без смены UX

1. **Intent-based preloading**
   Подгружать chunk следующего наиболее вероятного экрана заранее:

   * login → dashboard,
   * dashboard → deals/new-deal/settings,
   * hover/focus nav item → preload chunk.

2. **Скелетоны с фиксированной геометрией**
   Не просто loader, а сохранение будущих размеров контента.

3. **Отложенные второстепенные обновления**
   Пользовательский input должен побеждать пересчёты warning/status/hint UI.

4. **Изоляция тяжёлых секций**
   Большая часть dashboard jank исчезает, когда соседние панели перестают участвовать в каждом layout/repaint.

---

## Что не стоит делать

* не размазывать `React.memo` везде подряд без профилирования;
* не держать `will-change` на постоянной основе;
* не анимировать “удобные” CSS-свойства, если они layout-triggering;
* не добавлять тяжёлую виртуализацию заранее, пока не доказано, что списки действительно большие;
* не решать input lag через глобальный debounce всего UI — это ломает perceived responsiveness.

---

## Признаки, что стратегия сработала

Через профилирование вы должны увидеть:

* меньше commit’ов от App/Providers при локальных действиях;
* при вводе в форму перерисовывается только секция поля, а не весь page shell;
* route transition разбивается на несколько коротких коммитов вместо одного тяжёлого;
* открытие modal/dropdown/accordion не создаёт цепочку forced reflow;
* upload/status updates не двигают layout всей страницы.

---

## Практический порядок внедрения

1. Instrumentation + React Profiler baselines
2. Provider stabilization
3. Suspense/route boundary cleanup
4. CSS containment/content-visibility
5. Form section isolation
6. List row memoization
7. Animation/reflow audit
8. Intent preloading
9. Только потом — точечная virtualization, если она действительно нужна

---

Важное ограничение: из JSON видно стек, маршруты и доменные зоны, но не видно реального кода компонентов, эффектов, анимаций и паттернов state updates, поэтому конкретные точки thrashing здесь приоритизированы по архитектурному риску, а не по runtime trace. Дополнительно в репозитории есть documentation/spec drift, так что опираться надо именно на фактический React/Vite SPA слой, а не на старые описания. 

