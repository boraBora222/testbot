import asyncio
import logging
import random
import string
from pathlib import Path
from typing import Dict, List, Tuple

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import settings


logger = logging.getLogger(__name__)


class ExchangeStates(StatesGroup):
    choose_type = State()
    choose_from_currency = State()
    choose_to_currency = State()
    choose_network = State()
    enter_amount = State()
    enter_address = State()
    confirm = State()


router = Router(name="crypto_exchange")


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=("jinja2",)),
)


def render_screen(screen: str, **context: object) -> str:
    template = jinja_env.get_template("crypto_menu.jinja2")
    return template.render(screen=screen, **context)


SUPPORTED_CURRENCIES: List[str] = ["BTC", "ETH", "USDT", "USDC", "TON", "LTC"]

NETWORKS_BY_CURRENCY: Dict[str, List[str]] = {
    "BTC": ["BTC"],
    "ETH": ["ERC20"],
    "USDT": ["TRC20", "ERC20", "BEP20", "TON"],
    "USDC": ["ERC20", "BEP20"],
    "TON": ["TON"],
    "LTC": ["LTC"],
}

RATES_USD: Dict[str, float] = {
    "BTC": 65000.0,
    "ETH": 3500.0,
    "USDT": 1.0,
    "USDC": 1.0,
    "TON": 5.0,
    "LTC": 85.0,
}

FEE_PERCENT = 1.0
MIN_AMOUNT = 50.0


REPLY_MENU_BUTTONS: List[str] = [
    "🔄 Обменять",
    "💱 Курсы",
    "📜 Мои заявки",
    "👤 Профиль",
    "❓ FAQ",
    "🆘 Поддержка",
    "🏠 В главное меню",
    "❌ Отменить",
]


def build_reply_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔄 Обменять"),
                KeyboardButton(text="💱 Курсы"),
            ],
            [
                KeyboardButton(text="📜 Мои заявки"),
                KeyboardButton(text="👤 Профиль"),
            ],
            [
                KeyboardButton(text="❓ FAQ"),
                KeyboardButton(text="🆘 Поддержка"),
            ],
            [
                KeyboardButton(text="🏠 В главное меню"),
                KeyboardButton(text="❌ Отменить"),
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )
    return keyboard


