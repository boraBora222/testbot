from bot.crypto_exchange_bot import build_reply_main_menu_keyboard, settings


def test_build_reply_main_menu_keyboard_uses_web_app_for_https_site(monkeypatch) -> None:
    monkeypatch.setattr(settings, "front_base_url", "https://example.com")

    keyboard = build_reply_main_menu_keyboard()
    site_button = keyboard.keyboard[1][2]

    assert site_button.text == "🌐 Сайт"
    assert site_button.web_app is not None
    assert site_button.web_app.url == "https://example.com"


def test_build_reply_main_menu_keyboard_keeps_plain_site_button_for_http_site(monkeypatch) -> None:
    monkeypatch.setattr(settings, "front_base_url", "http://localhost:5138")

    keyboard = build_reply_main_menu_keyboard()
    site_button = keyboard.keyboard[1][2]

    assert site_button.text == "🌐 Сайт"
    assert site_button.web_app is None
