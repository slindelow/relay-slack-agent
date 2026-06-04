# RELAY — Product Requirements & Architecture Document

**Tagline:** Never lose a customer in a Slack channel again.  
**Hackathon Track:** New Slack Agent  
**Target User:** Customer Success Managers and Support Leads at B2B SaaS companies  
**Submission Deadline:** July 13, 2026

---

## 1. Problem Definition

### The Shift Nobody Planned For

Enterprise B2B support has quietly migrated off ticketing systems and into Slack. When a hospital system goes live on your platform, they don't open a Zendesk ticket — they ping the shared Slack Connect channel. When an API breaks at 2pm on a Tuesday, the enterprise customer messages the channel. Slack Connect has become the default support surface for B2B SaaS, and almost no tooling has caught up with this reality.

A mid-size B2B SaaS company with 50–200 enterprise accounts is now managing 50–200 active Slack Connect channels simultaneously. Each channel is a live relationship. Each unanswered message in one of those channels is a risk event.

### The Three Failure Modes

**1. Messages fall through the cracks**

There is no SLA tracking inside Slack. A question posted to the Acme Health channel at 11am on Friday sits unanswered until Monday morning because the CSM who owns that account was in back-to-back calls. By the time anyone notices, the customer has escalated to their account executive. This happens constantly and is structurally invisible — nobody sees the messages that didn't get answered until a customer complains.

**2. Knowledge is siloed per channel, not shared across them**

When the API rate limit error first appeared in the Stripe Health channel six months ago, the lead engineer wrote a detailed, accurate explanation that took 45 minutes to research. That explanation is now buried in a channel that nobody searches. The next time the same error appears — in the Cedars-Sinai channel, in the Mayo Clinic channel, in the Kaiser channel — each CSM researches it from scratch. The institutional knowledge of 200 customer channels is completely invisible to the team managing those channels.

**3. Churn signals are hidden in silence**

A customer who is disengaging doesn't always say so. They stop asking questions. A channel that averaged 25 messages per week six months ago now averages 3. The CSM doesn't notice because they're monitoring 60 channels and there's nothing to alert on — silence generates no notifications. The churn signal that would have triggered a proactive save conversation goes unread until the renewal call, when it's too late.

### Who Feels This Pain (and How Acutely)

- **B2B SaaS with enterprise accounts:** Any company using Slack Connect for customer communication. Estimated 40,000+ companies using Slack Connect for B2B support as of 2026.
- **Health-tech specifically:** Healthcare enterprise accounts have higher stakes per channel. A missed message from a CMO during a go-live week can cost the entire contract. Heidi's customer base (hospital systems, large practices) fits this profile exactly.
- **CSM-to-account ratios:** The pain scales with account load. A CSM managing 30+ accounts simply cannot maintain active awareness of 30 channels simultaneously without tooling.

---

## 2. Solution: RELAY

RELAY is a Slack-native agent that monitors all customer-facing Slack Connect channels on behalf of a B2B support or customer success team. It surfaces unanswered questions before they become incidents, retrieves relevant answers from across the organization's institutional knowledge, and drafts grounded responses that CSMs can review and send. It runs entirely inside Slack — no new surface to adopt, no tab to switch to.

### Core Principle

RELAY does not replace the CSM. It gives them awareness they cannot have manually at scale, and drafts responses they can choose to send. The human approves every outbound message. RELAY handles detection, retrieval, and drafting.

---

## 3. Feature Specification

### Feature A: Unanswered Question Detection (The SLA Layer)

**How it works:**

RELAY subscribes to message events across all registered customer Slack Connect channels via the Events API. When a message arrives, it is classified by the LLM as one of three types:
- `QUESTION` — requires a response from the B2B team
- `ACKNOWLEDGMENT` — customer confirming something, no response needed
- `FYI` — informational, no response needed

When a `QUESTION` is classified, RELAY starts a countdown based on the account's SLA tier:
- Enterprise tier: 30-minute response SLA
- Pro tier: 2-hour response SLA  
- Starter tier: 8-hour response SLA

If no response is detected within the SLA window, RELAY fires an alert to the CSM's internal Slack DM:

```
🔴 Unanswered question — Acme Health (Enterprise)
Waiting: 34 minutes  |  SLA: 30 min  |  Owner: @sofia

"We're seeing a 401 error on the FHIR endpoint after the 
migration last night. Can you help us debug this?"

[View in channel]  [Draft response]  [Snooze 30 min]
```

