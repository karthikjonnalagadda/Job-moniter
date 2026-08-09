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


@pytest.mark.parametrize(
    ("url", "ats"),
    [
        # ---- Required boundary cases (must-detect) ----
        ("https://workday.wd5.myworkdayjobs.com/Workday/", ATSType.WORKDAY),
        ("https://boards.greenhouse.io/acme", ATSType.GREENHOUSE),
        ("https://jobs.lever.co/acme", ATSType.LEVER),
        ("https://jobs.ashbyhq.com/acme", ATSType.ASHBY),
        ("https://careers.smartrecruiters.com/acme", ATSType.SMARTRECRUITERS),
        ("https://careers-acme.icims.com/jobs", ATSType.ICIMS),
        ("https://acme.wd3.myworkdaysite.com/careers", ATSType.WORKDAY),
        ("https://performancemanager.successfactors.com/acme", ATSType.SUCCESSFACTORS),
        ("https://acme.oraclecloud.com/hcmUI/CandidateExperience", ATSType.ORACLE),
        # ---- Newly-added platforms ----
        ("https://acme.taleo.net/careersection", ATSType.TALEO),
        ("https://apply.workable.com/acme/", ATSType.WORKABLE),
        ("https://acme.phenompeople.com/careers", ATSType.PHENOM),
        ("https://acme.eightfold.ai/careers", ATSType.EIGHTFOLD),
        ("https://acme.avature.net/careers", ATSType.AVATURE),
        ("https://acme.ultipro.com", ATSType.UKG),
        ("https://acme.dayforcehcm.com/CandidatePortal", ATSType.DAYFORCE),
    ],
)
def test_detects_expanded_platforms(url: str, ats: ATSType) -> None:
    assert DETECTOR.detect(url).ats_type == ats


@pytest.mark.parametrize(
    "url",
    [
        # Substring collisions that must NOT be misdetected (boundary-aware).
        "https://www.unilever.com/careers",          # contains "lever.co"
        "https://careers.hindustanunilever.com/",    # contains "lever.co"
        "https://www.workday.com/en-us/company.html",  # corp site, not *.myworkdayjobs.com
        "https://www.ukgear.com/jobs",               # contains "ukg" but not ukg.com
        "https://www.tcs.com/careers",               # plain corporate careers page
    ],
)
def test_no_substring_false_positives(url: str) -> None:
    assert DETECTOR.detect(url).ats_type == ATSType.UNKNOWN
