"""Domain + persistence models."""

from app.models.app_config import (
    AppConfigDocument,
    NotificationPreferences,
    RankingWeights,
    SchedulerConfig,
)
from app.models.base import ApiError, ApiResponse, AppBaseModel, MongoDocument, PyObjectId
from app.models.collector_benchmark import CollectorBenchmark
from app.models.common import DEFAULT_USER_ID, Location, SalaryRange
from app.models.company import Company, CompanyIntelligence
from app.models.dead_letter import DeadLetter
from app.models.job import Job, MatchDetail
from app.models.raw_payload import RawPayload
from app.models.retry_task import RetryTask
from app.models.run import SchedulerRun
from app.models.user import User
from app.models.user_preferences import ResumeVersion, UserPreferences

__all__ = [
    "DEFAULT_USER_ID",
    "ApiError",
    "ApiResponse",
    "AppBaseModel",
    "AppConfigDocument",
    "CollectorBenchmark",
    "Company",
    "CompanyIntelligence",
    "DeadLetter",
    "Job",
    "Location",
    "MatchDetail",
    "MongoDocument",
    "NotificationPreferences",
    "PyObjectId",
    "RankingWeights",
    "RawPayload",
    "ResumeVersion",
    "RetryTask",
    "SalaryRange",
    "SchedulerConfig",
    "SchedulerRun",
    "User",
    "UserPreferences",
]
