"""Slack Bolt app initialization."""

from slack_bolt.async_app import AsyncApp

from relay.config import get_settings

settings = get_settings()

app = AsyncApp(
    signing_secret=settings.slack_signing_secret,
    token=settings.slack_bot_token or None,
)

from relay.commands import help as _help  # noqa: E402,F401
from relay.commands import register as _register  # noqa: E402,F401
from relay.slack import home as _home  # noqa: E402,F401
from relay.slack import events as _events  # noqa: E402,F401
from relay.slack import actions as _actions  # noqa: E402,F401

