"""The 12 remaining ATS collectors (fixture payloads, no live calls).

Each test drives a collector's ``search`` through a ``FakeHttpClient`` returning
API-shaped fixtures and asserts the source row maps to a valid ``RawJob``.
"""

from __future__ import annotations

import httpx
import pytest
from app.collectors.ats.bamboohr import BambooHrCollector
from app.collectors.ats.breezyhr import BreezyHrCollector
from app.collectors.ats.comeet import ComeetCollector
from app.collectors.ats.icims import IcimsCollector
from app.collectors.ats.jazzhr import JazzHrCollector
from app.collectors.ats.jobvite import JobviteCollector
from app.collectors.ats.oracle import OracleCollector
from app.collectors.ats.recruitee import RecruiteeCollector
from app.collectors.ats.smartrecruiters import SmartRecruitersCollector
from app.collectors.ats.successfactors import SuccessFactorsCollector
from app.collectors.ats.teamtailor import TeamtailorCollector
from app.collectors.ats.workday import WorkdayCollector
from app.collectors.base import CollectorTarget
from app.core.exceptions import CollectorError

from tests.http_fakes import (
    BAMBOOHR_JOBS,
    BREEZY_POSITIONS,
    COMEET_POSITIONS,
    ICIMS_JOBS,
    JAZZHR_JOBS,
    JOBVITE_PAGE,
    ORACLE_REQS,
    RECRUITEE_OFFERS,
    SMARTRECRUITERS_JOBS,
    SUCCESSFACTORS_REQS,
    TEAMTAILOR_PAGE,
    WORKDAY_JOBS,
    FakeHttpClient,
)


def _handler(payload: object):
    def handler(method: str, url: str, **_: object) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


async def test_workday_posts_and_paginates() -> None:
    target = CollectorTarget(
        board_token="acme",
        company_name="Acme",
        extra={"host": "acme.wd1.myworkdayjobs.com", "tenant": "acme", "site": "External"},
    )
    collector = WorkdayCollector(FakeHttpClient(_handler(WORKDAY_JOBS)))
    jobs = await collector.search(target)
    assert len(jobs) == 1
    assert jobs[0].external_id == "JR-42"
    assert jobs[0].url == "https://acme.wd1.myworkdayjobs.com/job/Bengaluru/Staff-Engineer_JR-42"


async def test_workday_requires_host_tenant_site() -> None:
    collector = WorkdayCollector(FakeHttpClient(_handler(WORKDAY_JOBS)))
    with pytest.raises(CollectorError):
        await collector.search(CollectorTarget(board_token="acme"))


async def test_smartrecruiters_parses() -> None:
    collector = SmartRecruitersCollector(FakeHttpClient(_handler(SMARTRECRUITERS_JOBS)))
    jobs = await collector.search(CollectorTarget(board_token="acme", company_name="Acme"))
    assert jobs[0].external_id == "sr1"
    assert jobs[0].title == "Product Manager"
    assert "Pune" in (jobs[0].location or "")


async def test_bamboohr_parses() -> None:
    collector = BambooHrCollector(FakeHttpClient(_handler(BAMBOOHR_JOBS)))
    jobs = await collector.search(CollectorTarget(board_token="acme"))
    assert jobs[0].external_id == "b1"
    assert jobs[0].url == "https://acme.bamboohr.com/careers/b1"


async def test_recruitee_parses_remote() -> None:
    collector = RecruiteeCollector(FakeHttpClient(_handler(RECRUITEE_OFFERS)))
    jobs = await collector.search(CollectorTarget(board_token="acme"))
    assert jobs[0].external_id == "55"
    assert jobs[0].location == "Remote"


async def test_teamtailor_requires_api_key() -> None:
    collector = TeamtailorCollector(FakeHttpClient(_handler(TEAMTAILOR_PAGE)))
    with pytest.raises(CollectorError):
        await collector.search(CollectorTarget(board_token="acme"))


async def test_teamtailor_parses_with_auth() -> None:
    captured: dict[str, str] = {}

    def handler(method: str, url: str, **kwargs: object) -> httpx.Response:
        captured.update(kwargs.get("headers") or {})  # type: ignore[arg-type]
        return httpx.Response(200, json=TEAMTAILOR_PAGE)

    target = CollectorTarget(board_token="acme", extra={"api_key": "secret"})
    jobs = await TeamtailorCollector(FakeHttpClient(handler)).search(target)
    assert jobs[0].external_id == "tt1"
    assert jobs[0].location == "Remote"
    assert captured.get("Authorization") == "Token token=secret"


async def test_jobvite_parses_with_credentials() -> None:
    target = CollectorTarget(board_token="acme", extra={"api": "k", "sc": "s"})
    jobs = await JobviteCollector(FakeHttpClient(_handler(JOBVITE_PAGE))).search(target)
    assert jobs[0].external_id == "jv1"
    assert jobs[0].title == "Security Analyst"


async def test_comeet_parses() -> None:
    collector = ComeetCollector(FakeHttpClient(_handler(COMEET_POSITIONS)))
    jobs = await collector.search(CollectorTarget(board_token="acme"))
    assert jobs[0].external_id == "cm1"
    assert "Bengaluru" in (jobs[0].location or "")


async def test_breezyhr_parses_remote() -> None:
    collector = BreezyHrCollector(FakeHttpClient(_handler(BREEZY_POSITIONS)))
    jobs = await collector.search(CollectorTarget(board_token="acme"))
    assert jobs[0].external_id == "bz1"
    assert jobs[0].location == "Remote"


async def test_jazzhr_parses_with_api_key() -> None:
    target = CollectorTarget(board_token="acme", extra={"api_key": "k"})
    jobs = await JazzHrCollector(FakeHttpClient(_handler(JAZZHR_JOBS))).search(target)
    assert jobs[0].external_id == "jz1"
    assert jobs[0].url == "https://app.jazz.co/apply/abc123"


async def test_icims_parses_with_auth() -> None:
    target = CollectorTarget(board_token="acme", extra={"customer_id": "1234", "token": "t"})
    jobs = await IcimsCollector(FakeHttpClient(_handler(ICIMS_JOBS))).search(target)
    assert jobs[0].external_id == "ic1"
    assert jobs[0].title == "Data Engineer"


async def test_oracle_flattens_requisition_list() -> None:
    target = CollectorTarget(
        board_token="acme", extra={"host": "acme.fa.oraclecloud.com", "site": "CX_1001"}
    )
    jobs = await OracleCollector(FakeHttpClient(_handler(ORACLE_REQS))).search(target)
    assert jobs[0].external_id == "or1"
    assert jobs[0].title == "Cloud Architect"


async def test_successfactors_parses_sap_date() -> None:
    target = CollectorTarget(
        board_token="acme", extra={"host": "acme.successfactors.com", "token": "t"}
    )
    jobs = await SuccessFactorsCollector(FakeHttpClient(_handler(SUCCESSFACTORS_REQS))).search(
        target
    )
    assert jobs[0].external_id == "sf1"
    assert jobs[0].posted_at is not None  # /Date(...)/ parsed to a real datetime


async def test_auth_collector_missing_credentials_raises() -> None:
    for cls in (JobviteCollector, JazzHrCollector, IcimsCollector):
        with pytest.raises(CollectorError):
            await cls(FakeHttpClient(_handler({}))).search(CollectorTarget(board_token="acme"))