Clicking **Draft response** opens a threaded reply with a pre-drafted answer (see Feature B). Clicking **View in channel** jumps directly to the message. **Snooze** dismisses the alert and re-fires after the selected interval.

**Duplicate suppression:** If a teammate has already responded inside the SLA window, RELAY detects the response, cancels the alert, and logs the resolution time.

**Multi-CSM awareness:** If two CSMs share a channel, RELAY fires the alert to both and marks it as "claimed" once one clicks into it, preventing duplicate responses.

---

### Feature B: Cross-Channel Knowledge Retrieval (The Memory Layer)

**How it works:**

RELAY maintains a knowledge index built from two sources:
1. **Past channel resolutions** — when a `QUESTION` is marked resolved, the question + answer pair is indexed via embedding into the knowledge store
2. **Internal documentation** — connected via MCP to the company's knowledge base (Notion, Confluence, or a docs site), indexed on first connection and re-synced weekly

When a new question arrives, RELAY runs a semantic similarity search against this index to find the top 3 matching prior answers. These are passed as context to the LLM alongside the new question to generate a grounded, specific draft response.

**Slash command interface:**

CSMs can also query directly: `/relay has anyone seen Epic EHR integration timeouts before?`

RELAY responds in a private thread:

```
Found 3 relevant past answers:

1. Mayo Clinic channel (March 2026) — 94% match
   "Epic's Interconnect API has a 30s timeout on bulk FHIR 
   queries. The fix is to batch requests under 50 records..."
   
2. Kaiser channel (January 2026) — 87% match
   "We've seen this with Epic's sandbox environment specifically..."

3. Internal docs — 81% match
   Epic Integration Guide > Known Limitations > Timeout Handling

[Use answer 1 as draft]  [Combine answers]  [Search more]
```

The CSM selects which answer to use as the basis for their response draft.

---

### Feature C: Account Pulse & Silence Detection (The Churn Signal Layer)

**How it works:**

Every Sunday at 6pm, RELAY runs a pulse calculation for each registered customer channel:

- **Message volume:** Messages per week, 4-week rolling average, trend direction
- **Question resolution rate:** % of questions answered within SLA
- **Sentiment shift:** LLM classification of message tone over the past 30 days vs. the prior 30 days
- **Last customer message:** Days since the customer (not the CSM) last posted

Accounts are scored against a simple health model:

| Signal | Weight |
|---|---|
| Volume decline >40% week-over-week | High risk |
| No customer message in 14+ days | High risk |
| Sentiment shift negative | Medium risk |
| Multiple unanswered questions in past 7 days | Medium risk |
| Volume stable or growing | Healthy |

**Weekly digest to `#customer-pulse`:**

RELAY posts a Canvas to the team's internal `#customer-pulse` channel every Monday morning with a ranked account health list. Accounts flagged as at-risk are surfaced first with the specific signal that triggered the flag.

```
📊 Weekly Customer Pulse — Week of June 2, 2026

🔴 AT RISK (2 accounts)
├── Acme Health — Silent 18 days, volume down 60%
└── Riverside Medical — 3 unanswered questions last week

🟡 WATCH (4 accounts)
├── Cedars-Sinai — Sentiment shifted negative (billing questions)
└── ...

🟢 HEALTHY (44 accounts)
```

Clicking an account name expands to a full account summary Canvas showing the message history trend, open questions, and a suggested action (schedule a check-in call, send a proactive update, etc.).

---

### Feature D: Response Drafting with HITL Approval

Every response RELAY drafts is ephemeral — visible only to the CSM, not sent to the customer. The CSM reviews, edits if needed, and clicks **Send** to post to the customer channel. RELAY never posts directly to a customer-facing channel without explicit human approval.

The draft UI inside the CSM's internal channel:

```
Draft response for Acme Health — ready to review

---
Hi [name], thanks for flagging this. The 401 error after migration 
is typically caused by the OAuth token scope not being updated to 
include the FHIR R4 endpoint. Here's what to check:

1. Navigate to Settings > API > Token Management
2. Re-authorize with the fhir.read scope
3. If the error persists, share the full request header...
---

Sources: Mayo Clinic channel (March 2026), Epic Integration Guide

[Send to channel]  [Edit draft]  [Regenerate]  [Discard]
```

Clicking **Send to channel** posts the message directly to the customer Slack Connect channel under the CSM's name. RELAY logs the action with a timestamp, the source documents used, and the CSM who approved it.

---

## 4. Technical Architecture

