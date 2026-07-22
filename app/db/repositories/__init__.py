"""Repository implementations (Repository Pattern over MongoDB/Motor)."""

from app.db.repositories.base import MongoRepository, Repository
from app.db.repositories.benchmarks import BenchmarkRepository
from app.db.repositories.companies import CompanyRepository
from app.db.repositories.config import ConfigRepository
from app.db.repositories.dead_letters import DeadLetterRepository
from app.db.repositories.import_history import ImportHistoryRepository
from app.db.repositories.jobs import JobRepository
from app.db.repositories.raw_payloads import RawPayloadRepository
from app.db.repositories.retry_queue import RetryQueueRepository
from app.db.repositories.runs import RunRepository
from app.db.repositories.user_preferences import UserPreferencesRepository
from app.db.repositories.users import UserRepository

__all__ = [
    "BenchmarkRepository",
    "CompanyRepository",
    "ConfigRepository",
    "DeadLetterRepository",
    "ImportHistoryRepository",
    "JobRepository",
    "MongoRepository",
    "RawPayloadRepository",
    "Repository",
    "RetryQueueRepository",
    "RunRepository",
    "UserPreferencesRepository",
    "UserRepository",
]
