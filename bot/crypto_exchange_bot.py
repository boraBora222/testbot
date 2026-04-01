import logging
from decimal import Decimal
from math import ceil
from pathlib import Path

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from .config import settings
from .exchange_logic import (
    calculate_order_preview,
    format_datetime_for_user,
    format_money,
    format_rate,
    get_available_from_currencies,
    get_available_to_currencies,
    get_exchange_type_label,
    get_network_currency,
    get_network_label,
    get_network_options,
    get_order_status_emoji,
    get_order_status_label,
    get_rates_snapshot,
    validate_address,
    validate_amount,
)
from .redis_client import get_redis_client, publish_message
from .states import ExchangeStates, SupportStates
from shared import db
from shared.models import OrderDB
from shared.types.enums import ExchangeType

logger = logging.getLogger(__name__)
router = Router(name="crypto_exchange")
CONTRACT_PLACEHOLDER_PATH = Path(__file__).resolve().parent / "assets" / "contract_placeholder.txt"

REPLY_MENU_BUTTONS = [
    "💱 Обмен",
    "📊 Курсы",
    "📋 Заявки",
    "👤 Профиль",
    "❓ Поддержка",
    "🌐 Сайт",
    "📄 Договор",
    "❌ Отмена",
]


async def _touch_user(user: types.User) -> None:
    await db.ensure_exchange_user(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )


def build_reply_main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💱 Обмен"),
                KeyboardButton(text="📊 Курсы"),
                KeyboardButton(text="📋 Заявки"),
            ],
            [
                KeyboardButton(text="👤 Профиль"),
                KeyboardButton(text="❓ Поддержка"),
                KeyboardButton(text="🌐 Сайт"),
            ],
            [
                KeyboardButton(text="📄 Договор"),
                KeyboardButton(text="❌ Отмена"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел...",
    )


def build_exchange_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Crypto -> Fiat", callback_data=f"exchange:type:{ExchangeType.CRYPTO_TO_FIAT.value}")],
            [InlineKeyboardButton(text="💵 Fiat -> Crypto", callback_data=f"exchange:type:{ExchangeType.FIAT_TO_CRYPTO.value}")],
            [InlineKeyboardButton(text="🔄 Crypto -> Crypto", callback_data=f"exchange:type:{ExchangeType.CRYPTO_TO_CRYPTO.value}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")],
        ]
    )


def build_currency_keyboard(currencies: tuple[str, ...], scope: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for currency in currencies:
        current_row.append(InlineKeyboardButton(text=currency, callback_data=f"exchange:{scope}:{currency}"))
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="exchange:back")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_network_keyboard(exchange_type: str, from_currency: str, to_currency: str) -> InlineKeyboardMarkup:
    network_currency = get_network_currency(exchange_type, from_currency, to_currency)
    rows = [
        [InlineKeyboardButton(text=option["label"], callback_data=f"exchange:network:{option['code']}")]
        for option in get_network_options(exchange_type, from_currency, to_currency)
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="exchange:back")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_back_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="← Назад", callback_data="exchange:back"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel"),
            ]
        ]
    )


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="exchange:confirm")],
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="exchange:edit")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")],
        ]
    )


def build_after_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Мои заявки", callback_data="orders:page:1"),
                InlineKeyboardButton(text="📊 Курсы", callback_data="menu:rates"),
            ],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
        ]
    )


def build_rates_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="menu:rates")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
        ]
    )


def build_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
                InlineKeyboardButton(text="❓ Поддержка", callback_data="menu:support"),
            ]
        ]
    )


def build_site_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть сайт", url=settings.front_base_url)],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")],
        ]
    )


def build_support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")]
        ]
    )


def build_orders_keyboard(orders: list[dict], page: int, total_pages: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for order in orders:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{order['order_id']} | {order['from_currency']} -> {order['to_currency']}",
                    callback_data=f"orders:detail:{order['order_id']}:{page}",
                )
            ]
        )

    navigation_row: list[InlineKeyboardButton] = []
    if page > 1:
        navigation_row.append(InlineKeyboardButton(text="← Назад", callback_data=f"orders:page:{page - 1}"))
    if page < total_pages:
        navigation_row.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"orders:page:{page + 1}"))
    if navigation_row:
        rows.append(navigation_row)
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_order_detail_keyboard(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="← Назад к списку", callback_data=f"orders:page:{page}"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
            ]
        ]
    )


