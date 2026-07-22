"""Structured logging setup built on Loguru.

Design goals:
* One-line ``configure_logging()`` called at startup.
* Human-readable colored logs in development; JSON in production
  (``JOBAGENT_LOG_JSON=true``) for ingestion by log platforms.
* Per-domain log files (scheduler, collectors, email, ranking, export, api)
  via ``bind(domain=...)`` — routed with Loguru filters. Use
  ``get_logger("collectors")`` to obtain a domain-bound logger.
* Standard-library ``logging`` (used by uvicorn, motor, httpx) is redirected
  into Loguru so all output shares one format.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

from loguru import logger

from app.core.context import current_correlation_id, current_run_id

if TYPE_CHECKING:
    from loguru import Logger, Record

    from app.config.settings import Settings

# Domains that each get their own rotating log file.
LOG_DOMAINS: tuple[str, ...] = (
    "scheduler",
    "collectors",
    "email",
    "ranking",
    "export",
    "api",
    "registry",
    "routing",
    "import",
)

_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{extra[domain]}</cyan> | "
    "<magenta>{extra[correlation_id]}</magenta> | "
    "<level>{message}</level>"
)


def _patch_record(record: Record) -> None:
    """Inject the ambient correlation/run ids into every log record.

    Runs for every record via ``logger.configure(patcher=...)`` so the ids reach
    both the console format and the JSON file sinks without any call-site work.
    """

    extra = record["extra"]
    extra.setdefault("domain", "app")
    extra["correlation_id"] = current_correlation_id()
    extra["run_id"] = current_run_id()


class _InterceptHandler(logging.Handler):
    """Redirect stdlib logging records into Loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).bind(
            domain=record.name.split(".")[0] or "stdlib"
        ).log(level, record.getMessage())


def _domain_filter(domain: str) -> Callable[[Record], bool]:
    """Build a Loguru sink filter that keeps only records bound to ``domain``."""

    def _filter(record: Record) -> bool:
        return record["extra"].get("domain") == domain

    return _filter


def configure_logging(settings: Settings) -> None:
    """Initialise sinks. Idempotent — safe to call once at startup."""

    logger.remove()
    logger.configure(
        extra={"domain": "app", "correlation_id": "-", "run_id": "-"},
        patcher=_patch_record,
    )

    # Console sink → stderr, so stdout stays clean for CLI machine-readable
    # output (JSON reports) and logs never corrupt piped data.
    if settings.log_json:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            serialize=True,
            backtrace=False,
            diagnose=False,
        )
    else:
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=_CONSOLE_FORMAT,
            colorize=True,
            backtrace=settings.debug,
            diagnose=settings.debug,
        )

    # Per-domain rotating file sinks (always JSON on disk for machine parsing).
    log_dir: Path = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    for domain in LOG_DOMAINS:
        logger.add(
            log_dir / f"{domain}.log",
            level=settings.log_level,
            serialize=True,
            rotation="10 MB",
            retention="14 days",
            compression="zip",
            enqueue=True,  # async-safe across the pipeline
            filter=_domain_filter(domain),
        )

    # Route stdlib + third-party loggers through Loguru.
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for noisy in ("uvicorn", "uvicorn.access", "uvicorn.error", "motor", "httpx"):
        logging.getLogger(noisy).handlers = [_InterceptHandler()]
        logging.getLogger(noisy).propagate = False

    logger.bind(domain="api").info(
        "Logging configured (level={}, json={})", settings.log_level, settings.log_json
    )


def get_logger(domain: str = "app") -> Logger:
    """Return a logger bound to a domain (one of ``LOG_DOMAINS`` or ``app``)."""

    return logger.bind(domain=domain)
