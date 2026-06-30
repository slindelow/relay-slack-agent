# Glossary

## Acronyms and Internal Terms
| Term | Meaning | Context |
|------|---------|---------|
| RELAY | Slack-native customer-success agent | Product and Python package name. |
| Slack Connect | Cross-company Slack channels | RELAY monitors only registered customer channels. |
| MCP | Model Context Protocol | RELAY exposes governed context tools; HTTP auth is a current review item. |
| RTS | Slack Real-Time Search | Permission-aware internal Slack search via user tokens. |
| RLS | Row-level security | PostgreSQL tenant isolation with `app.current_workspace_id`. |
| KMS | Key Management Service | AWS KMS envelope encryption target for production secrets. |
| ARR | Annual recurring revenue | Synced from HubSpot into account pulse. |
| CSM | Customer success manager | Human reviewer/approver of RELAY drafts. |

## Commands
| Command | Meaning |
|---------|---------|
| `/relay settings` | Setup status, connector buttons, Slack Search, HubSpot sync. |
| `/relay register` | Register a Slack Connect customer channel to monitor. |
| `/relay ask` | Query indexed knowledge/context. |
| `/relay pulse` | Account/customer channel pulse with CRM and open question status. |
| `/relay delete-workspace-data` | Workspace deletion flow. |
