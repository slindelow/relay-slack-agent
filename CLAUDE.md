# Memory

## Me
Sofia is building RELAY in `/Users/sofialindelow/All agents/slackathon` with a two-agent workflow using Codex and Claude.

## Projects
| Name | What |
|------|------|
| RELAY | Slack-native customer-success agent for Slack Connect customer channels. Detects unanswered customer questions, tracks SLA risk, retrieves CRM/docs/GitHub/Slack context, drafts cited replies, and requires human approval before posting. |

## Current State
| Area | Status |
|------|--------|
| Branch | `main` is the stable/live branch. |
| Deployment | Railway live at `https://web-production-acd3.up.railway.app`; web and worker auto-deploy from `main`. |
| Beta | Core loop validated end-to-end; remaining checklist items are SLA timer, workspace deletion, and uninstall. |
| Tests | As of 2026-06-30 audit: `327 passed, 34 skipped`. |

## Important Terms
| Term | Meaning |
|------|---------|
| RELAY | Product/repo name. |
| MCP | RELAY context server mounted at `/mcp-api/mcp`; currently a security review hotspot. |
| RTS | Slack Real-Time Search / `assistant.search.context` user-token context path. |
| RLS | PostgreSQL row-level security using `app.current_workspace_id`. |
| KMS | Optional AWS KMS envelope encryption path; Railway beta currently uses global token key fallback. |

## Known Review Items
| Priority | Item |
|----------|------|
| P0 | Public MCP HTTP route needs caller authentication/authorization before broad exposure. |
| P1 | HubSpot browser install path trusts forgeable `team_id`/`user_id` query params. |
| P1 | GitHub/Drive resync leaves stale knowledge chunks on changed documents. |
| P2 | Slack event dedup is logged but not enforced before classification. |
| P2 | GitHub connector materializes full paginated issue/PR/release lists before slicing. |

Full review log: `docs/CODEBASE_REVIEW_2026-06-30.md`.

## Preferences
- Keep branch discipline: Codex branches use `codex/...`, Claude branches use `claude/...`, and avoid direct main commits unless the user explicitly asks or the repo's current operational pattern requires it.
- Update `docs/HANDOFF.md` after substantive implementation sessions.
- Use `uv run ...` for Python commands in this repo; bare `python` may not be on PATH.
