"""Handler for /relay help (and top-level /relay subcommand routing)."""

from difflib import get_close_matches

from relay.commands.ask import handle_ask
from relay.commands.pulse import handle_pulse
from relay.commands.register import handle_register
from relay.commands.settings import handle_settings
from relay.slack.app import app

_SETUP_COMMANDS = {"settings", "setup", "sources", "connect"}
_REGISTER_COMMANDS = {"register", "add"}
_KNOWN_COMMANDS = {
    "help",
    "settings",
    "setup",
    "sources",
    "connect",
    "register",
    "add",
    "ask",
    "pulse",
    "delete-workspace-data",
}


def _help_blocks() -> list[dict]:
    rows = [
        (
            "*Set up RELAY*",
            "Connect HubSpot, GitHub, Google Drive, and Slack Search.",
            "`/relay setup`",
        ),
        (
            "*Add a customer channel*",
            "Register a Slack Connect channel so RELAY can monitor customer questions.",
            "`/relay add #channel Account Name enterprise @owner`",
        ),
        (
            "*Ask knowledge*",
            "Search connected docs, GitHub, memory, and internal Slack context.",
            "`/relay ask what is the folder structure of the RELAY repo?`",
        ),
        (
            "*Check account pulse*",
            "See open questions, SLA health, owner, ARR, and renewal context.",
            "`/relay pulse Acme Corp`",
        ),
    ]
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*RELAY command center*\n"
                    "Pick the job you want RELAY to do. Run slash commands from the main message box, not a thread reply."
                ),
            },
        },
        {"type": "divider"},
    ]
    for title, purpose, example in rows:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{title}\n{purpose}\n{example}"},
        })
    blocks.extend([
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Admin/privacy*\n"
                    "Permanently delete workspace data when an admin needs to remove RELAY.\n"
                    "`/relay delete-workspace-data`"
                ),
            },
        },
    ])
    return blocks


def _unknown_command_text(subcommand: str) -> str:
    suggestion = get_close_matches(subcommand, _KNOWN_COMMANDS, n=1, cutoff=0.55)
    if suggestion:
        return f"Unknown RELAY command `{subcommand}`. Did you mean `/relay {suggestion[0]}`? Try `/relay help` for examples."
    return f"Unknown RELAY command `{subcommand}`. Try `/relay help` for examples."


@app.command("/relay")
async def relay_help(ack, respond, command, client=None):
    await ack()
    text = (command.get("text") or "").strip()
    subcommand = text.split()[0].lower() if text else ""

    if subcommand in _REGISTER_COMMANDS:
        # Re-use ack that was already called; pass a no-op ack to handle_register
        async def _noop_ack():
            pass

        await handle_register(ack=_noop_ack, respond=respond, command=command, client=client)
        return

    if subcommand == "ask":
        async def _noop_ack():
            pass

        await handle_ask(ack=_noop_ack, respond=respond, command=command)
        return

    if subcommand == "pulse":
        async def _noop_ack():
            pass

        await handle_pulse(ack=_noop_ack, respond=respond, command=command)
        return

    if subcommand in _SETUP_COMMANDS:
        async def _noop_ack():
            pass

        await handle_settings(ack=_noop_ack, respond=respond, command=command)
        return

    if subcommand == "delete-workspace-data":
        from relay.commands.delete import handle_delete_workspace

        async def _noop_ack():
            pass

        await handle_delete_workspace(
            ack=_noop_ack,
            command=command,
            client=client,
            respond=respond,
        )
        return

    if text and subcommand != "help":
        await respond(
            response_type="ephemeral",
            text=_unknown_command_text(subcommand),
        )
        return

    await respond(
        response_type="ephemeral",
        blocks=_help_blocks(),
    )
