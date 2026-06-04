"""App Home view skeleton."""

from relay.slack.app import app


@app.event("app_home_opened")
async def publish_app_home(event, client):
    await client.views_publish(
        user_id=event["user"],
        view={
            "type": "home",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "RELAY"}},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Welcome to RELAY.*\nMonitor customer Slack Connect channels, detect unanswered questions, and get cited response drafts.",
                    },
                },
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "*Setup checklist*\n"
                            ":white_circle: Register a customer channel\n"
                            ":white_circle: Connect CRM and knowledge sources\n"
                            ":white_circle: Assign account owners"
                        ),
                    },
                },
            ],
        },
    )

