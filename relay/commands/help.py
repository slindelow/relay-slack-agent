"""Handler for /relay help."""

from relay.slack.app import app


@app.command("/relay")
async def relay_help(ack, respond, command):
    await ack()
    text = (command.get("text") or "").strip().lower()

    if text and text != "help":
        await respond(
            response_type="ephemeral",
            text=f"Unknown subcommand: `{text}`. Try `/relay help`.",
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
                        "• `/relay register #channel account tier @owner` - Planned in Plan 2\n"
                        "• `/relay open` - Planned in Plan 3\n"
                        "• `/relay ask [question]` - Planned in Plan 5\n"
                        "• `/relay pulse` - Planned in Plan 6"
                    ),
                },
            },
        ],
    )

