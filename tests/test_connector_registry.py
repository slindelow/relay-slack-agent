"""Unit tests for the connector registry."""

import pytest

from relay.connectors.registry import get_connector


def test_get_connector_google_drive():
    connector = get_connector("google_drive")
    from relay.connectors.google_drive import GoogleDriveConnector
    assert isinstance(connector, GoogleDriveConnector)


def test_get_connector_github():
    connector = get_connector("github")
    from relay.connectors.github import GitHubConnector
    assert isinstance(connector, GitHubConnector)


def test_get_connector_unknown_raises():
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_connector("notion")


def test_get_connector_empty_raises():
    with pytest.raises(ValueError, match="Unknown connector type"):
        get_connector("")
