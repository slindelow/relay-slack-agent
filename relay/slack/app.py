"""Slack Bolt app initialization."""

from slack_bolt.async_app import AsyncApp

from relay.config import get_settings

settings = get_settings()

if settings.slack_bot_token:
    # Single-workspace mode: used in dev and tests when SLACK_BOT_TOKEN is set.
    app = AsyncApp(
        signing_secret=settings.slack_signing_secret,
        token=settings.slack_bot_token,
    )
else:
    # Multi-workspace OAuth mode: production / private beta.
    from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings
    from relay.slack.installation_store import DBInstallationStore

    app = AsyncApp(
        signing_secret=settings.slack_signing_secret,
        oauth_settings=AsyncOAuthSettings(
            client_id=settings.slack_client_id,
            client_secret=settings.slack_client_secret,
            installation_store=DBInstallationStore(),
            scopes=[
                "app_mentions:read",
                "channels:read",
                "chat:write",
                "commands",
                "groups:history",
                "groups:read",
                "im:write",
                "users:read",
            ],
            user_scopes=[
                "search:read.public",
                "search:read.files",
                "search:read.users",
            ],
        ),
    )

from relay.commands import help as _help  # noqa: E402,F401
from relay.commands import ask as _ask  # noqa: E402,F401
from relay.commands import delete as _delete  # noqa: E402,F401
from relay.commands import pulse as _pulse  # noqa: E402,F401
from relay.commands import register as _register  # noqa: E402,F401
from relay.commands import settings as _settings  # noqa: E402,F401
from relay.slack import home as _home  # noqa: E402,F401
from relay.slack import settings_actions as _settings_actions  # noqa: E402,F401
from relay.slack import events as _events  # noqa: E402,F401
from relay.slack import actions as _actions  # noqa: E402,F401
from relay.slack import draft_actions as _draft_actions  # noqa: E402,F401
