"""Canonical metric names.

Centralised so producers (pipeline, collectors, API) and the ``/metrics``
endpoint never disagree on a string. Names follow Prometheus conventions
(snake_case, base-unit suffixes) so a Prometheus/Grafana exporter can adopt them
verbatim later.
"""

from __future__ import annotations

from typing import Final

# ---- Counters (monotonic) ---------------------------------------------------
JOBS_COLLECTED: Final = "jobs_collected_total"
DUPLICATES_REMOVED: Final = "duplicates_removed_total"
COLLECTORS_EXECUTED: Final = "collectors_executed_total"
COLLECTORS_FAILED: Final = "collectors_failed_total"
API_REQUESTS: Final = "api_requests_total"
EMAILS_SENT: Final = "emails_sent_total"

# ---- Summaries (count + sum → average / p-agnostic) -------------------------
RANKING_DURATION: Final = "ranking_duration_seconds"
EMAIL_DURATION: Final = "email_duration_seconds"
SCHEDULER_DURATION: Final = "scheduler_duration_seconds"
COLLECTOR_DURATION: Final = "collector_duration_seconds"
MATCH_SCORE: Final = "match_score"  # observed per ranked job → average exposed

# ---- Gauges (point-in-time) -------------------------------------------------
JOBS_IN_LAST_RUN: Final = "jobs_in_last_run"
LAST_RUN_TIMESTAMP: Final = "last_run_timestamp_seconds"

# ---- Budgets / SLAs ---------------------------------------------------------
BUDGET_VIOLATIONS: Final = "budget_violations_total"
