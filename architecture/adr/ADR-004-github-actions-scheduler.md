# ADR-004: GitHub Actions Cron over Celery or a Distributed Scheduler

- **Status:** Accepted
- **Date:** 2026-07-21
- **Deciders:** Project architecture team

## Context
The core workload is a **single daily batch**: collect postings, deduplicate, embed, rank against the resume, and email an Excel report. It is not high-frequency, not high-concurrency, and not latency-sensitive. It also drags in a heavy ML stack (`torch`, `transformers`) that we do *not* want resident in the always-on FastAPI image. The team is tiny and there is no appetite to operate a message broker or an always-on worker fleet for one job a day.

## Decision
Run the daily pipeline as a **GitHub Actions cron workflow**. Actions provides managed, effectively free scheduling, encrypted secrets, captured logs, and artifact upload, with no broker or always-on worker to run or pay for. The heavy ML dependencies live only in the Actions job, keeping the API image lean.

## Alternatives Considered
- **Celery + Redis/RabbitMQ + beat** — the standard distributed-task answer, but it means running and paying for an always-on broker and worker, plus beat, to service a single daily job. Operational weight far exceeds the need.
- **APScheduler in-process** — simple, but requires an always-on host to live in and offers no HA or managed retry/log story.
- **Cloud schedulers (Render Cron, Cloud Scheduler, cron on a VM)** — viable, but either add another managed dependency/cost or require us to operate a VM.

## Trade-offs
We gain zero fixed infrastructure cost, managed secrets and logs, and separation of the ML stack from the serving image. We give up suitability for sub-minute or highly concurrent scheduling: Actions has job runtime limits, cold starts, and queueing behaviour unsuited to real-time fan-out. We also accept coupling to GitHub as the scheduling substrate.

## Consequences
Positive: nothing to operate between runs; cheap, observable, and reproducible. Negative: Actions logs are ephemeral, so run history must be persisted elsewhere. To address this, every run writes to a `scheduler_logs` MongoDB collection with a `run_id`/`correlation_id`, giving durable, queryable run history independent of GitHub's retention. If the workload ever grows toward real-time or high-fanout processing, this decision should be revisited in favour of a queue-based worker (e.g. Celery or a cloud task queue).
