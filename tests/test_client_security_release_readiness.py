from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_public_copy_uses_active_whitelist_wording() -> None:
    ru_locale = (REPO_ROOT / "front" / "src" / "i18n" / "locales" / "ru.ts").read_text(encoding="utf-8")
    en_locale = (REPO_ROOT / "front" / "src" / "i18n" / "locales" / "en.ts").read_text(encoding="utf-8")

    assert "Whitelist-проверка после заявки." not in ru_locale
    assert "Проверка адреса обязательна для первой сделки" not in ru_locale
    assert "Whitelist check after request." not in en_locale
    assert "Address verification is required for the first deal" not in en_locale

    assert "Сделки и выводы доступны только" in ru_locale
    assert "1 000 000 ₽/день" in ru_locale
    assert "10 000 000 ₽/день" in ru_locale
    assert "Deals and withdrawals are allowed only" in en_locale
    assert "1,000,000 ₽/day" in en_locale
    assert "10,000,000 ₽/day" in en_locale


def test_dashboard_copy_uses_unified_active_whitelist_rule() -> None:
    settings_page = (
        REPO_ROOT / "front" / "src" / "pages" / "dashboard" / "settings" / "index.tsx"
    ).read_text(encoding="utf-8")

    assert "Никаких пост-проверок после заявки." not in settings_page
    assert "Сделки и выводы доступны только на активные адреса из whitelist." in settings_page


def test_readme_reflects_live_security_settings_flow() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "client_security_settings_rollout_checklist.md" in readme
    assert "/profile` — live profile screen with daily and monthly limits, usage, and remaining balance." in readme
    assert "Manual wallet entry in `/exchange` is used only to submit a new whitelist address for moderation." in readme


def test_rollout_checklist_covers_sections_7_8_and_9() -> None:
    checklist = (
        REPO_ROOT / "docs" / "specifications" / "client_security_settings_rollout_checklist.md"
    ).read_text(encoding="utf-8")

    assert "sections `7`, `8`, and `9`" in checklist
    assert "frontend, API, and bot" in checklist
    assert "00:00 UTC" in checklist
    assert "atomically" in checklist
    assert "asynchronously" in checklist
    assert "dashboard" in checklist
    assert "Telegram bot" in checklist
    assert "admin" in checklist
    assert "Release Sign-Off" in checklist