async def _apply_message_rate_limit(user_id: int) -> bool:
    redis_client = get_redis_client()
    key = f"rate_limit:messages:{user_id}"
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, 60)
    return current <= 10


async def _apply_order_rate_limit(user_id: int) -> bool:
    redis_client = get_redis_client()
    key = f"rate_limit:orders:{user_id}"
    current = await redis_client.incr(key)
    if current == 1:
        await redis_client.expire(key, 3600)
    return current <= 3


def _build_main_menu_text() -> str:
    return "📋 Главное меню\n\nВыберите раздел:"


def _build_rates_text() -> str:
    lines = ["📊 Актуальные курсы (демо)", ""]
    for base, quote, rate in get_rates_snapshot():
        lines.append(f"{base} -> {quote}: {format_rate(rate, base, quote)}")
    lines.extend(
        [
            "",
            "⚠️ Курсы демонстрационные и могут отличаться от реальных.",
        ]
    )
    return "\n".join(lines)


def _build_amount_prompt(from_currency: str) -> str:
    return (
        "💰 Введите сумму для обмена\n\n"
        f"Минимум: {format_money(settings.min_exchange_amount_rub, 'RUB')}\n"
        f"Максимум: {format_money(settings.max_exchange_amount_rub, 'RUB')}\n\n"
        f"Сумма указывается в валюте списания: {from_currency}"
    )


def _build_address_prompt(exchange_type: str, from_currency: str, to_currency: str, network: str) -> str:
    address_target = to_currency if to_currency != "RUB" else "реквизиты"
    network_currency = get_network_currency(exchange_type, from_currency, to_currency)
    network_label = get_network_label(network_currency, network)
    return (
        "📍 Введите адрес кошелька или реквизиты для получения средств\n\n"
        f"Сеть: {network_label}\n"
        f"Получение: {address_target}"
    )


def _build_order_summary(data: dict) -> str:
    preview = calculate_order_preview(
        from_currency=data["from_currency"],
        to_currency=data["to_currency"],
        amount=Decimal(data["amount"]),
    )
    network_currency = get_network_currency(data["exchange_type"], data["from_currency"], data["to_currency"])
    network_label = get_network_label(network_currency, data["network"])
    return (
        "🧮 Расчёт обмена\n\n"
        f"Направление: {data['from_currency']} -> {data['to_currency']}\n"
        f"Тип: {get_exchange_type_label(data['exchange_type'])}\n"
        f"Сеть: {network_label}\n\n"
        f"Сумма: {format_money(Decimal(data['amount']), data['from_currency'])}\n"
        f"Курс: {format_rate(preview['rate'], data['from_currency'], data['to_currency'])}\n"
        f"К получению до комиссии: {format_money(preview['gross_receive_amount'], data['to_currency'])}\n"
        f"Комиссия ({settings.default_fee_percent}%): {format_money(preview['fee_amount'], data['to_currency'])}\n"
        f"Итого: {format_money(preview['receive_amount'], data['to_currency'])}\n\n"
        f"Адрес / реквизиты:\n{data['address']}\n\n"
        "⚠️ Курсы действительны 15 минут."
    )


def _build_order_detail_text(order: dict) -> str:
    return (
        f"📄 Заявка #{order['order_id']}\n\n"
        f"Статус: {get_order_status_emoji(order['status'])} {get_order_status_label(order['status'])}\n\n"
        f"Тип обмена: {get_exchange_type_label(order['exchange_type'])}\n"
        f"Направление: {order['from_currency']} -> {order['to_currency']}\n"
        f"Сеть: {order['network']}\n\n"
        f"Сумма: {format_money(order['amount'], order['from_currency'])}\n"
        f"Курс: {format_rate(order['rate'], order['from_currency'], order['to_currency'])}\n"
        f"Комиссия ({order['fee_percent']}%): {format_money(order['fee_amount'], order['to_currency'])}\n"
        f"К получению: {format_money(order['receive_amount'], order['to_currency'])}\n\n"
        f"Адрес / реквизиты:\n{order['address']}\n\n"
        f"Создана: {format_datetime_for_user(order['created_at'])}\n"
        f"Обновлена: {format_datetime_for_user(order['updated_at'])}"
    )


