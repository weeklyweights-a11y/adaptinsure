"""Discovery Engine — analyze incoming data formats and build client profiles."""

from src.discovery.engine import DiscoveryEngine
from src.discovery.profile import ClientProfile, FieldInfo

__all__ = ["ClientProfile", "DiscoveryEngine", "FieldInfo"]