def build_main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🔄 Обменять", callback_data="menu_exchange")],
        [InlineKeyboardButton(text="💱 Курсы", callback_data="menu_rates")],
        [InlineKeyboardButton(text="📜 Мои заявки", callback_data="menu_orders")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile")],
        [InlineKeyboardButton(text="❓ FAQ", callback_data="menu_faq")],
        [InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu_support")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_exchange_type_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text="Крипта → Крипта", callback_data="exchange_type_crypto_crypto"
            )
        ],
        [
            InlineKeyboardButton(
                text="Фиат → Крипта", callback_data="exchange_type_fiat_crypto"
            )
        ],
        [
            InlineKeyboardButton(
                text="Крипта → Фиат", callback_data="exchange_type_crypto_fiat"
            )
        ],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_main")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="exchange_cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_currency_keyboard(prefix: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for code in SUPPORTED_CURRENCIES:
        rows.append(
            [
                InlineKeyboardButton(
                    text=code, callback_data=f"{prefix}_currency_{code}"
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="exchange_back_step")]
    )
    rows.append(
        [InlineKeyboardButton(text="❌ Отменить", callback_data="exchange_cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_to_currency_keyboard(from_currency: str) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    for code in SUPPORTED_CURRENCIES:
        if code == from_currency:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=code, callback_data=f"to_currency_{code}"
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="exchange_back_step")]
    )
    rows.append(
        [InlineKeyboardButton(text="❌ Отменить", callback_data="exchange_cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_network_keyboard(currency: str) -> InlineKeyboardMarkup:
    networks = NETWORKS_BY_CURRENCY.get(currency, [])
    rows: List[List[InlineKeyboardButton]] = []
    for net in networks:
        rows.append(
            [
                InlineKeyboardButton(
                    text=net, callback_data=f"network_{net}"
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="exchange_back_step")]
    )
    rows.append(
        [InlineKeyboardButton(text="❌ Отменить", callback_data="exchange_cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_confirm_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвердить заявку", callback_data="exchange_confirm_order")],
        [InlineKeyboardButton(text="✏️ Изменить сумму", callback_data="exchange_edit_amount")],
        [InlineKeyboardButton(text="✏️ Изменить адрес", callback_data="exchange_edit_address")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="exchange_cancel")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_after_create_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_main")],
        [InlineKeyboardButton(text="🔄 Создать обмен", callback_data="menu_exchange")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_rates_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="BTC → USDT", callback_data="rate_BTC_USDT")],
        [InlineKeyboardButton(text="ETH → USDT", callback_data="rate_ETH_USDT")],
        [InlineKeyboardButton(text="USDT → BTC", callback_data="rate_USDT_BTC")],
        [InlineKeyboardButton(text="TON → USDT", callback_data="rate_TON_USDT")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="menu_rates")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_orders_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🟡 В обработке", callback_data="orders_in_progress")],
        [InlineKeyboardButton(text="🟢 Завершённые", callback_data="orders_completed")],
        [InlineKeyboardButton(text="🔴 Отменённые", callback_data="orders_cancelled")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_profile_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="⭐ Избранные пары", callback_data="profile_favorites")],
        [InlineKeyboardButton(text="🔔 Уведомления", callback_data="profile_notifications")],
        [InlineKeyboardButton(text="🌐 Язык", callback_data="profile_language")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_faq_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="Как создать обмен?", callback_data="faq_how_exchange")],
        [InlineKeyboardButton(text="Сколько идёт перевод?", callback_data="faq_how_long")],
        [InlineKeyboardButton(text="Какие комиссии?", callback_data="faq_fees")],
        [InlineKeyboardButton(text="Зачем нужна верификация?", callback_data="faq_kyc")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_support_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="✍️ Написать оператору", callback_data="support_write")],
        [InlineKeyboardButton(text="📨 Отправить ID заявки", callback_data="support_send_id")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def calculate_exchange(
    from_currency: str, to_currency: str, amount: float
) -> Tuple[float, float, float]:
    base_usd = RATES_USD[from_currency]
    quote_usd = RATES_USD[to_currency]
    fee_amount = amount * FEE_PERCENT / 100.0
    net_amount = amount - fee_amount
    usd_value = net_amount * base_usd
    receive_amount = usd_value / quote_usd
    rate = base_usd / quote_usd
    return fee_amount, receive_amount, rate


def generate_order_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"EX-{suffix}"


async def show_main_menu(message: types.Message | types.CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("main_menu")
    reply_keyboard = build_reply_main_menu_keyboard()
    if isinstance(message, types.CallbackQuery):
        await message.message.edit_text(text)
        await message.message.answer(text="Меню доступно на клавиатуре ниже.", reply_markup=reply_keyboard)
    else:
        await message.answer(text, reply_markup=reply_keyboard)


@router.message(Command("menu"))
async def cmd_start_menu(message: types.Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(F.text == "🏠 В главное меню")
async def msg_main_menu_button(message: types.Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(Command("exchange"))
async def cmd_exchange(message: types.Message, state: FSMContext) -> None:
    await state.set_state(ExchangeStates.choose_type)
    text = render_screen("exchange_type")
    keyboard = build_exchange_type_keyboard()
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "🔄 Обменять")
async def msg_exchange_button(message: types.Message, state: FSMContext) -> None:
    await cmd_exchange(message, state)


@router.message(Command("rates"))
async def cmd_rates(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("rates_menu")
    keyboard = build_rates_menu_keyboard()
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "💱 Курсы")
async def msg_rates_button(message: types.Message, state: FSMContext) -> None:
    await cmd_rates(message, state)


@router.message(Command("orders"))
async def cmd_orders(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("orders")
    keyboard = build_orders_keyboard()
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "📜 Мои заявки")
async def msg_orders_button(message: types.Message, state: FSMContext) -> None:
    await cmd_orders(message, state)


@router.message(Command("profile"))
async def cmd_profile(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("profile")
    keyboard = build_profile_keyboard()
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "👤 Профиль")
async def msg_profile_button(message: types.Message, state: FSMContext) -> None:
    await cmd_profile(message, state)


@router.message(Command("support"))
async def cmd_support(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("support")
    keyboard = build_support_keyboard()
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "❓ FAQ")
async def msg_faq_button(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("faq")
    keyboard = build_faq_keyboard()
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "🆘 Поддержка")
async def msg_support_button(message: types.Message, state: FSMContext) -> None:
    await cmd_support(message, state)


@router.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("cancelled")
    reply_keyboard = build_reply_main_menu_keyboard()
    await message.answer(text, reply_markup=reply_keyboard)


@router.message(F.text == "❌ Отменить")
async def msg_cancel_button(message: types.Message, state: FSMContext) -> None:
    await cmd_cancel(message, state)


@router.callback_query(F.data == "menu_main")
async def cb_menu_main(callback: CallbackQuery, state: FSMContext) -> None:
    await show_main_menu(callback, state)


@router.callback_query(F.data == "menu_exchange")
async def cb_menu_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExchangeStates.choose_type)
    text = render_screen("exchange_type")
    keyboard = build_exchange_type_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "menu_rates")
async def cb_menu_rates(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("rates_menu")
    keyboard = build_rates_menu_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "menu_orders")
async def cb_menu_orders(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("orders")
    keyboard = build_orders_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "menu_profile")
async def cb_menu_profile(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("profile")
    keyboard = build_profile_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "menu_faq")
async def cb_menu_faq(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("faq")
    keyboard = build_faq_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "menu_support")
async def cb_menu_support(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("support")
    keyboard = build_support_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("exchange_type_"))
async def cb_exchange_type(callback: CallbackQuery, state: FSMContext) -> None:
    exchange_type = callback.data.replace("exchange_type_", "")
    await state.update_data(exchange_type=exchange_type)
    await state.set_state(ExchangeStates.choose_from_currency)
    text = render_screen("exchange_from_currency")
    keyboard = build_currency_keyboard(prefix="from")
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("from_currency_"))
async def cb_from_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.replace("from_currency_", "")
    if currency not in SUPPORTED_CURRENCIES:
        await callback.answer("Неверная валюта", show_alert=True)
        return
    await state.update_data(from_currency=currency)
    await state.set_state(ExchangeStates.choose_to_currency)
    text = render_screen("exchange_to_currency")
    keyboard = build_to_currency_keyboard(from_currency=currency)
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("to_currency_"))
async def cb_to_currency(callback: CallbackQuery, state: FSMContext) -> None:
    currency = callback.data.replace("to_currency_", "")
    data = await state.get_data()
    from_currency = data.get("from_currency")
    if not from_currency or currency == from_currency:
        await callback.answer("Выберите другую валюту", show_alert=True)
        return
    if currency not in SUPPORTED_CURRENCIES:
        await callback.answer("Неверная валюта", show_alert=True)
        return
    await state.update_data(to_currency=currency)
    await state.set_state(ExchangeStates.choose_network)
    text = render_screen("exchange_network")
    keyboard = build_network_keyboard(currency)
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("network_"))
async def cb_network(callback: CallbackQuery, state: FSMContext) -> None:
    network = callback.data.replace("network_", "")
    await state.update_data(network=network)
    await state.set_state(ExchangeStates.enter_amount)
    text = render_screen("exchange_amount")
    await callback.message.edit_text(text)


