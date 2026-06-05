"""Handler logic for the /relay register subcommand."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

VALID_TIERS = {"enterprise", "pro", "starter"}

# Matches Slack channel mentions like <#C123456|channel-name>
_CHANNEL_MENTION_RE = re.compile(r"^<#([A-Z0-9]+)\|([^>]+)>$")

# Matches Slack user mentions like <@U123456> or <@U123456|display-name>
_USER_MENTION_RE = re.compile(r"^<@([A-Z0-9]+)(?:\|[^>]+)?>$")


def _parse_register_args(text: str) -> tuple[str, str, str, str | None] | None:
    """Parse the arguments after 'register'.

    Expected format:
        #channel-name account-name tier [@owner]
        <#C123456|channel-name> account-name tier [@owner]

    Returns (channel_id_or_name, channel_display_name, account_name, tier)
    or None if parsing fails.

    channel_id_or_name is the Slack channel ID (Cxxxxxxx) when a mention is
    provided, otherwise the plain name without '#'.
    """
    # Strip leading "register" if still present (defensive)
    stripped = text.strip()
    if stripped.lower().startswith("register"):
        stripped = stripped[len("register"):].strip()

    if not stripped:
        return None

    tokens = stripped.split()
    if len(tokens) < 3:
        return None

    # First token is the channel
    channel_token = tokens[0]
    mention_match = _CHANNEL_MENTION_RE.match(channel_token)
    if mention_match:
        channel_id = mention_match.group(1)
        channel_display_name = mention_match.group(2)
    elif channel_token.startswith("#"):
        channel_id = channel_token[1:]  # strip leading #
        channel_display_name = channel_id
    else:
        return None

    remaining_tokens = tokens[1:]

    # Drop optional @owner mention from the end
    if remaining_tokens and _USER_MENTION_RE.match(remaining_tokens[-1]):
        remaining_tokens = remaining_tokens[:-1]

    if len(remaining_tokens) < 2:
        return None

    # Last remaining token is the tier
    tier = remaining_tokens[-1].lower()
    if tier not in VALID_TIERS:
        return None

    # Everything between channel and tier is the account name
    account_name = " ".join(remaining_tokens[:-1])
    if not account_name:
        return None

    return channel_id, channel_display_name, account_name, tier


async def handle_register(ack, respond, command) -> None:
    """Handle the 'register' subcommand of /relay.

    Expected usage:
        /relay register #channel account-name tier [@owner]
    """
    await ack()

    raw_text = (command.get("text") or "").strip()
    # Strip the leading "register" word
    args_text = raw_text
    if args_text.lower().startswith("register"):
        args_text = args_text[len("register"):].strip()

    parsed = _parse_register_args(args_text)

    if parsed is None:
        await respond(
            response_type="ephemeral",
            text="Usage: /relay register #channel account-name tier [@owner]",
        )
        return

    channel_id, channel_display_name, account_name, tier = parsed

    # TODO(plan-2-integration): create CustomerAccount + MonitoredChannel in DB
    logger.info(
        "register_intent channel=%s account=%r tier=%s user=%s",
        channel_id,
        account_name,
        tier,
        command.get("user_id"),
    )

    await respond(
        response_type="ephemeral",
        text=(
            f"Channel #{channel_display_name} registered for account "
            f"'{account_name}' (tier: {tier})."
        ),
    )
