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
    WebAppInfo,
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
from .states import ExchangeStates, ProfileDocumentStates, SupportStates
from shared import db
from shared.async_tracing import add_async_trace, format_async_trace
from shared.models import LimitQuotaDB, OrderDraftDB
from shared.security_settings import (
    calculate_remaining_quota,
    ensure_whitelist_entry_can_be_created,
    find_matching_whitelist_entry,
    normalize_whitelist_network,
)
from shared.services.order_lifecycle import (
    build_order_detail_payload,
    build_order_draft,
    build_order_list_item,
    build_order_state_from_draft,
    build_repeat_seed,
    build_status_meta,
    can_repeat_order,
    get_status_filter_values,
    normalize_order_filter,
)
from shared.services.security_settings import (
    LimitQuotaNotConfiguredError,
    WhitelistApprovalRequiredError,
    create_pending_whitelist_entry,
    create_order_with_security_checks,
)
from shared.services import documents as document_service
from shared.types.enums import ClientDocumentType, DraftSource, DraftStep, ExchangeType, OrderCreatedFrom, OrderListFilter

logger = logging.getLogger(__name__)
router = Router(name="crypto_exchange")
CONTRACT_PLACEHOLDER_PATH = Path(__file__).resolve().parent / "assets" / "contract_placeholder.txt"
ORDER_FILTER_BUTTONS: tuple[tuple[str, OrderListFilter], ...] = (
    ("Все", OrderListFilter.ALL),
    ("Активные", OrderListFilter.ACTIVE),
    ("Новые", OrderListFilter.NEW),
    ("Ожидают оплату", OrderListFilter.WAITING_PAYMENT),
    ("В работе", OrderListFilter.PROCESSING),
    ("Завершены", OrderListFilter.COMPLETED),
    ("Отменены", OrderListFilter.CANCELLED),
)

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
PROFILE_DOCUMENT_STATE_KEY = "profile_document_type"
PROFILE_DOCUMENT_TYPE_OPTIONS: tuple[tuple[ClientDocumentType, str], ...] = (
    (ClientDocumentType.INN, "ИНН"),
    (ClientDocumentType.OGRN, "ОГРН"),
    (ClientDocumentType.CHARTER, "Устав"),
    (ClientDocumentType.PROTOCOL, "Протокол"),
    (ClientDocumentType.DIRECTOR_PASSPORT, "Паспорт директора"),
    (ClientDocumentType.EGRUL_EXTRACT, "Выписка ЕГРЮЛ"),
    (ClientDocumentType.BANK_DETAILS, "Банковские реквизиты"),
    (ClientDocumentType.OTHER, "Другой документ"),
)
PROFILE_DOCUMENT_LABELS = {document_type: label for document_type, label in PROFILE_DOCUMENT_TYPE_OPTIONS}


async def _touch_user(user: types.User) -> None:
    await db.ensure_exchange_user(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
    )


def build_site_menu_button() -> KeyboardButton:
    if settings.front_base_url.startswith("https://"):
        return KeyboardButton(text="🌐 Сайт", web_app=WebAppInfo(url=settings.front_base_url))
    return KeyboardButton(text="🌐 Сайт")


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
                build_site_menu_button(),
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


def _format_whitelist_choice(entry: dict) -> str:
    suffix = str(entry["address"])[-6:]
    return f"{entry['label']} ({suffix})"


def build_whitelist_keyboard(entries: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=_format_whitelist_choice(entry), callback_data=f"exchange:whitelist:{entry['id']}")]
        for entry in entries
    ]
    rows.append([InlineKeyboardButton(text="➕ Новый адрес для whitelist", callback_data="exchange:whitelist:new")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="exchange:back")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_whitelist_submission_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📨 Отправить на модерацию", callback_data="exchange:whitelist:submit")],
            [InlineKeyboardButton(text="← К выбору адреса", callback_data="exchange:back")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")],
        ]
    )


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
            [InlineKeyboardButton(text="💾 Сохранить как черновик", callback_data="draft:save")],
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="exchange:edit")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")],
        ]
    )


def build_after_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📋 Мои заявки", callback_data=f"orders:filter:{OrderListFilter.ALL.value}:1"),
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
            [InlineKeyboardButton(text="📂 Документы", callback_data="profile:documents")],
            [
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
                InlineKeyboardButton(text="❓ Поддержка", callback_data="menu:support"),
            ]
        ]
    )


