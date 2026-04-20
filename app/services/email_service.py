import asyncio
import socket
import smtplib
from email.message import EmailMessage

from fastapi import HTTPException, status

from app.core.config import settings


class EmailSender:
    """SMTP email sender used for account validation codes."""

    def __init__(self) -> None:
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._from_email = settings.smtp_from_email or settings.smtp_username
        self._from_name = settings.smtp_from_name
        self._use_tls = settings.smtp_use_tls
        self._use_ssl = settings.smtp_use_ssl

    @property
    def is_configured(self) -> bool:
        placeholder_values = {
            "smtp.example.com",
            "your-smtp-username",
            "your-smtp-password",
            "no-reply@example.com",
        }
        configured_values = {
            self._host,
            self._username,
            self._password,
            self._from_email,
        }
        return bool(
            self._host
            and self._port
            and self._username
            and self._password
            and self._from_email
            and configured_values.isdisjoint(placeholder_values)
        )

    async def send_validation_code(self, to_email: str, code: str, purpose: str) -> None:
        if not self.is_configured:
            if settings.app_env == "development":
                return
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SMTP is not configured",
            )

        subject = "Your AgentHub validation code"
        plain_text = (
            f"Use this validation code for {purpose}:\n\n"
            f"{code}\n\n"
            f"This code expires in {settings.email_code_expire_minutes} minutes."
        )

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{self._from_name} <{self._from_email}>"
        message["To"] = to_email
        message.set_content(plain_text)

        try:
            await asyncio.to_thread(self._send, message)
        except (OSError, smtplib.SMTPException, socket.gaierror) as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to send validation email",
            ) from exc

    def _send(self, message: EmailMessage) -> None:
        smtp_class = smtplib.SMTP_SSL if self._use_ssl else smtplib.SMTP
        with smtp_class(self._host, self._port, timeout=20) as smtp:
            if self._use_tls and not self._use_ssl:
                smtp.starttls()
            smtp.login(self._username, self._password)
            smtp.send_message(message)


email_sender = EmailSender()
