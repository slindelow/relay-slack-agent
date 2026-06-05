"""FastAPI app mounting Slack Bolt."""

from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from relay.slack.app import app as bolt_app

api = FastAPI(title="RELAY", version="0.1.0")
handler = AsyncSlackRequestHandler(bolt_app)


@api.get("/health")
async def health():
    return {"status": "ok", "service": "relay"}


@api.post("/slack/events")
async def slack_events(req: Request):
    return await handler.handle(req)


@api.get("/slack/install")
async def slack_install(req: Request):
    return await handler.handle(req)


@api.get("/slack/oauth_redirect")
async def slack_oauth_redirect(req: Request):
    return await handler.handle(req)