def build_profile_documents_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for document_type, label in PROFILE_DOCUMENT_TYPE_OPTIONS:
        current_row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"profile:documents:type:{document_type.value}",
            )
        )
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append(
        [
            InlineKeyboardButton(text="← Профиль", callback_data="profile:overview"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_profile_document_upload_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="← К типам", callback_data="profile:documents"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
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


def build_resume_draft_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Продолжить черновик", callback_data="draft:resume")],
            [InlineKeyboardButton(text="🗑 Начать заново", callback_data="draft:discard")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="exchange:cancel")],
        ]
    )


def build_orders_keyboard(orders: list[dict], page: int, total_pages: int, current_filter: OrderListFilter) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    filter_rows: list[list[InlineKeyboardButton]] = []
    current_filter_row: list[InlineKeyboardButton] = []
    for index, (label, order_filter) in enumerate(ORDER_FILTER_BUTTONS, start=1):
        prefix = "• " if current_filter == order_filter else ""
        current_filter_row.append(
            InlineKeyboardButton(
                text=f"{prefix}{label}",
                callback_data=f"orders:filter:{order_filter.value}:1",
            )
        )
        if index % 3 == 0:
            filter_rows.append(current_filter_row)
            current_filter_row = []
    if current_filter_row:
        filter_rows.append(current_filter_row)
    rows.extend(filter_rows)

    for order in orders:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{order['order_id']} | {order['from_currency']} -> {order['to_currency']}",
                    callback_data=f"orders:detail:{order['order_id']}:{page}:{current_filter.value}",
                )
            ]
        )

    navigation_row: list[InlineKeyboardButton] = []
    if page > 1:
        navigation_row.append(InlineKeyboardButton(text="← Назад", callback_data=f"orders:filter:{current_filter.value}:{page - 1}"))
    if page < total_pages:
        navigation_row.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"orders:filter:{current_filter.value}:{page + 1}"))
    if navigation_row:
        rows.append(navigation_row)
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_order_detail_keyboard(order_id: str, page: int, current_filter: OrderListFilter, can_repeat: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_repeat:
        rows.append([InlineKeyboardButton(text="🔁 Повторить", callback_data=f"orders:repeat:{order_id}")])
    rows.append(
        [
            InlineKeyboardButton(text="← Назад к списку", callback_data=f"orders:filter:{current_filter.value}:{page}"),
            InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def _build_resume_draft_text(draft: dict) -> str:
    direction = f"{draft['from_currency']} -> {draft['to_currency']}"
    return (
        "💾 Найден сохранённый черновик\n\n"
        f"Направление: {direction}\n"
        f"Сумма: {format_money(draft['amount'], draft['from_currency'])}\n"
        f"Обновлён: {format_datetime_for_user(draft['updated_at'])}\n\n"
        "Продолжить оформление или начать новый сценарий?"
    )


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
    lines = ["🧮 Расчёт обмена", ""]
    if data.get("source_order_id"):
        lines.extend(
            [
                f"Основано на заявке #{data['source_order_id']}.",
                "Финальные курс и комиссия пересчитаны по текущим правилам.",
                "",
            ]
        )
    if data.get("resumed_from_draft"):
        lines.extend(
            [
                "Вы продолжаете сохранённый черновик.",
                "",
            ]
        )
    lines.extend(
        [
            f"Направление: {data['from_currency']} -> {data['to_currency']}",
            f"Тип: {get_exchange_type_label(data['exchange_type'])}",
            f"Сеть: {network_label}",
            "",
            f"Сумма: {format_money(Decimal(data['amount']), data['from_currency'])}",
            f"Курс: {format_rate(preview['rate'], data['from_currency'], data['to_currency'])}",
            f"К получению до комиссии: {format_money(preview['gross_receive_amount'], data['to_currency'])}",
            f"Комиссия ({settings.default_fee_percent}%): {format_money(preview['fee_amount'], data['to_currency'])}",
            f"Итого: {format_money(preview['receive_amount'], data['to_currency'])}",
            "",
            f"Адрес / реквизиты:\n{data['address']}",
        ]
    )
    if data.get("whitelist_address_id"):
        lines.append("Источник адреса: активный whitelist.")
    lines.extend(
        [
            "",
            "⚠️ Курсы действительны 15 минут.",
        ]
    )
    return "\n".join(lines)


def _build_order_detail_text(order: dict) -> str:
    status_meta = build_status_meta(order["status"])
    lines = [
        f"📄 Заявка #{order['order_id']}",
        "",
        f"Статус: {get_order_status_emoji(order['status'])} {get_order_status_label(order['status'])}",
        f"Комментарий: {status_meta.reason}",
    ]
    if status_meta.eta_text:
        lines.append(f"ETA: {status_meta.eta_text}")
    if status_meta.next_step:
        lines.append(f"Следующий шаг: {status_meta.next_step}")
    lines.extend(
        [
            "",
            f"Тип обмена: {get_exchange_type_label(order['exchange_type'])}",
            f"Направление: {order['from_currency']} -> {order['to_currency']}",
            f"Сеть: {order['network']}",
            "",
            f"Сумма: {format_money(order['amount'], order['from_currency'])}",
            f"Курс: {format_rate(order['rate'], order['from_currency'], order['to_currency'])}",
            f"Комиссия ({order['fee_percent']}%): {format_money(order['fee_amount'], order['to_currency'])}",
            f"К получению: {format_money(order['receive_amount'], order['to_currency'])}",
            "",
            f"Адрес / реквизиты:\n{order['address']}",
            "",
            f"Создана: {format_datetime_for_user(order['created_at'])}",
            f"Обновлена: {format_datetime_for_user(order['updated_at'])}",
        ]
    )
    return "\n".join(lines)


def _build_orders_list_text(orders: list[dict], page: int, total_pages: int) -> str:
    if not orders:
        return "📋 Ваши заявки\n\nПока заявок нет."
    lines = ["📋 Ваши заявки", ""]
    for order in orders:
        status_meta = build_status_meta(order["status"])
        lines.extend(
            [
                f"#{order['order_id']} | {order['from_currency']} -> {order['to_currency']}",
                f"Сумма: {format_money(order['amount'], order['from_currency'])} | Статус: {get_order_status_emoji(order['status'])} {get_order_status_label(order['status'])}",
                status_meta.reason,
                format_datetime_for_user(order["created_at"]),
                "",
            ]
        )
    lines.append(f"Страница {page}/{total_pages}")
    return "\n".join(lines)


def _format_verification_level_label(value: str) -> str:
    mapping = {
        "basic": "basic",
        "extended": "extended",
        "corporate": "corporate",
    }
    return mapping.get(value, value)


def _format_profile_document_type_label(document_type: ClientDocumentType | str) -> str:
    if isinstance(document_type, ClientDocumentType):
        resolved_type = document_type
    else:
        try:
            resolved_type = ClientDocumentType(document_type)
        except ValueError:
            return document_type
    return PROFILE_DOCUMENT_LABELS.get(resolved_type, resolved_type.value)


def _build_profile_documents_text() -> str:
    return (
        "📂 Документы клиента\n\n"
        "Шаг 1. Выберите тип документа.\n\n"
        f"Поддерживаемые форматы: {document_service.PROFILE_DOCUMENT_SUPPORTED_FORMATS_LABEL}.\n"
        "Максимальный размер файла: 10 МБ.\n"
        "Если документ этого типа уже загружен, новый файл заменит предыдущий."
    )


def _build_profile_document_upload_prompt(document_type: ClientDocumentType) -> str:
    return (
        "📂 Загрузка документа\n\n"
        f"Шаг 2. Отправьте файл для типа «{_format_profile_document_type_label(document_type)}».\n\n"
        f"Поддерживаемые форматы: {document_service.PROFILE_DOCUMENT_SUPPORTED_FORMATS_LABEL}.\n"
        "Максимальный размер файла: 10 МБ.\n"
        "JPG и PNG отправляйте как документ, а не как сжатое фото."
    )


def _build_profile_document_success_text(
    document_type: ClientDocumentType,
    *,
    file_name: str | None,
    replaced: bool,
) -> str:
    status_line = "заменён новым" if replaced else "сохранён в профиле"
    file_line = f"\nФайл: {file_name}" if file_name else ""
    return (
        f"✅ Документ «{_format_profile_document_type_label(document_type)}» {status_line}.{file_line}\n"
        "Если понадобится обновить этот тип документа, просто отправьте новый файл."
    )


def _translate_profile_document_validation_error(exc: document_service.ProfileDocumentValidationError) -> str:
    raw_message = str(exc)
    if raw_message == "Unsupported profile document format.":
        return (
            "Неподдерживаемый формат файла. "
            f"Поддерживаются {document_service.PROFILE_DOCUMENT_SUPPORTED_FORMATS_LABEL}."
        )
    if raw_message == "Profile documents must be 10 MB or smaller.":
        return "Файл слишком большой. Максимальный размер документа 10 МБ."
    if raw_message == "Profile documents cannot be empty.":
        return "Файл пустой. Отправьте документ заново."
    if raw_message == "Profile document file name is required.":
        return "Не удалось определить имя файла. Отправьте документ как файл."
    return raw_message


def _build_profile_text(
    user_doc: dict,
    total_orders: int,
    active_orders: int,
    materials_count: int,
    quota: LimitQuotaDB | None,
) -> str:
    username = f"@{user_doc['username']}" if user_doc.get("username") else "-"
    full_name = " ".join(part for part in [user_doc.get("first_name"), user_doc.get("last_name")] if part) or "-"
    base_text = (
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
    if quota is None:
        return f"{base_text}\n\nЛимиты: пока не настроены. Обратитесь к менеджеру."

    daily_remaining = calculate_remaining_quota(quota.daily_limit, quota.daily_used)
    monthly_remaining = calculate_remaining_quota(quota.monthly_limit, quota.monthly_used)
    return (
        f"{base_text}\n\n"
        "Лимиты профиля\n"
        f"Уровень: {_format_verification_level_label(quota.verification_level.value)}\n"
        f"День: {format_money(quota.daily_used, 'RUB')} / {format_money(quota.daily_limit, 'RUB')}, "
        f"остаток {format_money(daily_remaining, 'RUB')}\n"
        f"Сброс дня: {format_datetime_for_user(quota.daily_reset_at)}\n"
        f"Месяц: {format_money(quota.monthly_used, 'RUB')} / {format_money(quota.monthly_limit, 'RUB')}, "
        f"остаток {format_money(monthly_remaining, 'RUB')}\n"
        f"Сброс месяца: {format_datetime_for_user(quota.monthly_reset_at)}"
    )


def _build_whitelist_text(network: str, active_entries: list[dict]) -> str:
    network_label = get_network_label("USDT", network)
    lines = [
        "📍 Выберите адрес получения",
        "",
        f"Сеть: {network_label}",
        "Сделки и выводы доступны только на активные адреса из whitelist.",
    ]
    if active_entries:
        lines.extend(
            [
                "",
                "Активные адреса:",
            ]
        )
        for entry in active_entries:
            lines.append(f"• {entry['label']} — {entry['address']}")
    else:
        lines.extend(
            [
                "",
                "Для этой сети пока нет активных whitelist-адресов.",
                "Добавьте новый адрес и отправьте его на модерацию.",
            ]
        )
    return "\n".join(lines)


def _build_new_whitelist_prompt(network: str) -> str:
    network_label = get_network_label("USDT", network)
    return (
        "📨 Новый адрес для whitelist\n\n"
        f"Сеть: {network_label}\n"
        "Введите адрес кошелька. Если адрес ещё не активирован, бот остановит создание заявки "
        "и предложит отправить его на модерацию."
    )


def _build_whitelist_submission_text(network: str, address: str) -> str:
    network_label = get_network_label("USDT", network)
    return (
        "Адрес ещё не активирован.\n\n"
        f"Сеть: {network_label}\n"
        f"Адрес: {address}\n\n"
        "Сделки и выводы доступны только после получения статуса active в whitelist. "
        "Отправить адрес на модерацию сейчас?"
    )


def _get_order_filter_label(order_filter: OrderListFilter) -> str:
    for label, candidate_filter in ORDER_FILTER_BUTTONS:
        if candidate_filter == order_filter:
            return label
    return order_filter.value


async def _show_orders_page(
    target: types.Message | CallbackQuery,
    *,
    user_id: int,
    page: int,
    order_filter: OrderListFilter,
) -> None:
    statuses = get_status_filter_values(order_filter)
    orders, total = await db.list_orders_for_user(
        user_id,
        page=page,
        page_size=10,
        statuses=list(statuses) if statuses else None,
    )
    enriched_orders = [build_order_list_item(order) for order in orders]
    total_pages = max(ceil(total / 10), 1)
    filter_label = _get_order_filter_label(order_filter)
    text = _build_orders_list_text(enriched_orders, page, total_pages)
    if order_filter != OrderListFilter.ALL:
        body = text.removeprefix("📋 Ваши заявки\n\n")
        text = f"📋 Ваши заявки\nФильтр: {filter_label}\n\n{body}"
    keyboard = build_orders_keyboard(enriched_orders, page, total_pages, order_filter)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


def _resolve_created_from(data: dict) -> OrderCreatedFrom:
    if data.get("draft_id"):
        return OrderCreatedFrom.DRAFT_SUBMIT
    if data.get("source_order_id"):
        return OrderCreatedFrom.REPEAT
    return OrderCreatedFrom.MANUAL


async def _get_existing_draft(owner_channel: str, owner_id: str) -> OrderDraftDB | None:
    draft = await db.get_current_order_draft(owner_channel, owner_id)
    if not draft:
        return None
    return OrderDraftDB(**draft)


async def _get_profile_quota(user_id: int) -> LimitQuotaDB | None:
    quota_payload = await db.get_limit_quota(user_id)
    if quota_payload is None:
        return None
    return LimitQuotaDB(**quota_payload)


async def _select_whitelist_entry(
    *,
    state: FSMContext,
    user_id: int,
    whitelist_id: str,
) -> dict | None:
    entries = await db.list_whitelist_addresses_for_user(user_id)
    for entry in entries:
        if entry.get("id") != whitelist_id or entry.get("status") != "active":
            continue
        await state.update_data(
            address=entry["address"],
            whitelist_address_id=entry["id"],
            use_whitelist=True,
            pending_whitelist_address=None,
            already_created=False,
        )
        return entry
    return None


async def show_main_menu(target: types.Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = _build_main_menu_text()
    keyboard = build_reply_main_menu_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_profile(target: types.Message | CallbackQuery, state: FSMContext, user_id: int) -> None:
    await state.clear()
    user_doc = await db.get_exchange_user(user_id)
    if not user_doc:
        text = "Профиль пока не найден. Используйте /start."
        if getattr(target, "message", None) is not None:
            await target.message.answer(text)
            await target.answer()
            return
        await target.answer(text)
        return

    total_orders = await db.count_orders_for_user(user_id)
    active_orders = await db.count_active_orders_for_user(user_id)
    materials_count = await db.count_materials_for_user(user_id)
    quota = await _get_profile_quota(user_id)
    text = _build_profile_text(user_doc, total_orders, active_orders, materials_count, quota)
    keyboard = build_profile_keyboard()
    if getattr(target, "message", None) is not None:
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_profile_documents(target: types.Message | CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ProfileDocumentStates.selecting_type)
    text = _build_profile_documents_text()
    keyboard = build_profile_documents_keyboard()
    if getattr(target, "message", None) is not None:
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_profile_document_upload_step(
    target: types.Message | CallbackQuery,
    state: FSMContext,
    document_type: ClientDocumentType,
) -> None:
    await state.set_state(ProfileDocumentStates.waiting_document)
    await state.update_data(**{PROFILE_DOCUMENT_STATE_KEY: document_type.value})
    text = _build_profile_document_upload_prompt(document_type)
    keyboard = build_profile_document_upload_keyboard()
    if getattr(target, "message", None) is not None:
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _resolve_profile_document_type_from_state(state: FSMContext) -> ClientDocumentType | None:
    data = await state.get_data()
    raw_document_type = data.get(PROFILE_DOCUMENT_STATE_KEY)
    if not raw_document_type:
        return None
    try:
        return ClientDocumentType(str(raw_document_type))
    except ValueError:
        return None


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


async def _show_whitelist_step(target: types.Message | CallbackQuery, state: FSMContext, data: dict, user_id: int) -> None:
    entries = await db.list_whitelist_addresses_for_user(user_id)
    requested_network = normalize_whitelist_network(str(data["network"]))
    active_entries: list[dict] = []
    for entry in entries:
        if entry.get("status") != "active":
            continue
        try:
            entry_network = normalize_whitelist_network(str(entry.get("network")))
        except ValueError:
            continue
        if entry_network == requested_network:
            active_entries.append(entry)
    await state.set_state(ExchangeStates.selecting_whitelist_address)
    text = _build_whitelist_text(data["network"], active_entries)
    keyboard = build_whitelist_keyboard(active_entries)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=keyboard)
        await target.answer()
        return
    await target.answer(text, reply_markup=keyboard)


async def _show_new_whitelist_address_step(target: types.Message | CallbackQuery, state: FSMContext, network: str) -> None:
    await state.set_state(ExchangeStates.entering_address)
    text = _build_new_whitelist_prompt(network)
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
    current_draft = await _get_existing_draft("telegram", str(message.from_user.id))
    if current_draft is not None:
        await state.clear()
        await message.answer(_build_resume_draft_text(current_draft.model_dump()), reply_markup=build_resume_draft_keyboard())
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
    await _show_orders_page(message, user_id=message.from_user.id, page=1, order_filter=OrderListFilter.ALL)


@router.message(Command("profile"))
@router.message(F.text == "👤 Профиль")
async def cmd_profile(message: types.Message, state: FSMContext) -> None:
    await _touch_user(message.from_user)
    await _show_profile(message, state, message.from_user.id)


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


@router.message(ProfileDocumentStates.waiting_document, F.document)
async def handle_profile_document_upload(message: types.Message, state: FSMContext) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return

    document_type = await _resolve_profile_document_type_from_state(state)
    if document_type is None:
        await state.clear()
        await message.answer(
            "Сессия загрузки документа истекла. Выберите тип документа заново из профиля.",
            reply_markup=build_reply_main_menu_keyboard(),
        )
        return

    document = message.document
    try:
        document_service.validate_profile_document_metadata(
            file_name=document.file_name,
            file_size=document.file_size,
        )
        stored_document = await document_service.transfer_profile_document_from_telegram(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            client_doc_type=document_type,
            telegram_file_id=document.file_id,
            file_name=document.file_name,
        )
    except document_service.ProfileDocumentValidationError as exc:
        await message.answer(_translate_profile_document_validation_error(exc))
        return
    except document_service.TelegramDocumentTransferError:
        await message.answer("Не удалось скачать файл из Telegram. Отправьте документ ещё раз.")
        return
    except document_service.ProfileDocumentStorageUnavailableError:
        await message.answer("Хранилище документов временно недоступно. Попробуйте позже.")
        return
    except document_service.ProfileDocumentPersistenceError:
        await message.answer("Не удалось сохранить запись документа. Попробуйте позже.")
        return

    await state.clear()
    await message.answer(
        _build_profile_document_success_text(
            document_type,
            file_name=stored_document.document.get("file_name"),
            replaced=stored_document.replaced,
        ),
        reply_markup=build_reply_main_menu_keyboard(),
    )
    logger.info(
        "Profile document uploaded via Telegram. user_id=%s document_id=%s client_doc_type=%s replaced=%s",
        message.from_user.id,
        stored_document.document.get("id"),
        document_type.value,
        stored_document.replaced,
    )


@router.message(ProfileDocumentStates.waiting_document, F.photo)
async def handle_profile_document_photo(message: types.Message) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    await message.answer(
        "Изображения для профиля отправляйте как документ, а не как сжатое фото. "
        "Так мы сохраним исходный файл и корректно проверим формат."
    )


@router.message(ProfileDocumentStates.waiting_document, ~F.document)
async def handle_profile_document_wrong_payload(message: types.Message) -> None:
    if not await _apply_message_rate_limit(message.from_user.id):
        await message.answer("Слишком много сообщений. Попробуйте через минуту.")
        return
    await message.answer("Отправьте документ одним файлом или вернитесь к выбору типа через профиль.")


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


@router.callback_query(F.data == "profile:overview")
async def cb_profile_overview(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_profile(callback, state, callback.from_user.id)


@router.callback_query(F.data == "profile:documents")
async def cb_profile_documents(callback: CallbackQuery, state: FSMContext) -> None:
    await _show_profile_documents(callback, state)


@router.callback_query(F.data.startswith("profile:documents:type:"))
async def cb_profile_document_type(callback: CallbackQuery, state: FSMContext) -> None:
    raw_document_type = callback.data.split(":")[-1]
    try:
        document_type = ClientDocumentType(raw_document_type)
    except ValueError:
        await callback.answer("Неподдерживаемый тип документа.", show_alert=True)
        return
    await _show_profile_document_upload_step(callback, state, document_type)


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


@router.callback_query(F.data == "exchange:whitelist:new")
async def cb_new_whitelist_address(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _show_new_whitelist_address_step(callback, state, data["network"])


@router.callback_query(F.data == "exchange:whitelist:submit")
async def cb_submit_whitelist_address(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    pending_address = data.get("pending_whitelist_address")
    if not pending_address:
        await callback.answer("Сессия истекла. Начните выбор адреса заново.", show_alert=True)
        return
    try:
        await create_pending_whitelist_entry(
            user_id=callback.from_user.id,
            network=data["network"],
            address=str(pending_address),
        )
    except ValueError as exc:
        await callback.answer(str(exc), show_alert=True)
        return

    await state.update_data(
        pending_whitelist_address=None,
        whitelist_address_id=None,
        use_whitelist=None,
        already_created=False,
    )
    await callback.answer("Адрес отправлен на модерацию.", show_alert=True)
    await _show_whitelist_step(callback, state, data, callback.from_user.id)


@router.callback_query(F.data.startswith("exchange:whitelist:"))
async def cb_select_whitelist(callback: CallbackQuery, state: FSMContext) -> None:
    whitelist_id = callback.data.split(":")[-1]
    if whitelist_id in {"new", "submit"}:
        return

    selected_entry = await _select_whitelist_entry(
        state=state,
        user_id=callback.from_user.id,
        whitelist_id=whitelist_id,
    )
    if selected_entry is None:
        await callback.answer("Адрес не найден или ещё не активирован.", show_alert=True)
        return

    await _show_confirmation(callback, state)


@router.message(ExchangeStates.entering_amount, ~F.text.in_(REPLY_MENU_BUTTONS))
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
    await _show_whitelist_step(message, state, updated_data, message.from_user.id)


@router.message(ExchangeStates.entering_address, ~F.text.in_(REPLY_MENU_BUTTONS))
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

    entered_address = (message.text or "").strip()
    entries = await db.list_whitelist_addresses_for_user(message.from_user.id)
    matched_entry = find_matching_whitelist_entry(
        entries,
        network=data["network"],
        address=entered_address,
    )
    if matched_entry is not None:
        if matched_entry.get("status") == "active":
            await state.update_data(
                address=matched_entry["address"],
                whitelist_address_id=matched_entry["id"],
                use_whitelist=True,
                already_created=False,
            )
            await message.answer("Адрес уже есть в активном whitelist. Продолжаем оформление заявки.")
            await _show_confirmation(message, state)
            return
        if matched_entry.get("status") == "pending":
            await message.answer(
                "Этот адрес уже ожидает модерации. Создать сделку можно будет после статуса active."
            )
            return
        await message.answer(
            "Этот адрес уже был отклонён и не может быть отправлен повторно. Добавьте другой адрес или обратитесь к менеджеру."
        )
        return

    try:
        ensure_whitelist_entry_can_be_created(
            entries,
            network=data["network"],
            address=entered_address,
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return

    await state.set_state(ExchangeStates.confirming_whitelist_submission)
    await state.update_data(
        pending_whitelist_address=entered_address,
        already_created=False,
    )
    await message.answer(
        _build_whitelist_submission_text(data["network"], entered_address),
        reply_markup=build_whitelist_submission_keyboard(),
    )


@router.callback_query(F.data == "exchange:edit")
async def cb_edit_exchange(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await _show_amount_step(callback, state, data["from_currency"])


@router.callback_query(F.data == "draft:save")
async def cb_save_draft(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await callback.answer("Сессия истекла. Начните заново.", show_alert=True)
        return

    existing_draft = await _get_existing_draft("telegram", str(callback.from_user.id))
    draft = build_order_draft(
        owner_channel="telegram",
        owner_id=str(callback.from_user.id),
        payload=data,
        source=data.get("draft_source", DraftSource.MANUAL.value),
        current_step=DraftStep.CONFIRM,
        source_order_id=data.get("source_order_id"),
        draft_id=existing_draft.draft_id if existing_draft is not None else None,
        created_at=existing_draft.created_at if existing_draft is not None else None,
    )
    saved_draft = await db.create_or_replace_order_draft(draft)
    await state.update_data(draft_id=saved_draft.draft_id)
    await callback.answer("Черновик сохранён.", show_alert=True)


@router.callback_query(F.data == "draft:resume")
async def cb_resume_draft(callback: CallbackQuery, state: FSMContext) -> None:
    existing_draft = await _get_existing_draft("telegram", str(callback.from_user.id))
    if existing_draft is None:
        await callback.answer("Черновик не найден.", show_alert=True)
        await _show_exchange_type(callback, state)
        return

    resume_state = build_order_state_from_draft(existing_draft)
    await state.clear()
    await state.update_data(**resume_state, already_created=False)
    await _show_confirmation(callback, state)


@router.callback_query(F.data == "draft:discard")
async def cb_discard_draft(callback: CallbackQuery, state: FSMContext) -> None:
    await db.delete_order_draft("telegram", str(callback.from_user.id))
    await state.clear()
    await _show_exchange_type(callback, state)


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
    try:
        order, warnings = await create_order_with_security_checks(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            payload=data,
            is_demo=settings.demo_mode,
            created_from=_resolve_created_from(data),
            source_order_id=data.get("source_order_id"),
            source_draft_id=data.get("draft_id"),
        )
    except WhitelistApprovalRequiredError:
        await state.update_data(already_created=False)
        await callback.answer(
            "Адрес не находится в активном whitelist. Выберите активный адрес или отправьте новый адрес на модерацию.",
            show_alert=True,
        )
        return
    except LimitQuotaNotConfiguredError:
        await state.update_data(already_created=False)
        await callback.answer(
            "Лимиты профиля пока не настроены. Пожалуйста, обратитесь к менеджеру.",
            show_alert=True,
        )
        return
    except ValueError as exc:
        await state.update_data(already_created=False)
        await callback.answer(str(exc), show_alert=True)
        return

    if data.get("draft_id"):
        await db.delete_order_draft("telegram", str(callback.from_user.id))
    manager_payload = add_async_trace(
        {
            "type": "notify_managers",
            "event": "new_order",
            "order_id": order.order_id,
            "user_id": callback.from_user.id,
            "username": callback.from_user.username,
            "summary": f"Новая заявка: {order.from_currency} -> {order.to_currency}, {format_money(order.amount, order.from_currency)}",
        },
        producer="bot.crypto_exchange_bot",
        queue_name=settings.notify_managers_queue_name,
        event_name="new_order",
    )
    logger.info(
        "Queued order manager notification. %s",
        format_async_trace(
            manager_payload,
            stage="queued",
            queue_name=settings.notify_managers_queue_name,
        ),
    )
    await publish_message(settings.notify_managers_queue_name, manager_payload)
    await state.clear()
    warning_text = ""
    if warnings:
        warning_text = "\n\n⚠️ Заявка превышает ваш текущий дневной или месячный лимит и помечена для проверки менеджером."
    await callback.message.edit_text(
        f"✅ Заявка создана!\n\nНомер: #{order.order_id}\nСтатус: {get_order_status_label('new')}\n\nМенеджер свяжется с вами в ближайшее время.{warning_text}",
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
    if current_state == ExchangeStates.selecting_whitelist_address.state:
        await _show_amount_step(callback, state, data["from_currency"])
        return
    if current_state in (
        ExchangeStates.entering_address.state,
        ExchangeStates.confirming_whitelist_submission.state,
        ExchangeStates.confirming.state,
    ):
        await _show_whitelist_step(callback, state, data, callback.from_user.id)
        return
    await show_main_menu(callback, state)


@router.callback_query(F.data.startswith("orders:filter:"))
async def cb_orders_filter(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, filter_value, page_value = callback.data.split(":")
    order_filter = normalize_order_filter(filter_value)
    await _show_orders_page(callback, user_id=callback.from_user.id, page=int(page_value), order_filter=order_filter)


@router.callback_query(F.data.startswith("orders:detail:"))
async def cb_order_detail(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    _, _, order_id, page_value, filter_value = callback.data.split(":")
    order = await db.get_order_for_user(order_id, callback.from_user.id)
    if not order:
        await callback.answer("⛔ Не ваша заявка или она не найдена.", show_alert=True)
        return
    enriched_order = build_order_detail_payload(order)
    current_filter = normalize_order_filter(filter_value)
    await callback.message.edit_text(
        _build_order_detail_text(enriched_order),
        reply_markup=build_order_detail_keyboard(order_id, int(page_value), current_filter, enriched_order["can_repeat"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("orders:repeat:"))
async def cb_order_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    order_id = callback.data.split(":")[-1]
    order = await db.get_order_for_user(order_id, callback.from_user.id)
    if not order:
        await callback.answer("⛔ Не ваша заявка или она не найдена.", show_alert=True)
        return
    if not can_repeat_order(order):
        await callback.answer("Повтор доступен только для завершённых или отменённых заявок.", show_alert=True)
        return

    repeat_seed = build_repeat_seed(order)
    await state.update_data(**repeat_seed, already_created=False)
    await _show_confirmation(callback, state)
    await callback.answer()
