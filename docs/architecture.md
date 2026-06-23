# RELAY Architecture

## Full Data Flow

```mermaid
flowchart TD
    A["Slack Connect Channel\n(customer workspace)"]
    B["Slack Events API\n/slack/events"]
    C["FastAPI + Slack Bolt\nrelay/api/main.py"]
    D["Celery Worker\nrelay/worker/tasks.py"]
    E["Message Classifier\nrelay/classifier/"]
    F["Question State Machine\nrelay/db/models.py — Question"]
    G["SLA Poller\nCelery beat — sla_poll_task"]
    H["CSM DM Alert\nSlack bot message"]
    I["Claim Action\nSlack interactivity"]
    J["MCP Server\nrelay/context/mcp_server.py"]
    K["question_lookup tool"]
    L["evidence_assembly tool"]
    M["draft_generation tool"]
    N["pgvector Semantic Search\nrelay/connectors/retrieval.py"]
    O["CRM Context\nHubSpot / customer_accounts"]
    P["GitHub / Google Drive\nrelay/connectors/"]
    Q["Slack Real-Time Search\nrelay/context/slack_rts.py"]
    R["Anthropic API\nclaude-sonnet-4-6"]
    S["Human Approval Modal\nrelay/slack/draft_modal.py"]
    T["Bot Posts Response\nSlack Connect channel"]
    U["Resolution Memory\nrelay/drafting/memory.py"]

    A -->|"customer posts message"| B
    B --> C
    C -->|"enqueue"| D
    D --> E
    E -->|"classified as question"| F
    F --> G
    G -->|"SLA at risk"| H
    H -->|"CSM clicks Claim"| I
    I -->|"triggers draft generation"| J

    subgraph MCP["MCP Server — relay/context/mcp_server.py"]
        J --> K
        J --> L
        J --> M
    end

    K -->|"question excerpt + urgency"| F
    L --> N
    L --> O
    L --> P
    L --> Q
    M -->|"evidence bundle"| R
    R -->|"structured draft (tool_use)"| S

    S -->|"CSM edits + approves"| T
    T --> U
    U -->|"feedback loop"| N

    style MCP fill:#e8f4f8,stroke:#2980b9,stroke-width:2px
    style J fill:#2980b9,color:#fff
    style M fill:#2980b9,color:#fff
    style R fill:#8e44ad,color:#fff
```

## Layer Summary

| Layer | What it does | Key files |
|-------|-------------|-----------|
| **Slack surface** | Receives Events API webhooks, slash commands, interactivity, OAuth | `relay/api/main.py`, `relay/slack/` |
| **Ingestion worker** | Classifies messages, creates Question rows, drives state machine | `relay/worker/tasks.py`, `relay/classifier/` |
| **SLA poller** | Celery beat job — fires alerts before response deadlines | `relay/worker/tasks.py` |
| **MCP Server** | Governed interface between Claude and RELAY's data tools | `relay/context/mcp_server.py` |
| **Context service** | Fetches question/account context, assembles evidence bundles | `relay/context/service.py`, `relay/context/contracts.py` |
| **Retrieval** | pgvector ANN search over indexed knowledge entries | `relay/connectors/retrieval.py` |
| **Connectors** | Sync GitHub/Google Drive docs; HubSpot CRM; Slack RTS | `relay/connectors/`, `relay/context/slack_rts.py` |
| **Draft generator** | Calls Anthropic API with evidence bundle via `draft_generation` MCP tool | `relay/drafting/generator.py` |
| **Approval modal** | Block Kit modal for CSM review, edit, and one-click send | `relay/slack/draft_modal.py` |
| **Resolution memory** | Stores approved Q+A pairs; feeds back into retrieval | `relay/drafting/memory.py` |

## MCP as the Integration Layer

```
Celery task (drafting_tasks.py)
  └─▶ draft_generation_tool()       ← MCP tool function
        ├─▶ evidence_assembly_tool() ← assembles pgvector + CRM + Slack RTS sources
        │     ├─▶ question_lookup_tool()
        │     ├─▶ pgvector retrieve()
        │     ├─▶ HubSpot account context
        │     └─▶ Slack Real-Time Search
        └─▶ generate_draft()         ← calls Anthropic API, saves Draft row
```

All draft generation routes through the MCP tool boundary. External clients (Claude Code, MCP inspector) can invoke the same `draft_generation` tool directly.

## Tenant Isolation

- PostgreSQL RLS (`SET LOCAL app.current_workspace_id`) on every session
- All `workspace_id` columns are UUIDs, never cross-joined
- Bot tokens, CRM tokens, and Slack search tokens encrypted with AES-256-GCM workspace DEKs
- Workspace data purge via `/relay delete-workspace-data` cascades through all tenant tables
