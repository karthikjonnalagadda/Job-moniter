"""ATS auto-detection from career URLs."""

from __future__ import annotations

import pytest
from app.models.enums import ATSType
from app.routing.detector import ATSDetector

DETECTOR = ATSDetector()


@pytest.mark.parametrize(
    ("url", "ats", "token"),
    [
        ("https://boards.greenhouse.io/acme", ATSType.GREENHOUSE, "acme"),
        ("https://jobs.lever.co/acme", ATSType.LEVER, "acme"),
        ("https://jobs.ashbyhq.com/acme", ATSType.ASHBY, "acme"),
        ("https://acme.bamboohr.com/careers", ATSType.BAMBOOHR, "acme"),
        ("https://acme.recruitee.com", ATSType.RECRUITEE, "acme"),
        ("https://acme.breezy.hr/", ATSType.BREEZYHR, "acme"),
        ("https://acme.applytojob.com/apply", ATSType.JAZZHR, "acme"),
        ("https://careers.smartrecruiters.com/acme", ATSType.SMARTRECRUITERS, "acme"),
        ("https://careers-acme.icims.com/jobs", ATSType.ICIMS, "careers-acme"),
    ],
)
def test_detects_platform_and_token(url: str, ats: ATSType, token: str) -> None:
    detection = DETECTOR.detect(url)
    assert detection.ats_type == ats
    assert detection.token == token
    assert detection.confidence >= 0.9


def test_workday_detected_without_token() -> None:
    detection = DETECTOR.detect("https://acme.wd1.myworkdayjobs.com/en-US/External")
    assert detection.ats_type == ATSType.WORKDAY
    assert detection.token is None  # tenant/site live deeper; not a subdomain token
    assert detection.platform == "Workday"


def test_unknown_url_not_detected() -> None:
    detection = DETECTOR.detect("https://www.tcs.com/careers")
    assert detection.ats_type == ATSType.UNKNOWN
    assert detection.detected is False


def test_empty_and_bare_host() -> None:
    assert DETECTOR.detect(None).ats_type == ATSType.UNKNOWN
    assert DETECTOR.detect("acme.lever.co/acme").ats_type == ATSType.LEVER  # scheme-less
