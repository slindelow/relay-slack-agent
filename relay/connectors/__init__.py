"""Source connector package for RELAY."""

from relay.connectors.base import Connector
from relay.connectors.registry import get_connector

__all__ = ["Connector", "get_connector"]
