"""Notification port.

A single generic interface so new channels (Telegram, Slack, Discord, WhatsApp)
are added later without touching the pipeline. Phase 2 defines the interface;
Phase 11 implements ``SmtpNotifier`` only. Future channels register themselves
the same way collectors do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import Field

from app.models.base import AppBaseModel


class NotificationMessage(AppBaseModel):
    """Channel-agnostic message. Channels use whichever fields apply."""

    subject: str
    body_text: str
    body_html: str | None = None
    attachments: list[Path] = Field(default_factory=list)


class Notifier(ABC):
    """Send a notification through one channel."""

    #: Registry key, e.g. ``"smtp"``, ``"telegram"``.
    channel: str = "base"

    @abstractmethod
    async def send(self, message: NotificationMessage) -> None:
        """Deliver the message. Raises ``NotificationError`` on failure."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the channel is configured and reachable."""
