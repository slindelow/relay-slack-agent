"""Connector factory — maps connector_type strings to Connector subclasses."""

from relay.connectors.base import Connector

_REGISTRY: dict[str, str] = {
    "google_drive": "relay.connectors.google_drive.GoogleDriveConnector",
    "github": "relay.connectors.github.GitHubConnector",
}


def get_connector(connector_type: str) -> Connector:
    """Return a fresh Connector instance for the given type.

    Lazy-imports the implementation module to avoid circular imports at
    package load time.
    """
    module_path = _REGISTRY.get(connector_type)
    if module_path is None:
        raise ValueError(f"Unknown connector type: {connector_type!r}. Valid types: {list(_REGISTRY)}")

    module_name, class_name = module_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name)
    return cls()
