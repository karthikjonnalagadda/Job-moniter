"""Cache abstraction.

Services depend on the ``CacheProvider`` port, never a concrete backend. Phase 2
ships the in-memory default; Redis / MongoDB-backed providers can be added later
and swapped by configuration with no service changes.
"""

from app.cache.base import CacheProvider
from app.cache.memory import InMemoryCache

__all__ = ["CacheProvider", "InMemoryCache"]