def _build_orders_list_text(orders: list[dict], page: int, total_pages: int) -> str:
    if not orders:
        return "📋 Ваши заявки\n\nПока заявок нет."
    lines = ["📋 Ваши заявки", ""]
    for order in orders:
        lines.extend(
            [
                f"#{order['order_id']} | {order['from_currency']} -> {order['to_currency']}",
                f"Сумма: {format_money(order['amount'], order['from_currency'])} | Статус: {get_order_status_emoji(order['status'])} {get_order_status_label(order['status'])}",
                format_datetime_for_user(order["created_at"]),
                "",
            ]
        )
    lines.append(f"Страница {page}/{total_pages}")
    return "\n".join(lines)


def _build_profile_text(user_doc: dict, total_orders: int, active_orders: int, materials_count: int) -> str:
    username = f"@{user_doc['username']}" if user_doc.get("username") else "-"
    full_name = " ".join(part for part in [user_doc.get("first_name"), user_doc.get("last_name")] if part) or "-"
    return (
        "👤 Профиль пользователя\n\n"
        f"Telegram ID: {user_doc['telegram_user_id']}\n"
        f"Username: {username}\n"
        f"Имя: {full_name}\n\n"
        f"Первый вход: {format_datetime_for_user(user_doc['first_seen_at'])}\n"
        f"Последняя активность: {format_datetime_for_user(user_doc['last_activity_at'])}\n\n"
        f"Заявок всего: {total_orders}\n"
        f"Активных: {active_orders}\n"
        f"Отправлено материалов: {materials_count}"
    )


