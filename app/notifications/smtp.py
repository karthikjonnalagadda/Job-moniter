"""SMTP notifier — responsive HTML email with attachments, retry, rate limiting.

Sends multipart (plain + HTML) email via ``smtplib`` on a worker thread (so the
async API is never blocked). Includes:

* **retry** with exponential backoff on transient SMTP errors;
* **rate limiting** (a minimum interval between sends);
* **failure recovery** — after the retry budget is exhausted the final error is
  raised as ``NotificationError`` so the caller can record a failed delivery.
"""

from __future__ import annotations

import asyncio
import smtplib
import time
from email.message import EmailMessage
from typing import TYPE_CHECKING

from app.config.logging import get_logger
from app.core.exceptions import NotificationError
from app.notifications.base import NotificationMessage, Notifier

if TYPE_CHECKING:
    from app.config.settings import SmtpSettings

log = get_logger("notify")


class SmtpNotifier(Notifier):
    """Deliver a report by email over SMTP."""

    channel = "smtp"

    def __init__(
        self,
        settings: SmtpSettings,
        *,
        max_retries: int = 3,
        min_interval_seconds: float = 0.0,
        backoff_base: float = 0.5,
    ) -> None:
        self._settings = settings
        self._max_retries = max_retries
        self._min_interval = min_interval_seconds
        self._backoff_base = backoff_base
        self._last_sent_at = 0.0

    async def send(self, message: NotificationMessage) -> None:
        if not self._settings.to_address:
            raise NotificationError("SMTP notifier requires a recipient (smtp.to_address)")
        await self._rate_limit()
        email = self._build(message)

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                await asyncio.to_thread(self._deliver, email)
                self._last_sent_at = time.monotonic()
                log.info("Email sent to {} (attempt {})", self._settings.to_address, attempt)
                return
            except (smtplib.SMTPException, OSError) as exc:
                last_error = exc
                log.warning("SMTP send failed (attempt {}/{}): {}", attempt, self._max_retries, exc)
                if attempt < self._max_retries:
                    await asyncio.sleep(self._backoff_base * 2 ** (attempt - 1))
        raise NotificationError(
            f"Email delivery failed after {self._max_retries} attempts: {last_error}"
        )

    async def health_check(self) -> bool:
        try:
            await asyncio.to_thread(self._probe)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("SMTP health check failed: {}", exc)
            return False
        return True

    # ---- internals ------------------------------------------------------
    async def _rate_limit(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_sent_at
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)

    def _build(self, message: NotificationMessage) -> EmailMessage:
        email = EmailMessage()
        email["Subject"] = message.subject
        email["From"] = self._settings.from_address
        email["To"] = self._settings.to_address
        email.set_content(message.body_text)
        if message.body_html:
            email.add_alternative(message.body_html, subtype="html")
        for path in message.attachments:
            data = path.read_bytes()
            maintype, subtype = _mime_type(path.suffix)
            email.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)
        return email

    def _deliver(self, email: EmailMessage) -> None:
        s = self._settings
        # Observability: connection parameters only — never the password/secret.
        log.info("SMTP connect host={} port={} tls={} from={} to={}",
                 s.host, s.port, s.use_tls, s.from_address, s.to_address)
        with smtplib.SMTP(s.host, s.port, timeout=30) as server:
            if s.use_tls:
                server.starttls()
            password = s.password.get_secret_value()
            if s.username and password:
                server.login(s.username, password)
                log.info("SMTP authentication succeeded for {}", s.username)
            server.send_message(email)

    def _probe(self) -> None:
        with smtplib.SMTP(self._settings.host, self._settings.port, timeout=10) as server:
            server.noop()


def _mime_type(suffix: str) -> tuple[str, str]:
    return {
        ".xlsx": ("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ".pdf": ("application", "pdf"),
        ".csv": ("text", "csv"),
        ".gz": ("application", "gzip"),
        ".json": ("application", "json"),
        ".html": ("text", "html"),
    }.get(suffix.lower(), ("application", "octet-stream"))
