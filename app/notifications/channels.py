"""Notification channel interfaces + registry.

SMTP is fully implemented (``app/notifications/smtp.py``). The other channels are
registered interface stubs — the architecture is ready for them (same ``Notifier``
port, same registry) without any implementation yet. Each stub advertises itself
as unconfigured via ``health_check`` and refuses to send until implemented, so
enabling one later is a drop-in, not a redesign (mirrors the collector plugin
pattern).
"""

from __future__ import annotations

from app.core.exceptions import NotificationError
from app.notifications.base import NotificationMessage, Notifier


class _UnimplementedChannel(Notifier):
    """Base for a registered-but-unimplemented channel."""

    async def send(self, message: NotificationMessage) -> None:
        raise NotificationError(f"Channel '{self.channel}' is not implemented yet")

    async def health_check(self) -> bool:
        return False  # not configured / not implemented


class TelegramNotifier(_UnimplementedChannel):
    channel = "telegram"


class SlackNotifier(_UnimplementedChannel):
    channel = "slack"


class DiscordNotifier(_UnimplementedChannel):
    channel = "discord"


class WhatsAppNotifier(_UnimplementedChannel):
    channel = "whatsapp"


class TeamsNotifier(_UnimplementedChannel):
    channel = "teams"


# Registry: channel name -> notifier class. SMTP is added by the DI layer with
# its settings; the stubs are constructable with no arguments.
STUB_CHANNELS: dict[str, type[Notifier]] = {
    "telegram": TelegramNotifier,
    "slack": SlackNotifier,
    "discord": DiscordNotifier,
    "whatsapp": WhatsAppNotifier,
    "teams": TeamsNotifier,
}


def available_channels() -> list[str]:
    """All channel names known to the system (implemented + stubbed)."""

    return ["smtp", *STUB_CHANNELS]
