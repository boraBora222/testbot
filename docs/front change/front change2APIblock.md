Техническое задание: Компонент TrustBlock
1. Общие сведения
1.1. Назначение документа
Настоящее техническое задание определяет требования к разработке React-компонента TrustBlock — блока социального доказательства для landing page B2B-криптообменника.
1.2. Цель компонента
Замена технического блока APIPreview на бизнес-ориентированную секцию доверия, повышающую конверсию для юридических лиц.
1.3. Стек технологий
React 18+
TypeScript
Tailwind CSS
Framer Motion (анимации)
Lucide React (иконки)
2. Функциональные требования
2.1. Структура компонента
plain
Copy
TrustBlock
├── Section Header (заголовок + подзаголовок)
├── Two-Column Grid
│   ├── Column 1: TestimonialCard (карусель отзывов)
│   │   ├── Avatar Block (фото + статус)
│   │   ├── Person Info (имя + должность)
│   │   ├── Company Info (название + тип)
│   │   ├── Deal Info Bar (дата + сумма + тип операции)
│   │   ├── Rating Block (звёзды + текст)
│   │   ├── Quote Block (текст отзыва)
│   │   ├── Progress Bar (индикатор авто-ротации)
│   │   └── Controls (навигация + точки + счётчик)
│   └── Column 2: SecurityColumn
│       ├── Security Items (4 элемента)
│       └── Stats Card (статистика)
└── Decorative Elements (градиенты)
2.2. Компонент TestimonialCard
2.2.1. Данные отзыва (Testimonial Interface)
TypeScript
Copy
interface Testimonial {
  id: number;              // Уникальный идентификатор
  name: string;            // ФИО клиента
  role: string;            // Должность
  company: string;         // Название компании
  companyType: string;     // Тип деятельности компании
  avatar: string;          // URL фото (рекомендуется 300x300)
  date: string;            // Дата сделки (формат: "DD месяц YYYY")
  amount: string;          // Сумма операции (с валютой)
  type: string;            // Тип операции (например, "USDT → ₽")
  rating: number;          // Рейтинг (1-5)
  text: string;            // Текст отзыва
}
2.2.2. Массив данных (минимум 5 отзывов)
Table
Поле	Пример значения
name	"Александр Петров"
role	"Финансовый директор"
company	"ООО «ТехноИмпорт»"
companyType	"Импорт электроники"
avatar	"https://i.pravatar.cc/300?img=11"
date	"15 марта 2025"
amount	"₽2,450,000"
type	"USDT → ₽"
rating	5
text	"Надежный партнер для импортных операций..."
2.2.3. Блок аватара
Требования:
Размер: 100×100px
Border radius: 24px
Border: 3px solid с цветом --surface-raised
Объект-fit: cover
Статус онлайн: зелёный круг (16px) с glow-эффектом в правом нижнем углу
Glow-эффект при hover на всю карточку
Hover-эффект:
Border color меняется на --accent-primary
Box-shadow: 0 0 30px rgba(99, 102, 241, 0.3)
2.2.4. Информация о человеке
Имя:
Font size: 24px (1.5rem)
Font weight: 700 (bold)
Letter spacing: -0.01em
Бейдж "Проверено":
Background: rgba(34, 197, 94, 0.1)
Border: 1px solid rgba(34, 197, 94, 0.2)
Border radius: 20px
Padding: 5px 12px
Font size: 12px
Color: #22c55e
Иконка: CheckCircle (12px)
Текст: "ПРОВЕРЕНО" (uppercase)
Должность:
Font size: 16px
Color: --text-secondary
2.2.5. Информация о компании
Бейдж компании:
Background: --surface-raised
Border: 1px solid --border-default
Border radius: 10px
Padding: 8px 14px
Иконка: Building2 (20px, цвет --accent-primary)
Тип компании:
Font size: 12px
Color: --text-tertiary
Отступ слева: 4px
2.2.6. Панель информации о сделке (Deal Info Bar)
Контейнер:
Background: --bg-emphasis
Border radius: 16px
Padding: 16px 20px
Display: flex
Gap: 16px
Flex-wrap: wrap
Элемент сделки:
Иконка в круге: 36×36px, background --surface-raised, border radius 10px
Label: 11px, uppercase, letter-spacing 0.08em, color --text-tertiary
Value: 15px, font-weight 600, color --text-primary
Сумма выделена цветом --accent-primary
Три обязательных поля:
Дата сделки (иконка Calendar)
Сумма операции (иконка Banknote)
Тип операции (иконка ArrowLeftRight)
2.2.7. Рейтинг
Звёзды:
Размер: 20×20px
Заполненные: цвет #fbbf24, fill currentColor
Пустые: цвет --text-tertiary
Gap: 4px
Текст рейтинга:
Font size: 14px
Color: --text-secondary
Текст: "Отличный сервис"
2.2.8. Блок цитаты
Контейнер:
Background: --bg-emphasis
Border radius: 20px
Padding: 24px
Border-left: 4px solid --accent-primary
Иконка кавычек:
Размер: 48×48px
Position: absolute, top 16px, right 20px
Color: --accent-primary
Opacity: 0.2
Текст:
Font size: 18px
Line height: 1.8
Color: --text-secondary
Font style: italic
2.2.9. Прогресс-бар авто-ротации
Контейнер:
Position: absolute, bottom 0, left 0, right 0
Height: 4px
Background: --border-default
Заполнение:
Background: linear-gradient(90deg, --accent-primary, --accent-secondary)
Анимация: linear, обновление каждые 100ms
Длительность полного цикла: 10 секунд
2.2.10. Элементы управления
Контейнер:
Margin top: 28px
Padding top: 24px
Border top: 1px solid --border-default
Display: flex
Justify-content: space-between
Align-items: center
Кнопки навигации:
Размер: 48×48px
Background: --surface-raised
Border: 1px solid --border-default
Border radius: 14px
Иконки: ChevronLeft / ChevronRight (22px)
Hover:
Background: --accent-primary
Color: white
Border color: --accent-primary
Transform: translateY(-2px)
Точки (dots):
Неактивная: 12×12px, --text-tertiary
Активная: 36×12px, border radius 6px, градиент
Transition: 0.4s cubic-bezier(0.16, 1, 0.3, 1)
Счётчик:
Font size: 14px
Color: --text-tertiary
Текущий номер: --text-primary, font-weight 700
3. Анимации
3.1. Тайминги
Table
Элемент	Длительность	Easing
Смена отзыва	500ms	cubic-bezier(0.16, 1, 0.3, 1)
Hover карточки	500ms	cubic-bezier(0.16, 1, 0.3, 1)
Hover кнопки	300ms	cubic-bezier(0.16, 1, 0.3, 1)
Прогресс-бар	100ms linear	linear
Появление секции	900ms	cubic-bezier(0.16, 1, 0.3, 1)
3.2. Анимация градиентной полосы
css
Copy
@keyframes gradientShift {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}
/* animation: gradientShift 3s ease infinite */
3.3. Hover-эффекты
Карточка отзыва:
Border color: rgba(99, 102, 241, 0.25)
Box-shadow: --shadow-layer + --shadow-glow
Transform: translateY(-4px)
Аватар:
Border color: --accent-primary
Box-shadow: 0 0 30px rgba(99, 102, 241, 0.3)
4. Визуальный стиль
4.1. CSS-переменные
css
Copy
:root {
  --bg-default: #050508;
  --bg-subtle: #0a0a0f;
  --bg-emphasis: #12121a;
  --surface-default: #161620;
  --surface-raised: #1e1e2d;
  --surface-hover: #262636;
  --text-primary: #ffffff;
  --text-secondary: #a1a1b5;
  --text-tertiary: #6b6b80;
  --accent-primary: #6366f1;
  --accent-secondary: #a855f7;
  --accent-glow: rgba(99, 102, 241, 0.2);
  --border-default: rgba(255, 255, 255, 0.06);
  --shadow-layer: 0 8px 32px rgba(0, 0, 0, 0.5);
  --shadow-glow: 0 0 60px rgba(99, 102, 241, 0.15);
  --success: #22c55e;
  --success-bg: rgba(34, 197, 94, 0.1);
}
4.2. Типографика
Table
Элемент	Размер	Вес	Цвет
Заголовок секции	48px	700	--text-primary
Подзаголовок	18px	400	--text-secondary
Имя клиента	24px	700	--text-primary
Должность	16px	400	--text-secondary
Текст отзыва	18px	400	--text-secondary
Label сделки	11px	400	--text-tertiary
Value сделки	15px	600	--text-primary
4.3. Декоративные элементы
Градиент справа:
Position: absolute, top -200px, right -200px
Size: 800×800px
Background: radial-gradient(circle, rgba(99, 102, 241, 0.08), transparent 55%)
Filter: blur(100px)
Градиент слева:
Position: absolute, bottom -200px, left -200px
Size: 600×600px
Background: radial-gradient(circle, rgba(168, 85, 247, 0.06), transparent 55%)
Filter: blur(100px)
5. Security Column
5.1. Заголовок
Иконка: ShieldCheck в градиентном круге (40×40px)
Текст: "Безопасность"
5.2. Элементы безопасности
Table
Иконка	Заголовок	Описание
Shield	SSL-шифрование	Все транзакции защищены 256-битным шифрованием
FileCheck	Соответствие 115-ФЗ	Полное соответствие требованиям AML/KYC
Scale	Юридическое сопровождение	Поддержка на всех этапах сделки
Award	0 инцидентов	С 2024 года безупречная работа
Hover:
Transform: translateX(6px)
Background: --surface-raised
Border color: rgba(99, 102, 241, 0.2)
5.3. Карточка статистики
Данные:
10K+ Операций
₽500M Объем
4.9 Рейтинг
Стили:
Background: градиент 145deg
Border radius: 20px
Значения: градиентный текст
6. Поведение
6.1. Авто-ротация
Интервал: 10 секунд
Пауза при наведении на карточку
Возобновление при уходе курсора
6.2. Ручная навигация
Кнопки вперёд/назад
Клик по точкам
Сброс таймера при ручной навигации
6.3. Адаптивность
Desktop (≥1024px):
Grid: 1.4fr 0.6fr
Gap: 48px
Tablet (<1024px):
Grid: 1fr (одна колонка)
Отзывы сверху, безопасность снизу
Mobile (<640px):
Padding: 16px
Avatar: 80×80px
Deal Info Bar: вертикальный стек
7. Интеграция
7.1. Импорты
TypeScript
Copy
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Shield, FileCheck, Award, Quote, Star, Scale,
  ChevronLeft, ChevronRight, ShieldCheck, CheckCircle,
  Building2, Calendar, Banknote, ArrowLeftRight, Users
} from 'lucide-react';
7.2. Props компонента
TypeScript
Copy
interface TrustBlockProps {
  testimonials?: Testimonial[];  // Массив отзывов (опционально, есть дефолт)
  autoRotateInterval?: number;    // Интервал в мс (default: 10000)
  showProgressBar?: boolean;      // Показывать прогресс-бар (default: true)
}
7.3. Использование
tsx
Copy
import { TrustBlock } from './components/TrustBlock';

function App() {
  return (
    <main>
      {/* ... другие секции ... */}
      <TrustBlock />
      {/* ... другие секции ... */}
    </main>
  );
}
8. Критерии приёмки
8.1. Обязательные требования
[ ] Компонент отображает минимум 5 отзывов
[ ] Аватары имеют размер 100×100px
[ ] Панель сделки содержит дату, сумму и тип операции
[ ] Указан тип деятельности компании
[ ] Есть бейдж "Проверено"
[ ] Авто-ротация работает (10 сек)
[ ] Пауза при наведении
[ ] Прогресс-бар отображается
[ ] Анимации соответствуют ТЗ
[ ] Адаптивность работает
8.2. Нефункциональные требования
[ ] Нет TypeScript ошибок
[ ] Нет console.warn/error
[ ] Lighthouse Performance ≥ 90
[ ] Корректная работа в Chrome, Firefox, Safari
9. Макеты и референсы
9.1. Демо-версия
URL: https://jhzqsmdopxdck.ok.kimi.link
9.2. Файлы
index.html — статическая версия
TrustBlock.tsx — React-компонент