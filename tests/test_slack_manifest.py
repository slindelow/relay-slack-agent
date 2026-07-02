from pathlib import Path

import yaml


def test_slack_manifest_private_beta_routes_and_scopes():
    manifest = yaml.safe_load(Path("slack-app-manifest.yaml").read_text())

    command = manifest["features"]["slash_commands"][0]
    assert len(manifest["features"]["slash_commands"]) == 1
    assert command["command"] == "/relay"
    assert command["url"].endswith("/slack/events")
    assert command["should_escape"] is True
    assert "add #channel" in command["usage_hint"]
    assert "ask" in command["usage_hint"]

    app_home = manifest["features"]["app_home"]
    assert app_home["messages_tab_enabled"] is True

    settings = manifest["settings"]
    assert settings["event_subscriptions"]["request_url"].endswith("/slack/events")
    assert settings["interactivity"]["request_url"].endswith("/slack/events")
    assert "app_home_opened" in settings["event_subscriptions"]["bot_events"]
    assert "app_uninstalled" in settings["event_subscriptions"]["bot_events"]
    assert "message.channels" in settings["event_subscriptions"]["bot_events"]
    assert "message.groups" in settings["event_subscriptions"]["bot_events"]

    scopes = set(manifest["oauth_config"]["scopes"]["bot"])
    for required_scope in {
        "channels:history",
        "channels:read",
        "chat:write",
        "commands",
        "groups:history",
        "groups:read",
        "im:write",
        "users:read",
    }:
        assert required_scope in scopes