```
+-------------------------------------------------------------------------+
|                         SLACK WORKSPACE (Internal)                      |
|                                                                         |
|  CSM Dashboard          #customer-pulse       DM Alerts    /relay cmd   |
|  [Canvas Pulse View]    [Weekly Digest]       [SLA Alerts] [Knowledge]  |
+-------+---------------------+----------------------------+--------------+
        |                     |                            |
        | Block Kit Events    | Canvas Write               | Slash Command
        v                     v                            v
+-------+---------------------+----------------------------+--------------+
|                     RELAY APPLICATION (Slack Bolt / Python)             |
|                                                                         |
|  - Events API Listener      - SLA Timer Engine    - RTS Query Router    |
|  - Message Classifier       - Alert Dispatcher    - Response Composer   |
+-------+---------------------+----------------------------+--------------+
        |                     |                            |
        | Store/Query         | Embed + Search             | Tool Calls
        v                     v                            v
+-------+---------------------+-------+   +---------------+--------------+
|     POSTGRESQL + PGVECTOR           |   |        MCP SERVER            |
|                                     |   |                              |
|  - customer_accounts                |   |  - search_knowledge_base()   |
|  - monitored_channels               |   |  - get_account_history()     |
|  - message_log                      |   |  - get_open_questions()      |
|  - knowledge_entries                |   |  - draft_response()          |
|  - account_pulse_snapshots          |   |  - sync_documentation()      |
+-------------------------------------+   +------------------------------+
                                                        |
                                          Connected via MCP protocol to:
                                          - Internal docs (Notion/Confluence)
                                          - Past resolution knowledge base
```

### Slack Connect Channel Monitoring

RELAY monitors customer-facing Slack Connect channels by subscribing to `message` events via the Events API. All registered channels are stored in the `monitored_channels` table. When a message event fires, the payload includes the channel ID, which is matched against this registry to determine account context (tier, CSM owner, SLA threshold).

**Important:** RELAY only monitors channels where it has been explicitly added as a bot member by an admin. It never accesses channels it hasn't been invited to. This is enforced at the database level — only channels in `monitored_channels` are processed; all others are discarded immediately.

### RTS API Usage

The Real-Time Search API (`assistant.search.context`) is used for two specific purposes:

1. **Cross-channel knowledge retrieval** — when a CSM runs `/relay [question]`, RELAY uses RTS to perform a permission-aware semantic search across all Slack channel history the bot has access to, surfacing relevant prior answers from other customer channels
2. **Context assembly on alert** — when RELAY fires an SLA alert, it pulls the last 10 messages of conversation context from the channel using RTS to give the CSM full situational awareness without leaving their DM

### LLM Classification Pipeline

Every incoming message is passed through a two-step classification before entering the SLA timer:

**Step 1 — Intent classification (Claude Haiku, fast + cheap):**
```python
classify_message(
    content: str,
    channel_context: str  # last 5 messages for context
) -> Literal["QUESTION", "ACKNOWLEDGMENT", "FYI", "INTERNAL"]
```

**Step 2 — If QUESTION — urgency classification:**
```python
classify_urgency(
    content: str,
    account_tier: str
) -> Literal["P0", "P1", "P2"]
```

P0 questions (system down, data loss, security) immediately fire an alert regardless of SLA timer. P1 and P2 follow the tier-based SLA schedule.

**Response drafting (Claude Sonnet 4.6):**
```python
draft_response(
    question: str,
    retrieved_context: list[KnowledgeEntry],
    account_context: AccountProfile,
    tone: str  # from account profile: "formal" | "conversational"
) -> DraftResponse
```

---

## 5. Database Schema

