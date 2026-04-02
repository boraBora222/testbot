import asyncio
import logging
import smtplib
from email.message import EmailMessage

from web.auth import fingerprint_sensitive_value
from web.config import settings

logger = logging.getLogger(__name__)


def _validate_smtp_configuration() -> None:
    missing_fields: list[str] = []
    if not settings.smtp_host:
        missing_fields.append("SMTP_HOST")
    if not settings.smtp_username:
        missing_fields.append("SMTP_USERNAME")
    if not settings.smtp_password:
        missing_fields.append("SMTP_PASSWORD")
    if not settings.smtp_from_email:
        missing_fields.append("SMTP_FROM_EMAIL")

    if missing_fields:
        logger.error("SMTP configuration is incomplete. missing_fields=%s", missing_fields)
        raise RuntimeError("SMTP configuration is incomplete.")


def _send_email_sync(recipient_email: str, subject: str, body: str) -> None:
    _validate_smtp_configuration()

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.smtp_from_email
    message["To"] = recipient_email
    message.set_content(body)

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp_client:
        smtp_client.ehlo()
        if settings.smtp_use_tls:
            smtp_client.starttls()
            smtp_client.ehlo()
        smtp_client.login(settings.smtp_username, settings.smtp_password)
        smtp_client.send_message(message)


async def send_verification_code(email: str, code: str) -> None:
    subject = "Verify your email"
    body = (
        "Your verification code is: "
        f"{code}\n\n"
        f"This code expires in {settings.auth_verification_code_ttl_minutes} minutes.\n"
        "If you did not request email verification, you can ignore this message."
    )

    try:
        await asyncio.to_thread(_send_email_sync, email, subject, body)
    except (RuntimeError, smtplib.SMTPException, OSError) as exc:
        logger.exception(
            "Failed to send verification email. email_fingerprint=%s",
            fingerprint_sensitive_value(email),
        )
        raise RuntimeError("Failed to send verification email.") from exc

    logger.info("Verification email sent successfully. email_fingerprint=%s", fingerprint_sensitive_value(email))


async def send_password_reset_code(email: str, code: str) -> None:
    subject = "Reset your password"
    body = (
        "Your password reset code is: "
        f"{code}\n\n"
        f"This code expires in {settings.auth_reset_code_ttl_minutes} minutes.\n"
        "If you did not request a password reset, you can ignore this message."
    )

    try:
        await asyncio.to_thread(_send_email_sync, email, subject, body)
    except (RuntimeError, smtplib.SMTPException, OSError) as exc:
        logger.exception(
            "Failed to send password reset email. email_fingerprint=%s",
            fingerprint_sensitive_value(email),
        )
        raise RuntimeError("Failed to send password reset email.") from exc

    logger.info("Password reset email sent successfully. email_fingerprint=%s", fingerprint_sensitive_value(email))
