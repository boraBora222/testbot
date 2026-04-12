import smtplib

import pytest

import web.services.email_service as email_service


class FakeSmtpClient:
    def __init__(self, host: str, port: int, timeout: int) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.ehlo_calls = 0
        self.starttls_calls = 0
        self.login_calls: list[tuple[str, str]] = []
        self.messages = []

    def __enter__(self) -> "FakeSmtpClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def ehlo(self) -> None:
        self.ehlo_calls += 1

    def starttls(self) -> None:
        self.starttls_calls += 1

    def login(self, username: str, password: str) -> None:
        self.login_calls.append((username, password))

    def send_message(self, message) -> None:
        self.messages.append(message)


def test_send_email_sync_uses_starttls_for_standard_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[FakeSmtpClient] = []

    def fake_smtp(host: str, port: int, timeout: int) -> FakeSmtpClient:
        client = FakeSmtpClient(host, port, timeout)
        clients.append(client)
        return client

    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "smtp_port", 587)
    monkeypatch.setattr(email_service.settings, "smtp_username", "smtp-user")
    monkeypatch.setattr(email_service.settings, "smtp_password", "smtp-password")
    monkeypatch.setattr(email_service.settings, "smtp_from_email", "no-reply@example.com")
    monkeypatch.setattr(email_service.settings, "smtp_use_ssl", False)
    monkeypatch.setattr(email_service.settings, "smtp_use_tls", True)
    monkeypatch.setattr(smtplib, "SMTP", fake_smtp)

    email_service._send_email_sync("user@example.com", "Verify your email", "123456")

    client = clients[0]
    assert client.host == "smtp.example.com"
    assert client.port == 587
    assert client.timeout == 30
    assert client.starttls_calls == 1
    assert client.ehlo_calls == 2
    assert client.login_calls == [("smtp-user", "smtp-password")]
    assert client.messages[0]["To"] == "user@example.com"


def test_send_email_sync_uses_implicit_ssl_without_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    clients: list[FakeSmtpClient] = []

    def fake_smtp_ssl(host: str, port: int, timeout: int) -> FakeSmtpClient:
        client = FakeSmtpClient(host, port, timeout)
        clients.append(client)
        return client

    monkeypatch.setattr(email_service.settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(email_service.settings, "smtp_port", 465)
    monkeypatch.setattr(email_service.settings, "smtp_username", "smtp-user")
    monkeypatch.setattr(email_service.settings, "smtp_password", "smtp-password")
    monkeypatch.setattr(email_service.settings, "smtp_from_email", "no-reply@example.com")
    monkeypatch.setattr(email_service.settings, "smtp_use_ssl", True)
    monkeypatch.setattr(email_service.settings, "smtp_use_tls", True)
    monkeypatch.setattr(smtplib, "SMTP_SSL", fake_smtp_ssl)

    email_service._send_email_sync("user@example.com", "Reset your password", "654321")

    client = clients[0]
    assert client.host == "smtp.example.com"
    assert client.port == 465
    assert client.starttls_calls == 0
    assert client.ehlo_calls == 1
    assert client.login_calls == [("smtp-user", "smtp-password")]
    assert client.messages[0]["To"] == "user@example.com"
