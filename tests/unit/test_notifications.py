"""SMTP notifier (retry/rate-limit) + channel stubs."""

from __future__ import annotations

import smtplib
from pathlib import Path
from typing import ClassVar

import pytest
from app.config.settings import SmtpSettings
from app.core.exceptions import NotificationError
from app.notifications.base import NotificationMessage
from app.notifications.channels import STUB_CHANNELS, available_channels
from app.notifications.smtp import SmtpNotifier
from pydantic import SecretStr


def _settings() -> SmtpSettings:
    return SmtpSettings(
        host="localhost", port=25, username="u", password=SecretStr("p"),
        use_tls=False, from_address="from@x.com", to_address="to@x.com",
    )


class _FakeSMTP:
    sent: ClassVar[list[object]] = []

    def __init__(self, *a: object, **k: object) -> None:
        pass

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def starttls(self) -> None: ...
    def login(self, *a: object) -> None: ...
    def noop(self) -> None: ...
    def send_message(self, msg: object) -> None:
        _FakeSMTP.sent.append(msg)


async def test_smtp_send_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    notifier = SmtpNotifier(_settings())
    await notifier.send(NotificationMessage(subject="Hi", body_text="body", body_html="<b>b</b>"))
    assert len(_FakeSMTP.sent) == 1


async def test_smtp_retries_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Broken(_FakeSMTP):
        def send_message(self, msg: object) -> None:
            raise smtplib.SMTPException("boom")

    monkeypatch.setattr(smtplib, "SMTP", _Broken)
    notifier = SmtpNotifier(_settings(), max_retries=2, backoff_base=0.0)
    with pytest.raises(NotificationError):
        await notifier.send(NotificationMessage(subject="s", body_text="b"))


async def test_smtp_requires_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    settings = _settings()
    settings.to_address = ""
    with pytest.raises(NotificationError):
        await SmtpNotifier(settings).send(NotificationMessage(subject="s", body_text="b"))


async def test_smtp_attachments(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _FakeSMTP.sent = []
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    attach = tmp_path / "r.csv"
    attach.write_text("a,b\n1,2\n")
    await SmtpNotifier(_settings()).send(
        NotificationMessage(subject="s", body_text="b", attachments=[attach])
    )
    assert len(_FakeSMTP.sent) == 1


async def test_channel_stubs_unimplemented() -> None:
    assert set(STUB_CHANNELS) == {"telegram", "slack", "discord", "whatsapp", "teams"}
    assert "smtp" in available_channels()
    stub = STUB_CHANNELS["telegram"]()
    assert await stub.health_check() is False
    with pytest.raises(NotificationError):
        await stub.send(NotificationMessage(subject="s", body_text="b"))
