"""Test doubles for the shared HTTP client (no live network)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from app.http.client import HttpClient


class FakeHttpClient(HttpClient):
    """An ``HttpClient`` that returns canned responses from a handler function."""

    def __init__(self, handler: Callable[..., httpx.Response]) -> None:
        self._handler = handler
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        return self._handler(method, url, **kwargs)

    async def aclose(self) -> None:
        return None


# ---- Fixture payloads shaped like the real public APIs ----------------------
GREENHOUSE_JOBS = {
    "jobs": [
        {
            "id": 123,
            "title": "Backend Engineer",
            "updated_at": "2026-01-02T10:00:00Z",
            "location": {"name": "Remote"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            "content": "<p>Build things.</p>",
        },
        {  # invalid: empty title -> dropped by validate()
            "id": 124,
            "title": "",
            "location": {},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/124",
            "content": "",
        },
    ]
}

LEVER_PAGE_0 = [
    {
        "id": "a1",
        "text": "Platform Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/a1",
        "categories": {"location": "New York"},
        "createdAt": 1735732800000,
        "descriptionPlain": "Own the platform.",
    },
    {
        "id": "a2",
        "text": "SRE",
        "hostedUrl": "https://jobs.lever.co/acme/a2",
        "categories": {"location": "Remote"},
        "createdAt": 1735732800000,
        "descriptionPlain": "Keep it up.",
    },
]
LEVER_PAGE_1 = [
    {
        "id": "a3",
        "text": "Data Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/a3",
        "categories": {"location": "Remote"},
        "createdAt": 1735732800000,
        "descriptionPlain": "Pipelines.",
    }
]

ASHBY_JOBS = {
    "jobs": [
        {
            "id": "x1",
            "title": "ML Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/x1",
            "location": "Remote",
            "descriptionHtml": "<p>Models.</p>",
            "publishedAt": "2026-01-03T00:00:00Z",
            "isRemote": True,
        }
    ]
}

# ---- Phase-5 remainder: the other 12 ATS platforms -------------------------
WORKDAY_JOBS = {
    "total": 1,
    "jobPostings": [
        {
            "title": "Staff Engineer",
            "externalPath": "/job/Bengaluru/Staff-Engineer_JR-42",
            "locationsText": "Bengaluru, India",
            "postedOn": "Posted 3 Days Ago",
            "bulletFields": ["JR-42"],
        }
    ],
}

SMARTRECRUITERS_JOBS = {
    "totalFound": 1,
    "offset": 0,
    "limit": 100,
    "content": [
        {
            "id": "sr1",
            "name": "Product Manager",
            "ref": "https://jobs.smartrecruiters.com/acme/sr1",
            "location": {"city": "Pune", "region": "MH", "country": "in"},
            "releasedDate": "2026-01-04T00:00:00.000Z",
        }
    ],
}

BAMBOOHR_JOBS = {
    "result": [
        {
            "id": "b1",
            "jobOpeningName": "HR Business Partner",
            "location": {"city": "Hyderabad", "state": "TS", "country": "India"},
            "isRemote": "no",
            "datePosted": "2026-01-05",
        }
    ]
}

RECRUITEE_OFFERS = {
    "offers": [
        {
            "id": 55,
            "title": "Frontend Engineer",
            "careers_url": "https://acme.recruitee.com/o/frontend-engineer",
            "city": "Remote",
            "country": "India",
            "remote": True,
            "description": "Build UIs.",
            "published_at": "2026-01-06T00:00:00Z",
        }
    ]
}

TEAMTAILOR_PAGE = {
    "data": [
        {
            "id": "tt1",
            "type": "jobs",
            "attributes": {
                "title": "Growth Marketer",
                "body": "<p>Grow.</p>",
                "created-at": "2026-01-07T00:00:00Z",
                "remote-status": "fully",
            },
            "links": {"careersite-job-url": "https://acme.teamtailor.com/jobs/tt1"},
        }
    ],
    "links": {},  # no "next" -> single page
}

JOBVITE_PAGE = {
    "requisitions": [
        {
            "eId": "jv1",
            "title": "Security Analyst",
            "location": "Chennai, India",
            "date": "2026-01-08T00:00:00Z",
            "detail": "Defend.",
            "jobUrl": "https://jobs.jobvite.com/acme/job/jv1",
        }
    ],
    "page": 1,
    "pageCount": 1,
}

COMEET_POSITIONS = [
    {
        "uid": "cm1",
        "name": "Backend Engineer",
        "url_comeet_hosted_page": "https://www.comeet.com/jobs/acme/cm1",
        "location": {"city": "Bengaluru", "country": "India"},
        "details": "APIs.",
        "time_updated": "2026-01-09T00:00:00Z",
    }
]

BREEZY_POSITIONS = [
    {
        "_id": "bz1",
        "name": "DevOps Engineer",
        "url": "https://acme.breezy.hr/p/bz1",
        "location": {"city": "Remote", "country": {"name": "India"}, "is_remote": True},
        "description": "Pipelines.",
        "published_date": "2026-01-10T00:00:00Z",
    }
]

JAZZHR_JOBS = [
    {
        "id": "jz1",
        "title": "QA Engineer",
        "board_code": "abc123",
        "city": "Mumbai",
        "state": "MH",
        "country_id": "India",
        "description": "Test.",
        "original_open_date": "2026-01-11",
    }
]

ICIMS_JOBS = {
    "searchResults": [
        {
            "id": "ic1",
            "jobTitle": "Data Engineer",
            "url": "https://careers-acme.icims.com/jobs/ic1/job",
            "location": "Gurugram, India",
            "postedDate": "2026-01-12T00:00:00Z",
        }
    ]
}

ORACLE_REQS = {
    "items": [
        {
            "requisitionList": [
                {
                    "Id": "or1",
                    "Title": "Cloud Architect",
                    "RequisitionURL": "https://acme.fa.oraclecloud.com/job/or1",
                    "PrimaryLocation": "Bengaluru, India",
                    "PostedDate": "2026-01-13T00:00:00Z",
                    "ExternalDescriptionStr": "Architect.",
                }
            ]
        }
    ]
}

SUCCESSFACTORS_REQS = {
    "d": {
        "results": [
            {
                "jobReqId": "sf1",
                "jobTitle": "SAP Consultant",
                "postingUrl": "https://acme.successfactors.com/job/sf1",
                "location": "Noida, India",
                "jobDescription": "Consult.",
                "boardPostingDate": "/Date(1736726400000)/",
            }
        ]
    }
}
