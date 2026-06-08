from pathlib import Path

import yaml


def test_slack_manifest_private_beta_routes_and_scopes():
    manifest = yaml.safe_load(Path("slack-app-manifest.yaml").read_text())

    command = manifest["features"]["slash_commands"][0]
    assert command["command"] == "/relay"
    assert command["url"].endswith("/slack/events")

    settings = manifest["settings"]
    assert settings["event_subscriptions"]["request_url"].endswith("/slack/events")
    assert settings["interactivity"]["request_url"].endswith("/slack/events")
    assert "app_home_opened" in settings["event_subscriptions"]["bot_events"]
    assert "app_uninstalled" in settings["event_subscriptions"]["bot_events"]
    assert "message.groups" in settings["event_subscriptions"]["bot_events"]

    scopes = set(manifest["oauth_config"]["scopes"]["bot"])
    for required_scope in {
        "channels:read",
        "chat:write",
        "commands",
        "groups:history",
        "groups:read",
        "im:write",
        "users:read",
    }:
        assert required_scope in scopes

    assert "channels:history" not in scopes
