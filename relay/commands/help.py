"""Handler for /relay help (and top-level /relay subcommand routing)."""

from relay.commands.ask import handle_ask
from relay.commands.pulse import handle_pulse
from relay.commands.register import handle_register
from relay.slack.app import app


@app.command("/relay")
async def relay_help(ack, respond, command):
    await ack()
    text = (command.get("text") or "").strip()
    subcommand = text.split()[0].lower() if text else ""

    if subcommand == "register":
        # Re-use ack that was already called; pass a no-op ack to handle_register
        async def _noop_ack():
            pass

        await handle_register(ack=_noop_ack, respond=respond, command=command)
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

    if text and subcommand != "help":
        await respond(
            response_type="ephemeral",
            text=f"Unknown subcommand: `{subcommand}`. Try `/relay help`.",
        )
        return

    await respond(
        response_type="ephemeral",
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": "*RELAY commands*"}},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "• `/relay help` - Show this message\n"
                        "• `/relay register #channel account tier @owner` - Register a customer channel\n"
                        "• `/relay open` - Planned in Plan 3\n"
                        "• `/relay ask [question]` - Search connected knowledge sources\n"
                        "• `/relay pulse [account]` - Show account health digest"
                    ),
                },
            },
        ],
    )
