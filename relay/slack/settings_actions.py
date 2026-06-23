"""Slack action registrations for /relay settings connector setup."""

from relay.commands.settings import (
    handle_disconnect_slack_search,
    handle_save_github_connector,
    handle_save_google_drive_connector,
    handle_setup_github_connector,
    handle_setup_google_drive_connector,
    handle_sync_connector,
)
from relay.slack.app import app


app.action("relay_disconnect_slack_search")(handle_disconnect_slack_search)
app.action("relay_setup_github_connector")(handle_setup_github_connector)
app.action("relay_setup_google_drive_connector")(handle_setup_google_drive_connector)
app.action("relay_sync_connector")(handle_sync_connector)
app.view("relay_save_github_connector")(handle_save_github_connector)
app.view("relay_save_google_drive_connector")(handle_save_google_drive_connector)
