from fastapi.testclient import TestClient
import pytest

import bot.main as bot_main


class _FakeDispatcher:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.updates = []

    async def emit_startup(self, *, bot) -> None:
        self.started = True

    async def emit_shutdown(self, *, bot) -> None:
        self.stopped = True

    async def feed_update(self, bot, update) -> None:
        self.updates.append((bot, update))


def test_webhook_mode_requires_public_https_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bot_main.settings, "telegram_bot_mode", "webhook")
    monkeypatch.setattr(bot_main.settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(bot_main.settings, "front_base_url", "http://localhost:5138")

    with pytest.raises(ValueError, match="FRONT_BASE_URL must use https:// in webhook mode."):
        bot_main.settings.validate_telegram_webhook_settings()


def test_webhook_endpoint_validates_secret_and_forwards_update(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_dispatcher = _FakeDispatcher()
    fake_bot = object()
    lifecycle_events: list[str] = []

    async def fake_configure_webhook(bot, dispatcher) -> None:
        lifecycle_events.append("configure")

    async def fake_remove_webhook(bot) -> None:
        lifecycle_events.append("remove")

    monkeypatch.setattr(bot_main.settings, "telegram_bot_mode", "webhook")
    monkeypatch.setattr(bot_main.settings, "telegram_webhook_secret", "secret-token")
    monkeypatch.setattr(bot_main.settings, "front_base_url", "https://example.com")
    monkeypatch.setattr(bot_main, "configure_webhook", fake_configure_webhook)
    monkeypatch.setattr(bot_main, "remove_webhook", fake_remove_webhook)

    app = bot_main.create_webhook_app(fake_bot, fake_dispatcher)

    with TestClient(app) as client:
        rejected_response = client.post(
            bot_main.settings.telegram_webhook_path,
            json={"update_id": 1},
        )
        assert rejected_response.status_code == 403

        accepted_response = client.post(
            bot_main.settings.telegram_webhook_path,
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret-token"},
            json={
                "update_id": 1,
                "message": {
                    "message_id": 10,
                    "date": 0,
                    "chat": {"id": 123, "type": "private"},
                    "from": {"id": 123, "is_bot": False, "first_name": "Test"},
                    "text": "/start",
                },
            },
        )
        assert accepted_response.status_code == 200
        assert accepted_response.json() == {"ok": True}
        assert fake_dispatcher.started is True
        assert len(fake_dispatcher.updates) == 1
        forwarded_bot, forwarded_update = fake_dispatcher.updates[0]
        assert forwarded_bot is fake_bot
        assert forwarded_update.update_id == 1

    assert fake_dispatcher.stopped is True
    assert lifecycle_events == ["configure", "remove"]
