"""Company classification + search-priority.

Maps a company (its detected ``category`` plus name/size hints) to:

* a **classification bucket** — Indian AI Company, Indian Product/SaaS, Indian
  Unicorn, Indian Startup, Indian MNC / IT Services, GCC / Global Product,
  Consulting, or a sector label — used for reporting; and
* a **priority tier** (1 = highest) with a **priority score** in [0, 1] that the
  ranking engine rewards through its ``company_priority`` component.

Priority tiers (per product spec):
    P1  Indian AI startups · Indian product companies · Indian SaaS · unicorns
    P2  Indian analytics · FinTech · Healthcare AI
    P3  Global product companies hiring in India (GCCs)
    P4  IT services · Consulting
    P5  Everything else
"""

from __future__ import annotations

# category → classification bucket (for reports)
_BUCKET: dict[str, str] = {
    "ai_genai": "Indian AI Company",
    "analytics_ai": "Indian AI Company",
    "saas": "Indian SaaS / Product",
    "product": "Indian Product Company",
    "unicorn": "Indian Unicorn",
    "fintech": "Indian FinTech (Startup)",
    "bfsi": "BFSI",
    "healthtech": "Healthcare / HealthTech",
    "pharma": "Pharma",
    "gcc": "GCC / Global Product (India)",
    "it_services": "Indian MNC / IT Services",
    "consulting": "Consulting",
    "startup": "Indian Startup",
    "deeptech": "Indian Startup (DeepTech)",
    "ecommerce": "Consumer / E-commerce",
    "consumer": "Consumer / E-commerce",
    "retail": "Consumer / E-commerce",
    "foodtech": "Consumer / E-commerce",
    "edtech": "EdTech",
    "gaming": "Gaming",
    "telecom": "Telecom",
    "energy": "Energy",
    "automotive": "Automotive",
    "manufacturing": "Manufacturing",
    "conglomerate": "Conglomerate",
    "aerospace": "Aerospace",
    "mobility": "Mobility",
    "travel": "Travel",
    "agritech": "AgriTech",
    "robotics": "Robotics",
    "spacetech": "SpaceTech",
    "proptech": "PropTech",
    "hrtech": "HRTech",
}

# category → priority tier (1 = highest)
_TIER: dict[str, int] = {
    # P1
    "ai_genai": 1, "saas": 1, "product": 1, "unicorn": 1,
    # P2
    "analytics_ai": 2, "fintech": 2, "healthtech": 2, "startup": 2, "deeptech": 2,
    # P3
    "gcc": 3,
    # P4
    "it_services": 4, "consulting": 4,
}
_DEFAULT_TIER = 5

_TIER_SCORE: dict[int, float] = {1: 1.0, 2: 0.8, 3: 0.6, 4: 0.4, 5: 0.2}


def priority_tier(category: str | None) -> int:
    return _TIER.get((category or "").lower(), _DEFAULT_TIER)


def priority_score(category: str | None) -> float:
    """0-1 score for the ranking engine's ``company_priority`` component."""

    return _TIER_SCORE[priority_tier(category)]


def bucket(category: str | None) -> str:
    return _BUCKET.get((category or "").lower(), "Other (sector)")


def classify(company: dict) -> dict:
    """Return {bucket, priority_tier, priority_score} for a DB company record."""

    cat = company.get("category") or company.get("company_category")
    tier = priority_tier(cat)
    return {
        "company": company.get("company_name") or company.get("name"),
        "category": cat,
        "bucket": bucket(cat),
        "priority_tier": tier,
        "priority_score": _TIER_SCORE[tier],
    }


def build_priority_map(companies: list[dict]) -> dict[str, float]:
    """Map lowercased company name → priority score, for pipeline.process()."""

    out: dict[str, float] = {}
    for c in companies:
        name = (c.get("company_name") or c.get("name") or "").strip().lower()
        if name:
            out[name] = priority_score(c.get("category") or c.get("company_category"))
    return out