async def show_main_menu(target: types.Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = _build_main_menu_text()
    keyboard = build_reply_main_menu_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_exchange_type(target: types.Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExchangeStates.selecting_type)
    text = "💱 Оформление заявки\n\nШаг 1. Выберите тип обмена."
    keyboard = build_exchange_type_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_from_currency(callback: CallbackQuery, state: FSMContext, exchange_type: str) -> None:
    await state.set_state(ExchangeStates.selecting_from_currency)
    await callback.message.edit_text(
        "Шаг 2. Выберите валюту списания.",
        reply_markup=build_currency_keyboard(get_available_from_currencies(exchange_type), "from"),
    )


async def _show_to_currency(callback: CallbackQuery, state: FSMContext, exchange_type: str, from_currency: str) -> None:
    await state.set_state(ExchangeStates.selecting_to_currency)
    await callback.message.edit_text(
        "Шаг 3. Выберите валюту получения.",
        reply_markup=build_currency_keyboard(get_available_to_currencies(exchange_type, from_currency), "to"),
    )


async def _show_network_step(callback: CallbackQuery, state: FSMContext, data: dict) -> None:
    await state.set_state(ExchangeStates.selecting_network)
    await callback.message.edit_text(
        "Шаг 4. Выберите сеть.",
        reply_markup=build_network_keyboard(data["exchange_type"], data["from_currency"], data["to_currency"]),
    )


async def _show_amount_step(target: types.Message | CallbackQuery, state: FSMContext, from_currency: str) -> None:
    await state.set_state(ExchangeStates.entering_amount)
    text = _build_amount_prompt(from_currency)
    keyboard = build_back_cancel_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_address_step(target: types.Message | CallbackQuery, state: FSMContext, data: dict) -> None:
    await state.set_state(ExchangeStates.entering_address)
    text = _build_address_prompt(data["exchange_type"], data["from_currency"], data["to_currency"], data["network"])
    keyboard = build_back_cancel_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_confirmation(target: types.Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExchangeStates.confirming)
    data = await state.get_data()
    text = _build_order_summary(data)
    keyboard = build_confirm_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


@router.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await show_main_menu(message, state)


@router.message(Command("exchange"))
@router.message(F.text == "💱 Обмен")
async def cmd_exchange(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    await _show_exchange_type(message, state)


@router.message(Command("rates"))
@router.message(F.text == "📊 Курсы")
async def cmd_rates(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await state.clear()
    await message.answer(_build_rates_text(), reply_markup=build_rates_keyboard())


@router.message(Command("orders"))
@router.message(F.text == "📋 Заявки")
async def cmd_orders(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await state.clear()
    orders, total = await db.list_orders_for_user(message.from_user.id, page=1, page_size=10)
    total_pages = max(ceil(total / 10), 1)
    await message.answer(
        _build_orders_list_text(orders, 1, total_pages),
        reply_markup=build_orders_keyboard(orders, 1, total_pages),
    )


@router.message(Command("profile"))
@router.message(F.text == "👤 Профиль")
async def cmd_profile(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await state.clear()
    user_doc = await db.get_exchange_user(message.from_user.id)
    if not user_doc:
        await message.answer("Профиль пока не найден. Используйте /start.")
        return
    total_orders = await db.count_orders_for_user(message.from_user.id)
    active_orders = await db.count_active_orders_for_user(message.from_user.id)
    materials_count = await db.count_materials_for_user(message.from_user.id)
    await message.answer(
        _build_profile_text(user_doc, total_orders, active_orders, materials_count),
        reply_markup=build_profile_keyboard(),
    )


@router.message(Command("support"))
@router.message(F.text == "❓ Поддержка")
async def cmd_support(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await state.set_state(SupportStates.waiting_message)
    await message.answer(
        "❓ Поддержка\n\nОпишите ваш вопрос или проблему.\nВы можете отправить текст, фото или документ.\n\nМенеджер ответит в рабочее время (9:00-18:00 МСК).",
        reply_markup=build_support_keyboard(),
    )


@router.message(F.text == "🌐 Сайт")
async def cmd_site(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await state.clear()
    await message.answer(
        "🌐 Сайт\n\nНажмите кнопку ниже, чтобы открыть сайт компании.",
        reply_markup=build_site_keyboard(),
    )


@router.message(F.text == "📄 Договор")
async def cmd_contract(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await state.clear()
    contract_file = FSInputFile(CONTRACT_PLACEHOLDER_PATH, filename="dogovor-placeholder.txt")
    await message.answer_document(
        contract_file,
        caption="📄 Договор\n\nПока отправляем временную заглушку. Позже заменим её документом из БД.",
        reply_markup=build_reply_main_menu_keyboard(),
    )


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await state.clear()
    await message.answer("Текущий сценарий отменён. Вы можете начать заново из меню.", reply_markup=build_reply_main_menu_keyboard())


@router.callback_query(F.data == "menu:main")
async def cb_menu_main(callback: CallbackQuery, state: FSMContext) -> None:
    await show_main_menu(callback, state)


@router.callback_query(F.data == "menu:rates")
async def cb_rates(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(_build_rates_text(), reply_markup=build_rates_keyboard())
    await callback.answer()


@router.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SupportStates.waiting_message)
    await callback.message.edit_text(
        "❓ Поддержка\n\nОпишите ваш вопрос или проблему.\nВы можете отправить текст, фото или документ.\n\nМенеджер ответит в рабочее время (9:00-18:00 МСК).",
        reply_markup=build_support_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:type:"))
async def cb_exchange_type(callback: CallbackQuery, state: FSMContext) -> None:
    exchange_type = callback.data.split(":")[-1]
    await state.update_data(exchange_type=exchange_type)
    await _show_from_currency(callback, state, exchange_type)
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:from:"))
async def cb_from_currency(callback: CallbackQuery, state: FSMContext) -> None:
    from_currency = callback.data.split(":")[-1]
    data = await state.get_data()
    exchange_type = data["exchange_type"]
    if from_currency not in get_available_from_currencies(exchange_type):
        await callback.answer("Неподдерживаемая валюта.", show_alert=True)
        return
    await state.update_data(from_currency=from_currency)
    await _show_to_currency(callback, state, exchange_type, from_currency)
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:to:"))
async def cb_to_currency(callback: CallbackQuery, state: FSMContext) -> None:
    to_currency = callback.data.split(":")[-1]
    data = await state.get_data()
    exchange_type = data["exchange_type"]
    from_currency = data["from_currency"]
    if to_currency == from_currency:
        await callback.answer("Валюта получения должна отличаться.", show_alert=True)
        return
    if to_currency not in get_available_to_currencies(exchange_type, from_currency):
        await callback.answer("Неподдерживаемая валюта.", show_alert=True)
        return
    await state.update_data(to_currency=to_currency)
    await _show_network_step(callback, state, {**data, "to_currency": to_currency})
    await callback.answer()


@router.callback_query(F.data.startswith("exchange:network:"))
async def cb_network(callback: CallbackQuery, state: FSMContext) -> None:
    network = callback.data.split(":")[-1]
    await state.update_data(network=network)
    data = await state.get_data()
    await _show_amount_step(callback, state, data["from_currency"])


@router.message(ExchangeStates.entering_amount)
async def handle_amount(message: types.Message, state: FSMContext) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    data = await state.get_data()
    is_valid, error_message, amount = validate_amount(message.text or "", data["from_currency"])
    if not is_valid or amount is None:
        await message.answer(error_message)
        return
    await state.update_data(amount=str(amount))
    updated_data = await state.get_data()
    await _show_address_step(message, state, updated_data)


@router.message(ExchangeStates.entering_address)
async def handle_address(message: types.Message, state: FSMContext) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    data = await state.get_data()
    is_valid, error_message = validate_address(
        data["exchange_type"],
        data["from_currency"],
        data["to_currency"],
        data["network"],
        message.text or "",
    )
    if not is_valid:
        await message.answer(error_message)
        return
    await state.update_data(address=(message.text or "").strip(), already_created=False)
    await _show_confirmation(message, state)


@router.callback_query(F.data == "exchange:edit")
async def cb_edit_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _show_amount_step(callback, state, data["from_currency"])


@router.callback_query(F.data == "exchange:confirm")
async def cb_confirm_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await callback.answer("Сессия истекла. Начните заново.", show_alert=True)
        return
    if data.get("already_created"):
        await callback.answer("Заявка уже создана.", show_alert=True)
        return
    if not await _apply_order_rate_limit(callback.from_user.id):
        await callback.answer("Превышен лимит: не более 3 заявок в час.", show_alert=True)
        return

    await state.update_data(already_created=True)
    preview = calculate_order_preview(
        from_currency=data["from_currency"],
        to_currency=data["to_currency"],
        amount=Decimal(data["amount"]),
    )
    order_id = await db.get_next_order_id()
    order = OrderDB(
        order_id=order_id,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        exchange_type=data["exchange_type"],
        from_currency=data["from_currency"],
        to_currency=data["to_currency"],
        amount=Decimal(data["amount"]),
        network=data["network"],
        address=data["address"],
        rate=preview["rate"],
        fee_percent=settings.default_fee_percent,
        fee_amount=preview["fee_amount"],
        receive_amount=preview["receive_amount"],
        is_demo=settings.demo_mode,
    )
    await db.create_order(order)
    await publish_message(
        settings.notify_managers_queue_name,
        {
            "type": "notify_managers",
            "event": "new_order",
            "order_id": order_id,
            "user_id": callback.from_user.id,
            "username": callback.from_user.username,
            "summary": f"Новая заявка: {order.from_currency} -> {order.to_currency}, {format_money(order.amount, order.from_currency)}",
        },
    )
    await state.clear()
    await callback.message.edit_text(
        f"✅ Заявка создана!\n\nНомер: #{order_id}\nСтатус: {get_order_status_label('new')}\n\nМенеджер свяжется с вами в ближайшее время.",
        reply_markup=build_after_create_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "exchange:cancel")
async def cb_cancel_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Текущий сценарий отменён.")
    await callback.message.answer(_build_main_menu_text(), reply_markup=build_reply_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "exchange:back")
async def cb_back_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    if current_state == ExchangeStates.selecting_from_currency.state:
        await _show_exchange_type(callback, state)
        return
    if current_state == ExchangeStates.selecting_to_currency.state:
        await _show_from_currency(callback, state, data["exchange_type"])
        return
    if current_state == ExchangeStates.selecting_network.state:
        await _show_to_currency(callback, state, data["exchange_type"], data["from_currency"])
        return
    if current_state == ExchangeStates.entering_amount.state:
        await _show_network_step(callback, state, data)
        return
    if current_state in (ExchangeStates.entering_address.state, ExchangeStates.confirming.state):
        await _show_amount_step(callback, state, data["from_currency"])
        return
    await show_main_menu(callback, state)


@router.callback_query(F.data.startswith("orders:page:"))
async def cb_orders_page(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    page = int(callback.data.split(":")[-1])
    orders, total = await db.list_orders_for_user(callback.from_user.id, page=page, page_size=10)
    total_pages = max(ceil(total / 10), 1)
    await callback.message.edit_text(
        _build_orders_list_text(orders, page, total_pages),
        reply_markup=build_orders_keyboard(orders, page, total_pages),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("orders:detail:"))
async def cb_order_detail(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, order_id, page_value = callback.data.split(":")
    order = await db.get_order_for_user(order_id, callback.from_user.id)
    if not order:
        await callback.answer("⛔ Не ваша заявка или она не найдена.", show_alert=True)
        return
    await callback.message.edit_text(_build_order_detail_text(order), reply_markup=build_order_detail_keyboard(int(page_value)))
    await callback.answer()