@router.message(ExchangeStates.enter_amount)
async def handle_amount(message: types.Message, state: FSMContext) -> None:
    text = message.text or ""
    try:
        amount = float(text.replace(",", "."))
    except ValueError:
        error_text = render_screen("exchange_amount_error")
        await message.answer(error_text)
        return
    if amount < MIN_AMOUNT:
        error_text = render_screen("exchange_amount_error")
        await message.answer(error_text)
        return
    await state.update_data(amount=amount)
    await state.set_state(ExchangeStates.enter_address)
    next_text = render_screen("exchange_address")
    await message.answer(next_text)


@router.message(ExchangeStates.enter_address)
async def handle_address(message: types.Message, state: FSMContext) -> None:
    address = (message.text or "").strip()
    if len(address) < 8:
        error_text = render_screen("exchange_address_error")
        await message.answer(error_text)
        return
    await state.update_data(address=address)
    await state.set_state(ExchangeStates.confirm)
    data = await state.get_data()
    from_currency = data["from_currency"]
    to_currency = data["to_currency"]
    amount = float(data["amount"])
    network = data["network"]
    fee_amount, receive_amount, rate = calculate_exchange(
        from_currency=from_currency,
        to_currency=to_currency,
        amount=amount,
    )
    confirm_text = render_screen(
        "exchange_confirm",
        exchange_type=data["exchange_type"],
        from_currency=from_currency,
        to_currency=to_currency,
        network=network,
        amount=f"{amount:.2f}",
        fee_amount=f"{fee_amount:.2f}",
        receive_amount=f"{receive_amount:.2f}",
        fee_percent=f"{FEE_PERCENT:.2f}",
        rate=f"{rate:.4f}",
        address=address,
    )
    keyboard = build_confirm_keyboard()
    await message.answer(confirm_text, reply_markup=keyboard)


@router.callback_query(F.data == "exchange_edit_amount")
async def cb_edit_amount(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExchangeStates.enter_amount)
    text = render_screen("exchange_amount")
    await callback.message.edit_text(text)


