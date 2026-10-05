"""Gửi email qua SMTP bằng thư viện chuẩn (chạy trong thread để không chặn event loop)."""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Protocol

from app.config import Settings
from app.notify.render import Email


class EmailSender(Protocol):
    @property
    def configured(self) -> bool: ...

    async def send(self, to: str, email: Email) -> None: ...


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    @property
    def configured(self) -> bool:
        return bool(self._s.smtp_host and self._s.smtp_from)

    async def send(self, to: str, email: Email) -> None:
        await asyncio.to_thread(self._send_sync, to, email)

    def _message(self, to: str, email: Email) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = email.subject
        msg["From"] = self._s.smtp_from
        msg["To"] = to
        msg["Message-ID"] = make_msgid(domain=self._s.smtp_from.rsplit("@", 1)[-1].strip("> "))
        msg.set_content(email.text)
        msg.add_alternative(email.html, subtype="html")
        return msg

    def _send_sync(self, to: str, email: Email) -> None:
        s = self._s
        ctx = ssl.create_default_context()
        smtp: smtplib.SMTP
        if s.smtp_security == "ssl":
            smtp = smtplib.SMTP_SSL(
                s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds, context=ctx
            )
        else:
            smtp = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=s.smtp_timeout_seconds)
        with smtp:
            if s.smtp_security == "starttls":
                smtp.starttls(context=ctx)
            if s.smtp_username:
                smtp.login(s.smtp_username, s.smtp_password)
            smtp.send_message(self._message(to, email))