```sql
CREATE EXTENSION IF NOT EXISTS pgvector;

-- Registered customer accounts
CREATE TABLE customer_accounts (
    id SERIAL PRIMARY KEY,
    workspace_id VARCHAR(255) NOT NULL,         -- Internal Slack workspace ID
    company_name VARCHAR(255) NOT NULL,
    account_tier VARCHAR(20) NOT NULL,          -- 'Enterprise', 'Pro', 'Starter'
    csm_slack_user_id VARCHAR(255) NOT NULL,    -- Primary owner
    backup_csm_slack_user_id VARCHAR(255),
    sla_minutes INT NOT NULL,                   -- Derived from tier, overridable
    tone_preference VARCHAR(20) DEFAULT 'conversational',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Slack Connect channels being monitored
CREATE TABLE monitored_channels (
    id SERIAL PRIMARY KEY,
    account_id INT REFERENCES customer_accounts(id) ON DELETE CASCADE,
    slack_channel_id VARCHAR(255) UNIQUE NOT NULL,
    channel_name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    added_by_slack_user_id VARCHAR(255) NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Every inbound customer message
CREATE TABLE message_log (
    id SERIAL PRIMARY KEY,
    channel_id INT REFERENCES monitored_channels(id),
    slack_message_ts VARCHAR(255) NOT NULL,     -- Slack timestamp, used as message ID
    sender_slack_user_id VARCHAR(255) NOT NULL,
    sender_is_customer BOOLEAN NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(20),                          -- 'QUESTION', 'ACKNOWLEDGMENT', 'FYI'
    urgency VARCHAR(5),                          -- 'P0', 'P1', 'P2', NULL
    sla_deadline TIMESTAMP,
    response_received_at TIMESTAMP,
    response_within_sla BOOLEAN,
    alert_fired_at TIMESTAMP,
    alert_snoozed_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Knowledge base: indexed Q&A pairs and documentation chunks
CREATE TABLE knowledge_entries (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(20) NOT NULL,           -- 'channel_resolution', 'documentation'
    source_reference TEXT,                       -- Channel name + date, or doc URL
    question TEXT,
    answer TEXT NOT NULL,
    embedding VECTOR(1024),                      -- Voyage AI voyage-3 dimensions
    use_count INT DEFAULT 0,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weekly account health snapshots
CREATE TABLE account_pulse_snapshots (
    id SERIAL PRIMARY KEY,
    account_id INT REFERENCES customer_accounts(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    messages_this_week INT DEFAULT 0,
    messages_prev_week INT DEFAULT 0,
    customer_messages_this_week INT DEFAULT 0,
    questions_asked INT DEFAULT 0,
    questions_answered_within_sla INT DEFAULT 0,
    days_since_last_customer_message INT,
    sentiment_score FLOAT,                       -- -1.0 (negative) to 1.0 (positive)
    health_status VARCHAR(20),                   -- 'Healthy', 'Watch', 'At Risk'
    health_flags TEXT[],                         -- e.g. ['SILENT_14_DAYS', 'VOLUME_DROP']
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit log of all RELAY actions
CREATE TABLE action_log (
    id SERIAL PRIMARY KEY,
    account_id INT REFERENCES customer_accounts(id),
    action_type VARCHAR(50) NOT NULL,            -- 'ALERT_FIRED', 'DRAFT_SENT', 'SNOOZED'
    triggered_by_slack_user_id VARCHAR(255),
    message_log_id INT REFERENCES message_log(id),
    knowledge_entry_ids INT[],                   -- Which sources informed the draft
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. MCP Server Specification

The MCP server runs as a lightweight Python service that exposes the knowledge base and account data to the LLM layer. It is the only component that directly queries the database — the Slack Bolt app communicates with it via the MCP protocol over a local SSE connection.

### Exposed Tools

**`search_knowledge_base(query: str, top_k: int = 5) -> list[KnowledgeEntry]`**

Embeds the query using Voyage AI (`voyage-3`), runs a cosine similarity search against `knowledge_entries.embedding`, and returns the top-k results with source references and similarity scores.

```python
# Returns
[{
    "id": 142,
    "source_type": "channel_resolution",
    "source_reference": "Mayo Clinic channel — March 14, 2026",
    "question": "401 error on FHIR endpoint after token refresh",
    "answer": "Re-authorize OAuth with fhir.read scope...",
    "similarity_score": 0.94
}]
```

**`get_account_context(account_id: int, days: int = 30) -> AccountContext`**

Returns a structured summary of an account's recent activity: open questions, SLA performance, CSM owner, tier, tone preference, and the last N message summaries.

**`get_open_questions(channel_id: str) -> list[OpenQuestion]`**

Returns all questions in a channel that are past their SLA deadline and have not been resolved. Used to populate the weekly digest and the CSM dashboard.

**`index_resolution(question: str, answer: str, source_reference: str) -> bool`**

Called when a CSM marks a response as sent. Embeds the Q&A pair and stores it in `knowledge_entries` for future retrieval. This is how the knowledge base grows over time.

**`sync_documentation(source_url: str, source_type: str) -> SyncResult`**

Fetches and re-indexes documentation from a connected source (Notion page, Confluence space, or docs URL). Chunks using a 400-token window with 80-token overlap. Stores chunks as individual `knowledge_entries` with `source_type = 'documentation'`.

---

## 7. Slack Primitives Used

| Primitive | Purpose |
|---|---|
| **Events API** | Subscribe to `message` events in monitored Slack Connect channels |
| **Slack Connect** | The customer-facing channels RELAY monitors |
| **RTS API (`assistant.search.context`)** | Cross-channel semantic search for knowledge retrieval and context assembly |
| **Block Kit (interactive messages)** | SLA alert cards with action buttons (Draft, Snooze, View) |
| **Block Kit (modals)** | Draft review interface before sending |
| **Canvas** | Weekly account pulse digest, per-account health summaries |
| **Slash commands (`/relay`)** | Ad-hoc knowledge queries from CSMs |
| **Ephemeral messages** | Draft responses visible only to the CSM before approval |
| **DM to bot** | Alert delivery to individual CSM without channel noise |

---

## 8. Security & Privacy

**Channel access is explicit and logged.** RELAY only processes messages in channels where it has been explicitly added by an admin. Every channel addition is recorded in `action_log`. RELAY cannot self-invite to channels.

**Customer data never leaves the knowledge base context.** Customer message content is stored in the local PostgreSQL instance only. It is passed to the LLM (Claude API via Anthropic enterprise endpoints with zero data retention) for classification and drafting, then discarded from memory. No customer message content is cached externally.

**CSM identity is preserved on send.** When RELAY sends a draft, it posts under the CSM's Slack identity via the `chat.postMessage` API using the CSM's authorized token. Messages never appear to come from a bot in customer-facing channels.

**Audit trail is complete.** Every alert, draft, send, and snooze action is logged in `action_log` with the triggering user, timestamp, and source documents used. This provides a full audit trail for any escalation review.

---

## 9. Hackathon Delivery Scope

### What to Build (6 weeks, demo-ready)

**Week 1–2: Core infrastructure**
- Slack Bolt app with Events API listener
- Channel registration admin flow (`/relay register #channel-name acme-health enterprise`)
- Message classification pipeline (Haiku for intent, Sonnet for drafting)
- PostgreSQL schema + pgvector setup
- Basic SLA timer with DM alert

