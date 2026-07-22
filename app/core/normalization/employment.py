"""Employment-type normalization — free text → ``EmploymentType`` enum."""

from __future__ import annotations

from app.models.enums import EmploymentType

# Order matters: earlier, more specific keywords win (e.g. "graduate program"
# before "full time", "internship" before "part time").
_KEYWORDS: tuple[tuple[EmploymentType, tuple[str, ...]], ...] = (
    (EmploymentType.GRADUATE_PROGRAM, ("graduate program", "graduate programme", "new grad")),
    (EmploymentType.APPRENTICESHIP, ("apprentice", "apprenticeship")),
    (EmploymentType.INTERNSHIP, ("intern", "internship", "trainee")),
    (EmploymentType.FREELANCE, ("freelance", "freelancer")),
    (EmploymentType.CONTRACT, ("contract", "contractor", "c2h", "b2b")),
    (EmploymentType.TEMPORARY, ("temporary", "temp", "seasonal")),
    (EmploymentType.PART_TIME, ("part time", "part-time", "parttime")),
    (EmploymentType.FULL_TIME, ("full time", "full-time", "fulltime", "permanent", "regular")),
)


class EmploymentNormalizer:
    """Classify a posting's employment type from free text."""

    def parse(self, text: str | None) -> EmploymentType:
        if not text:
            return EmploymentType.UNKNOWN
        lowered = str(text).lower()
        for employment_type, keywords in _KEYWORDS:
            if any(keyword in lowered for keyword in keywords):
                return employment_type
        return EmploymentType.UNKNOWN
