"""Company classification + priority tiers."""

from __future__ import annotations

from app.core.classification import (
    bucket,
    build_priority_map,
    classify,
    priority_score,
    priority_tier,
)


def test_priority_tiers() -> None:
    assert priority_tier("ai_genai") == 1
    assert priority_tier("saas") == 1
    assert priority_tier("unicorn") == 1
    assert priority_tier("fintech") == 2
    assert priority_tier("healthtech") == 2
    assert priority_tier("gcc") == 3
    assert priority_tier("it_services") == 4
    assert priority_tier("consulting") == 4
    assert priority_tier("manufacturing") == 5
    assert priority_tier(None) == 5


def test_priority_scores_monotonic() -> None:
    assert priority_score("ai_genai") > priority_score("fintech") > priority_score("gcc")
    assert priority_score("gcc") > priority_score("it_services") > priority_score("manufacturing")
    assert 0.0 <= priority_score("manufacturing") <= 1.0


def test_bucket_labels() -> None:
    assert bucket("ai_genai") == "Indian AI Company"
    assert bucket("gcc") == "GCC / Global Product (India)"
    assert bucket("it_services") == "Indian MNC / IT Services"
    assert bucket("nonsense") == "Other (sector)"


def test_classify_and_priority_map() -> None:
    companies = [
        {"company_name": "Sarvam AI", "category": "ai_genai"},
        {"company_name": "TCS", "category": "it_services"},
        {"company_name": "Some Bank", "category": "bfsi"},
    ]
    c = classify(companies[0])
    assert c["priority_tier"] == 1 and c["bucket"] == "Indian AI Company"
    pmap = build_priority_map(companies)
    assert pmap["sarvam ai"] == 1.0
    assert pmap["tcs"] == 0.4
    assert pmap["some bank"] == 0.2