@router.callback_query(F.data == "exchange_edit_address")
async def cb_edit_address(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ExchangeStates.enter_address)
    text = render_screen("exchange_address")
    await callback.message.edit_text(text)


@router.callback_query(F.data == "exchange_confirm_order")
async def cb_confirm_order(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    from_currency = data["from_currency"]
    to_currency = data["to_currency"]
    amount = float(data["amount"])
    network = data["network"]
    address = data["address"]
    fee_amount, receive_amount, rate = calculate_exchange(
        from_currency=from_currency,
        to_currency=to_currency,
        amount=amount,
    )
    order_id = generate_order_id()
    await state.clear()
    text = render_screen(
        "exchange_created",
        order_id=order_id,
        exchange_type=data["exchange_type"],
        from_currency=from_currency,
        to_currency=to_currency,
        network=network,
        amount=f"{amount:.2f}",
        fee_amount=f"{fee_amount:.2f}",
        receive_amount=f"{receive_amount:.2f}",
        fee_percent=f"{FEE_PERCENT:.2f}",
        rate=f"{rate:.4f}",
        address=address,
    )
    keyboard = build_after_create_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "exchange_cancel")
async def cb_exchange_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = render_screen("cancelled")
    keyboard = build_main_menu_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data == "exchange_back_step")
async def cb_back_step(callback: CallbackQuery, state: FSMContext) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    if current_state == ExchangeStates.choose_from_currency:
        await state.set_state(ExchangeStates.choose_type)
        text = render_screen("exchange_type")
        keyboard = build_exchange_type_keyboard()
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    if current_state == ExchangeStates.choose_to_currency:
        await state.set_state(ExchangeStates.choose_from_currency)
        text = render_screen("exchange_from_currency")
        keyboard = build_currency_keyboard(prefix="from")
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    if current_state == ExchangeStates.choose_network:
        from_currency = data.get("from_currency", "")
        await state.set_state(ExchangeStates.choose_to_currency)
        text = render_screen("exchange_to_currency")
        keyboard = build_to_currency_keyboard(from_currency=from_currency)
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    if current_state in (ExchangeStates.enter_amount, ExchangeStates.enter_address):
        to_currency = data.get("to_currency", "")
        await state.set_state(ExchangeStates.choose_network)
        text = render_screen("exchange_network")
        keyboard = build_network_keyboard(to_currency)
        await callback.message.edit_text(text, reply_markup=keyboard)
        return
    await state.clear()
    text = render_screen("main_menu")
    keyboard = build_main_menu_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("rate_"))
async def cb_rate_pair(callback: CallbackQuery, state: FSMContext) -> None:
    payload = callback.data.replace("rate_", "")
    try:
        base, quote = payload.split("_", maxsplit=1)
    except ValueError:
        await callback.answer("Неверная пара", show_alert=True)
        return
    if base not in RATES_USD or quote not in RATES_USD:
        await callback.answer("Неверная пара", show_alert=True)
        return
    base_usd = RATES_USD[base]
    quote_usd = RATES_USD[quote]
    rate = base_usd / quote_usd
    text = render_screen(
        "rate_details",
        pair_label=f"{base} → {quote}",
        base_currency=base,
        quote_currency=quote,
        rate=f"{rate:.4f}",
    )
    keyboard = build_rates_menu_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("orders_"))
async def cb_orders_filters(callback: CallbackQuery, state: FSMContext) -> None:
    text = render_screen("orders")
    keyboard = build_orders_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("profile_"))
async def cb_profile_filters(callback: CallbackQuery, state: FSMContext) -> None:
    text = render_screen("profile")
    keyboard = build_profile_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("faq_"))
async def cb_faq_details(callback: CallbackQuery, state: FSMContext) -> None:
    text = render_screen("faq")
    keyboard = build_faq_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("support_"))
async def cb_support_actions(callback: CallbackQuery, state: FSMContext) -> None:
    text = render_screen("support")
    keyboard = build_support_keyboard()
    await callback.message.edit_text(text, reply_markup=keyboard)


async def on_startup(bot: Bot) -> None:
    logger.info("Crypto exchange bot started")


async def on_shutdown(bot: Bot) -> None:
    await bot.session.close()
    logger.info("Crypto exchange bot stopped")


async def main() -> None:
    if not settings.telegram_bot_token:
        logger.critical("TELEGRAM_BOT_TOKEN is not configured")
        raise SystemExit(1)

    logging.basicConfig(level=logging.INFO)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Crypto exchange bot stopped by user")

