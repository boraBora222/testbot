from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot import crypto_exchange_bot as bot_module
from bot.states import ProfileDocumentStates
from shared.services.documents import (
    ProfileDocumentPersistenceError,
    ProfileDocumentStorageUnavailableError,
    ProfileDocumentValidationError,
    StoredProfileDocument,
    TelegramDocumentTransferError,
)


def test_build_profile_keyboard_includes_documents_entry() -> None:
    keyboard = bot_module.build_profile_keyboard()

    assert keyboard.inline_keyboard[0][0].text == "📂 Документы"
    assert keyboard.inline_keyboard[0][0].callback_data == "profile:documents"


@pytest.mark.anyio
async def test_profile_document_type_callback_moves_bot_to_upload_step() -> None:
    callback = SimpleNamespace(
        data="profile:documents:type:inn",
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
        from_user=SimpleNamespace(id=321),
    )
    state = SimpleNamespace(
        set_state=AsyncMock(),
        update_data=AsyncMock(),
    )

    await bot_module.cb_profile_document_type(callback, state)

    state.set_state.assert_awaited_once_with(ProfileDocumentStates.waiting_document)
    state.update_data.assert_awaited_once_with(profile_document_type="inn")
    callback.message.edit_text.assert_awaited_once()
    prompt_text = callback.message.edit_text.await_args.args[0]
    assert "ИНН" in prompt_text
    callback.answer.assert_awaited_once()


def _build_document_message(*, file_name: str = "inn.pdf", file_size: int = 1024) -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=321, username="client321", first_name="Client"),
        document=SimpleNamespace(
            file_id="telegram-file-1",
            file_name=file_name,
            file_size=file_size,
        ),
        answer=AsyncMock(),
    )


def _build_state(*, document_type: str = "inn") -> SimpleNamespace:
    return SimpleNamespace(
        get_data=AsyncMock(return_value={bot_module.PROFILE_DOCUMENT_STATE_KEY: document_type}),
        clear=AsyncMock(),
    )


@pytest.mark.anyio
async def test_handle_profile_document_upload_uses_shared_transfer_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _build_document_message()
    state = _build_state()
    captured: dict[str, object] = {}

    async def fake_transfer_profile_document_from_telegram(**kwargs):
        captured.update(kwargs)
        return StoredProfileDocument(
            document={
                "id": "mat_inn",
                "file_name": "inn.pdf",
                "created_at": datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc),
            },
            replaced=False,
        )

    monkeypatch.setattr(bot_module, "_apply_message_rate_limit", AsyncMock(return_value=True))
    monkeypatch.setattr(
        bot_module.document_service,
        "validate_profile_document_metadata",
        lambda **kwargs: ("inn.pdf", "application/pdf"),
    )
    monkeypatch.setattr(
        bot_module.document_service,
        "transfer_profile_document_from_telegram",
        fake_transfer_profile_document_from_telegram,
    )

    await bot_module.handle_profile_document_upload(message, state)

    assert captured == {
        "user_id": 321,
        "username": "client321",
        "first_name": "Client",
        "client_doc_type": bot_module.ClientDocumentType.INN,
        "telegram_file_id": "telegram-file-1",
        "file_name": "inn.pdf",
    }
    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    success_text = message.answer.await_args.args[0]
    assert "ИНН" in success_text
    assert "inn.pdf" in success_text


@pytest.mark.anyio
async def test_handle_profile_document_upload_mentions_replace_on_reupload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _build_document_message(file_name="inn-v2.pdf")
    state = _build_state()

    async def fake_transfer_profile_document_from_telegram(**kwargs):
        return StoredProfileDocument(
            document={"id": "mat_inn", "file_name": "inn-v2.pdf"},
            replaced=True,
        )

    monkeypatch.setattr(bot_module, "_apply_message_rate_limit", AsyncMock(return_value=True))
    monkeypatch.setattr(
        bot_module.document_service,
        "validate_profile_document_metadata",
        lambda **kwargs: ("inn-v2.pdf", "application/pdf"),
    )
    monkeypatch.setattr(
        bot_module.document_service,
        "transfer_profile_document_from_telegram",
        fake_transfer_profile_document_from_telegram,
    )

    await bot_module.handle_profile_document_upload(message, state)

    success_text = message.answer.await_args.args[0]
    assert "заменён новым" in success_text


@pytest.mark.anyio
async def test_handle_profile_document_upload_returns_clear_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = _build_document_message(file_name="payload.exe")
    state = _build_state()

    monkeypatch.setattr(bot_module, "_apply_message_rate_limit", AsyncMock(return_value=True))

    def fake_validate_profile_document_metadata(**kwargs):
        raise ProfileDocumentValidationError("Unsupported profile document format.")

    monkeypatch.setattr(
        bot_module.document_service,
        "validate_profile_document_metadata",
        fake_validate_profile_document_metadata,
    )

    await bot_module.handle_profile_document_upload(message, state)

    state.clear.assert_not_awaited()
    message.answer.assert_awaited_once_with(
        "Неподдерживаемый формат файла. Поддерживаются PDF, DOC, DOCX, XLS, XLSX, JPG, PNG."
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("exc", "expected_message"),
    [
        (
            TelegramDocumentTransferError("Telegram source file could not be downloaded."),
            "Не удалось скачать файл из Telegram. Отправьте документ ещё раз.",
        ),
        (
            ProfileDocumentStorageUnavailableError("Profile document storage is temporarily unavailable."),
            "Хранилище документов временно недоступно. Попробуйте позже.",
        ),
        (
            ProfileDocumentPersistenceError("Profile document could not be saved."),
            "Не удалось сохранить запись документа. Попробуйте позже.",
        ),
    ],
)
async def test_handle_profile_document_upload_returns_step_specific_failure_messages(
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception,
    expected_message: str,
) -> None:
    message = _build_document_message()
    state = _build_state()

    async def fake_transfer_profile_document_from_telegram(**kwargs):
        raise exc

    monkeypatch.setattr(bot_module, "_apply_message_rate_limit", AsyncMock(return_value=True))
    monkeypatch.setattr(
        bot_module.document_service,
        "validate_profile_document_metadata",
        lambda **kwargs: ("inn.pdf", "application/pdf"),
    )
    monkeypatch.setattr(
        bot_module.document_service,
        "transfer_profile_document_from_telegram",
        fake_transfer_profile_document_from_telegram,
    )

    await bot_module.handle_profile_document_upload(message, state)

    state.clear.assert_not_awaited()
    message.answer.assert_awaited_once_with(expected_message)