**Week 3–4: Knowledge layer**
- MCP server with `search_knowledge_base` and `index_resolution` tools
- Voyage AI embedding pipeline
- `/relay [question]` slash command with knowledge retrieval response
- Resolution indexing when CSM clicks Send

**Week 5: Account pulse**
- Weekly pulse calculation job (APScheduler or cron)
- Canvas generation for `#customer-pulse` digest
- Per-account health scoring

**Week 6: Polish + demo**
- Block Kit UI refinement
- Demo environment setup with synthetic customer channels
- 3-minute demo video script and recording

### What to Leave Out (Post-Hackathon)
- Multi-tenant workspace support (build for single workspace demo)
- Notion/Confluence sync (demo with seeded knowledge base)
- Native CRM integration (HubSpot/Salesforce) — out of scope
- Mobile push notifications

### Demo Script (3 minutes)

1. **(0:00–0:30)** Show the problem: a CSM's screen with 40 Slack Connect channels, a message from Acme Health that's been sitting unanswered for 2 hours
2. **(0:30–1:00)** RELAY fires the SLA alert DM — show the Block Kit card with the unanswered question, account tier, and wait time. CSM clicks "Draft response"
3. **(1:00–1:45)** Draft appears — show the retrieved source (similar question answered in a different customer channel 3 months ago), the grounded response, and the source citation. CSM clicks Send.
4. **(1:45–2:15)** Cut to `/relay has anyone seen Epic FHIR timeout errors before?` — show cross-channel knowledge retrieval returning 3 matching prior resolutions
5. **(2:15–3:00)** Show Monday morning `#customer-pulse` Canvas — highlight the "At Risk" account flagged for 18 days of silence, and the suggested action. Close on the health dashboard.

---

## 10. Why RELAY Wins the Hackathon

**It's only possible in Slack.** Monitoring Slack Connect channels with the RTS API for semantic question detection is a capability that cannot exist in Zendesk, Intercom, or any external tool. RELAY is not a Slack integration — it's a Slack-native product.

**MCP has a genuine architectural role.** The MCP server is not a folder bridge. It is the access layer between the LLM and a proprietary knowledge base that grows with every resolution. Judges evaluating technological implementation will see a legitimate reason for the protocol.

**The demo is emotionally clear.** A CSM missing a customer message is a specific, embarrassing, high-stakes failure mode every judge at a B2B software company has experienced personally. The problem is felt in the first 30 seconds. The solution is obvious by minute 2.

**It's built on existing work.** The classification pipelines, Slack webhook patterns, and knowledge indexing logic parallel what's already built in the SDR Leads Agent and Competitive Analysis Agent in this codebase. RELAY is a new surface on proven patterns, not a greenfield build.
