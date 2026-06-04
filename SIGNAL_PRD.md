# SIGNAL — Product Requirements & Architecture Document

**Tagline:** Competitive intelligence that finds you, not the other way around.
**Hackathon Track:** New Slack Agent
**Target User:** Growth, Sales, and GTM teams at health-tech SaaS companies
**Reference Company:** Heidi Health (AI medical scribe, $65M Series B)
**Submission Deadline:** July 13, 2026

---

## 1. Problem Definition

### Intelligence That Dies in a Spreadsheet

Heidi's Competitive Analysis agent already does the hard work. Every week it scrapes pricing pages, G2 reviews, job postings, funding announcements, and changelog entries across 13 competitors — Freed, Suki, DeepScribe, Abridge, Epic Ambient AI, athenaAmbient, and eight others. It synthesizes the data into a structured threat matrix, a feature gap analysis, and an HTML report with charts.

Nobody reads it.

The report lives in a Google Sheet tab and an HTML file in an output directory. The growth team knows it exists. They intend to review it on Mondays. But Monday has standup, then a pipeline call, then a customer escalation, and by the time anyone remembers the competitive report it's Wednesday and already stale. The intelligence is good. The delivery is broken.

### The Three Failure Modes

**1. Intelligence is pulled, not pushed**

Every competitive insight the team needs requires someone to remember to go look for it. There is no mechanism that brings a competitive signal to the person who needs it at the moment they need it. A sales rep walking into a renewal call with a customer who named Freed as an alternative has no way to know that Freed dropped their Pro pricing by 20% last Tuesday. They find out when the customer tells them.

**2. Deal context is invisible to the intelligence layer**

The competitive data has no awareness of live sales activity. When a rep opens a deal channel for the Cedars-Sinai renewal and the conversation turns to pricing, the system has no way to know that this is a moment when Freed's latest pricing move is directly relevant. The intelligence and the deal live in completely separate systems with no connection between them.

**3. Weekly cadence is too slow for a fast-moving market**

The AI medical scribe market moves in days, not weeks. athenaAmbient announced free ambient AI for all 160,000 athenahealth users in early 2026 — a move that directly undercuts Heidi's US small practice segment. Abridge raised $550M in a single year. Epic launched its native scribe in August 2025. These are not weekly events; they are signals that require immediate awareness and response. A Monday report delivered Thursday is a missed opportunity.

### The Market Context

Heidi competes in one of the fastest-moving verticals in enterprise software. The competitive landscape includes:

- **Tier 1 direct competitors** (Freed, Suki, Nabla, Twofold, DeepScribe, Mentalyc, Chartnote) competing head-to-head for the same clinician audience via PLG models
- **Tier 2 existential threats** (Epic, athenahealth, Oracle Health, Nuance/Microsoft, Abridge) who are bundling AI scribes into EHR contracts at zero marginal cost to the customer

A GTM team navigating this landscape needs competitive intelligence that is fast, contextual, and actionable — not a weekly HTML file.

---

## 2. Solution: SIGNAL

SIGNAL is the Slack-native surface layer for Heidi's existing competitive intelligence engine. It does not replace the underlying data collection and synthesis logic — it replaces the broken delivery mechanism. Intelligence moves from a spreadsheet nobody reads to the channel where the conversation is already happening, at the moment it's relevant.

SIGNAL has three modes:

1. **On-demand lookup** — any team member gets an instant competitive snapshot via slash command
2. **Proactive deal-time alerts** — when a tracked competitor makes a move, the relevant deal channels are notified automatically
3. **Weekly battlecard Canvas** — the Monday digest delivered directly to `#competitive-intel` as a navigable Slack Canvas

### Core Principle

SIGNAL does not generate new competitive intelligence. It surfaces existing intelligence — from the Comp Analysis agent's database, from the scraping pipeline, from the structured competitor registry — at the right time, in the right place, to the right person. The hard work is already done. SIGNAL is the last mile.

---

## 3. Feature Specification

### Feature A: On-Demand Competitor Snapshot (`/signal`)

**Command:** `/signal [competitor]`
**Examples:** `/signal freed` · `/signal abridge` · `/signal epic`

Any member of the GTM team triggers an instant competitor snapshot. SIGNAL looks up the competitor in the database, assembles the current state from the latest scrape run, and posts a structured Block Kit card visible only to the requesting user (ephemeral).

**Output card structure:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴  FREED AI  —  Threat Level: HIGH
Last updated: 2 days ago
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 PRICING
  Free: $0 (limited)
  Pro: $99/mo  ⬇️ Was $109/mo (changed 6 days ago)
  Annual: $69/mo

⭐ G2 SENTIMENT
  Rating: 4.7/5  (↑ from 4.5 last month)
  Top complaint: "Limited specialty note templates"
  Top praise: "Fastest EHR push we've tested"

📣 RECENT MOVES  (last 30 days)
  • Launched browser extension for Epic EHR (Jan 28)
  • Added structured data export for billing teams (Jan 22)
  • 3 new G2 reviews mentioning Heidi by name

🧑‍💻 HIRING SIGNAL
  14 open roles  (+6 vs. last month)
  New: 2x Enterprise AE (US), 1x UK Sales Manager
  → Signal: Enterprise push + UK market entry

⚔️  HEIDI SEGMENTS AT RISK
  GP · Mental Health · Allied Health (US, CA)

[Full battlecard]  [Compare to Heidi]  [Alert me on changes]
```

**Additional commands:**

`/signal compare freed abridge` — side-by-side comparison of two competitors on pricing, G2, features, and threat level

`/signal who threatens [segment]` — lists all competitors threatening a specific Heidi segment (e.g., `/signal who threatens mental-health`)

`/signal latest` — returns the top 3 competitive signals from the past 7 days across all tracked competitors

---

### Feature B: Proactive Deal-Time Alerts

This is the highest-value feature. When a competitor makes a significant move, SIGNAL identifies which active deal channels are relevant and delivers the alert directly into those channels — not to a generic `#competitive-intel` channel that may not be watched by the rep handling that deal.

**Two trigger types:**

**Trigger 1: Competitor signal detected (data-driven)**

The Comp Analysis scraping pipeline runs and detects a significant event:
- Pricing change (any direction)
- New funding round or acquisition
- New feature launch (changelog entry)
- G2 rating shift >0.2 points
- Hiring spike (>30% increase in open roles week-over-week)
- New market entry (new geography mentioned in job postings or press releases)

SIGNAL classifies the signal by severity:

| Severity | Criteria | Alert behavior |
|---|---|---|
| P0 | EHR-native competitor launches free tier (Epic, athena) | Immediate alert to all relevant deal channels + `#competitive-intel` + `#gtm-leadership` |
| P1 | Pricing change, funding round, new EHR integration | Alert to relevant deal channels within 1 hour of detection |
| P2 | Changelog entry, G2 shift, hiring change | Batched into next daily digest |

**Trigger 2: Competitor mention in a deal channel (RTS-driven)**

The RTS API (`assistant.search.context`) monitors registered deal channels for competitor mentions. When a message in a deal channel contains a competitor name (e.g., "the customer mentioned Freed", "they're comparing us to DeepScribe"), SIGNAL:

1. Identifies which competitor was mentioned
2. Pulls the current snapshot for that competitor
3. Generates a contextual briefing tailored to the deal conversation
4. Posts it as a threaded reply to the message that contained the mention

```
[In thread under: "The Cedars-Sinai team mentioned they're 
evaluating Freed as a backup option"]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 SIGNAL — Competitive briefing: Freed AI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Freed dropped Pro pricing from $109 → $99/mo 6 days ago.
This may come up in your next call.

THEIR WEAKNESSES (from recent G2 reviews):
• "Limited specialty templates" — mentioned in 8/12 recent reviews
• "No native Epic integration — requires browser extension"
• "No Australian data sovereignty" — relevant if Cedars has compliance req.

YOUR ADVANTAGES vs. FREED for this account:
• Heidi has deeper specialty template library (19 vs. 6 Freed templates)
• Heidi AU data residency if required
• Heidi enterprise onboarding support — Freed is self-serve only

[Full Freed battlecard]  [Prep talking points]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Deal channel registration:**

Deal channels are registered by an admin using `/signal register-deal #channel-name [competitor-tags]`. Example: `/signal register-deal #deal-cedars-sinai freed deepscribe nuance`. The competitor tags tell SIGNAL which competitors to watch for in this channel. Untagged channels still receive alerts for P0 signals.

---

### Feature C: Weekly Battlecard Canvas

Every Monday at 7:00am in the team's timezone, SIGNAL posts a Slack Canvas to `#competitive-intel`. This replaces the HTML report — same intelligence, native Slack format, zero context-switching.

**Canvas structure:**

```
Heidi Competitive Intelligence — Week of June 2, 2026

━━━━━━ THIS WEEK'S TOP SIGNALS ━━━━━━
🔴 athenaAmbient extended free tier to AU users — direct 
   threat to Heidi's AU GP segment. See: athena card below.
🟡 Freed dropped Pro pricing by 9% (Jan 28)
🟡 DeepScribe posted 4x Enterprise AE roles — enterprise push
🟢 Nabla G2 rating dropped 0.3pts — negative EU press

━━━━━━ COMPETITOR CARDS ━━━━━━

[Freed AI]  [Suki]  [Nabla]  [DeepScribe]  [Abridge]
[Epic]  [athenahealth]  [Nuance DAX]  [Oracle]  [More ↓]

━━━━━━ THREAT MATRIX ━━━━━━
           GP   MH   Allied  Specialist  Enterprise
Freed      🔴   🔴   🟡      🟢          🟢
Abridge    🟢   🟢   🟢      🔴          🔴
Epic       🟡   🟢   🟢      🟡          🔴
athena     🔴   🟢   🟡      🟡          🟢
DeepScribe 🟡   🟢   🟡      🔴          🔴

━━━━━━ PRICING COMPARISON ━━━━━━
[Table: Heidi vs. top 5 on price, free tier, key features]

━━━━━━ RECOMMENDED ACTIONS ━━━━━━
1. Accelerate AU data residency messaging — athena's AU 
   expansion makes this a differentiation point now
2. Prep pricing objection response for Freed's $99 drop
3. Review Mental Health template library vs. Mentalyc — 
   their DAP template builder is gaining G2 mentions
```

Each competitor card is a Canvas section with expandable detail: full pricing breakdown, G2 verbatims, changelog summary, job signal analysis, and Heidi's competitive response points.

---

### Feature D: Competitive Signal Feed (`#competitive-intel` channel)

Between Monday digests, SIGNAL posts individual signal cards to `#competitive-intel` as P0 and P1 events are detected. These are concise — one card per signal, with direct links to the full battlecard on the Canvas.

```
🚨 NEW SIGNAL — athenaAmbient  [P0]

athenahealth extended free ambient AI to Australian users 
(announcement Jan 30, 2026). Previously US-only.

Impact: Directly threatens Heidi AU GP segment. 160,000+ 
athena AU users now have free AI scribe access.

Affected deal channels: #deal-westmead-health, #deal-royal-melb
Affected pipeline: $2.1M in AU renewal deals flagged

[View full athena battlecard]  [See affected deals]  [Prep response]
```

---

## 4. Technical Architecture

```
+--------------------------------------------------------------------------+
|                        SLACK WORKSPACE (Internal)                        |
|                                                                          |
|  #competitive-intel     Deal Channels          DM / Ephemeral            |
|  [Weekly Canvas]        [Deal-time alerts]     [/signal response]        |
+--------+---------------------+-----------------------------+-------------+
         |                     |                             |
         | Canvas Write        | Thread reply / Block Kit    | Slash command
         v                     v                             v
+--------+---------------------+-----------------------------+-------------+
|                    SIGNAL APPLICATION (Slack Bolt / Python)              |
|                                                                          |
|  - Events API Listener      - RTS Competitor Mention Detector            |
|  - Signal Classifier        - Deal Channel Registry                      |
|  - Alert Dispatcher         - Canvas Renderer                            |
|  - Slash Command Router     - Weekly Cron (APScheduler)                  |
+--------+---------------------+-----------------------------+-------------+
         |                     |                             |
         | Read/Write          | Embed + Search              | Tool calls
         v                     v                             v
+--------+---------------------+--------+   +--------------+-------------+
|        POSTGRESQL + PGVECTOR          |   |       MCP SERVER           |
|                                       |   |                            |
|  - competitors                        |   |  get_competitor_snapshot() |
|  - competitor_snapshots (weekly)      |   |  get_recent_signals()      |
|  - competitor_signals (event log)     |   |  compare_competitors()     |
|  - price_history                      |   |  search_intelligence()     |
|  - deal_channels                      |   |  get_battlecard()          |
|  - signal_deliveries (audit)          |   |  run_scrape_pipeline()     |
+---------------------------------------+   +----------------------------+
                                                         |
                                          Calls existing scraping tools:
                                          scrape_pricing.py
                                          scrape_changelogs.py
                                          scrape_reviews.py
                                          scrape_jobs.py
                                          scrape_funding.py
                                          analyze_competitive_landscape.py
```

### Relationship to Existing Comp Analysis Agent

SIGNAL does not rewrite any existing tool. It wraps the existing pipeline behind a Slack-facing interface:

| Existing component | Role in SIGNAL |
|---|---|
| `tools/config/competitors.json` | Competitor registry — unchanged, read by MCP server |
| `tools/scrape_pricing.py` | Called by MCP `run_scrape_pipeline()` tool |
| `tools/scrape_changelogs.py` | Called by MCP `run_scrape_pipeline()` tool |
| `tools/scrape_reviews.py` | Called by MCP `run_scrape_pipeline()` tool |
| `tools/scrape_jobs.py` | Called by MCP `run_scrape_pipeline()` tool |
| `tools/scrape_funding.py` | Called by MCP `run_scrape_pipeline()` tool |
| `tools/analyze_competitive_landscape.py` | Called by MCP after scrape, output stored to DB |
| `tools/build_html_report.py` | Replaced by Canvas renderer — HTML report deprecated |
| `tools/sheets_write_competitive.py` | Retained for longitudinal tracking, Canvas is primary |
| `tools/config/competitor_seed_data.json` | Retained as fallback — unchanged |

New components added:
- `signal_app.py` — Slack Bolt app entry point
- `signal_mcp_server.py` — MCP server exposing competitor tools to LLM
- `signal_canvas.py` — Canvas generation from competitive_analysis.json
- `signal_alerts.py` — Signal classifier, severity scoring, deal channel routing
- `signal_rts.py` — RTS API integration for competitor mention detection

### RTS API Integration

The RTS API is used for one specific purpose: detecting competitor mentions in registered deal channels.

When a message event fires in a registered deal channel, SIGNAL calls `assistant.search.context` with the message content as the query. The response is checked for semantic matches against the registered competitor names and aliases for that channel. If a match is found above a confidence threshold (0.85), the deal-time alert flow is triggered.

Competitor aliases handled by the matcher:

| Canonical name | Aliases matched |
|---|---|
| Freed AI | "Freed", "getfreed", "freed.ai" |
| Nuance DAX | "DAX", "Nuance", "Dragon Ambient" |
| Epic Ambient AI | "Epic", "Epic's scribe", "Epic ambient" |
| Abridge | "Abridge" |
| DeepScribe | "DeepScribe", "Deep Scribe" |

### Signal Severity Classification

When the scraping pipeline detects a change, the LLM classifies it against the severity model:

```python
classify_signal(
    event_type: str,           # 'pricing_change', 'funding', 'feature_launch', etc.
    competitor: str,
    description: str,
    affected_segments: list[str],
    affected_markets: list[str]
) -> SignalClassification:
    severity: Literal["P0", "P1", "P2"]
    alert_immediately: bool
    affected_deal_channel_tags: list[str]
    recommended_response: str
```

P0 criteria (alert immediately to all channels):
- EHR-native competitor (Epic, athena, Oracle, Nuance) launches free tier or drops price
- Any competitor raises >$100M funding
- Any competitor announces direct EHR integration with Epic or athenahealth
- Any competitor expands into a new market where Heidi has active pipeline

P1 criteria (alert relevant channels within 1 hour):
- Any Tier 1 competitor pricing change
- Any Tier 1 competitor raises funding
- New EHR integration by Tier 1 competitor
- Any competitor's G2 rating drops >0.3 (opportunity to surface in competitive conversations)

P2 criteria (batch into daily digest):
- Changelog entries without pricing/integration impact
- Job posting changes
- G2 rating shifts <0.3
- Blog post or marketing content change

---

## 5. Database Schema

```sql
CREATE EXTENSION IF NOT EXISTS pgvector;

-- Master competitor registry (mirrors competitors.json, synced on startup)
CREATE TABLE competitors (
    id SERIAL PRIMARY KEY,
    competitor_id VARCHAR(50) UNIQUE NOT NULL,   -- e.g. 'freed', 'abridge'
    name VARCHAR(255) NOT NULL,
    tier VARCHAR(20) NOT NULL,                    -- 'direct', 'adjacent'
    threat_level VARCHAR(20) NOT NULL,            -- 'critical', 'high', 'medium', 'low'
    website VARCHAR(500),
    pricing_url VARCHAR(500),
    g2_url VARCHAR(500),
    heidi_segments_threatened TEXT[],
    heidi_markets_threatened TEXT[],
    aliases TEXT[],                               -- for RTS mention matching
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Weekly scrape snapshots — one row per competitor per week
CREATE TABLE competitor_snapshots (
    id SERIAL PRIMARY KEY,
    competitor_id INT REFERENCES competitors(id),
    snapshot_date DATE NOT NULL,
    pricing_json JSONB,                           -- current plan structure
    g2_rating FLOAT,
    g2_review_count INT,
    g2_top_pros TEXT[],
    g2_top_cons TEXT[],
    open_role_count INT,
    open_role_breakdown JSONB,                    -- by category
    changelog_entries JSONB,                      -- new entries this week
    data_freshness JSONB,                         -- which sources were live vs. cached
    raw_analysis_json JSONB,                      -- full output from analyze_competitive_landscape.py
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(competitor_id, snapshot_date)
);

-- Individual competitive events/signals
CREATE TABLE competitor_signals (
    id SERIAL PRIMARY KEY,
    competitor_id INT REFERENCES competitors(id),
    signal_type VARCHAR(50) NOT NULL,             -- 'pricing_change', 'funding', 'feature_launch', etc.
    severity VARCHAR(5) NOT NULL,                 -- 'P0', 'P1', 'P2'
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    affected_segments TEXT[],
    affected_markets TEXT[],
    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source_url VARCHAR(500),
    alert_sent BOOLEAN DEFAULT FALSE,
    alert_sent_at TIMESTAMP
);

-- Pricing history for change detection
CREATE TABLE price_history (
    id SERIAL PRIMARY KEY,
    competitor_id INT REFERENCES competitors(id),
    recorded_date DATE NOT NULL,
    plan_name VARCHAR(100) NOT NULL,
    price_monthly FLOAT,
    price_annual FLOAT,
    currency VARCHAR(10) DEFAULT 'USD',
    notes TEXT,
    UNIQUE(competitor_id, recorded_date, plan_name)
);

-- Registered deal channels
CREATE TABLE deal_channels (
    id SERIAL PRIMARY KEY,
    slack_channel_id VARCHAR(255) UNIQUE NOT NULL,
    channel_name VARCHAR(255),
    registered_by_slack_user_id VARCHAR(255) NOT NULL,
    competitor_tags TEXT[],                       -- which competitors to watch for
    is_active BOOLEAN DEFAULT TRUE,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Audit of all alerts sent
CREATE TABLE signal_deliveries (
    id SERIAL PRIMARY KEY,
    signal_id INT REFERENCES competitor_signals(id),
    slack_channel_id VARCHAR(255),
    slack_user_id VARCHAR(255),                   -- NULL for channel posts
    delivery_type VARCHAR(30),                    -- 'deal_alert', 'channel_post', 'dm', 'ephemeral'
    delivered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    was_interacted BOOLEAN DEFAULT FALSE          -- did anyone click through?
);

-- Competitor intelligence embeddings for semantic search
CREATE TABLE competitor_intelligence_chunks (
    id SERIAL PRIMARY KEY,
    competitor_id INT REFERENCES competitors(id),
    snapshot_id INT REFERENCES competitor_snapshots(id),
    chunk_type VARCHAR(50),                       -- 'pricing', 'g2_review', 'changelog', 'job_signal'
    content TEXT NOT NULL,
    embedding VECTOR(1024),                       -- Voyage AI voyage-3
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 6. MCP Server Specification

The MCP server exposes the competitive intelligence database and scraping pipeline to the LLM layer. It is the only component that directly queries the database and calls the existing scraping tools.

### Exposed Tools

**`get_competitor_snapshot(competitor_id: str, include_history_days: int = 30) -> CompetitorSnapshot`**

Returns the latest snapshot for a competitor, including pricing, G2 data, changelog entries, hiring signal, and a 30-day price history. Used to generate `/signal [competitor]` responses.

```python
# Returns structured dict including:
{
    "name": "Freed AI",
    "threat_level": "high",
    "pricing": {"free": "$0", "pro": "$99/mo", "annual": "$69/mo"},
    "pricing_changed_days_ago": 6,
    "g2_rating": 4.7,
    "g2_rating_trend": "+0.2 vs last month",
    "g2_top_cons": ["Limited specialty templates", "Browser extension required for Epic"],
    "open_roles": 14,
    "hiring_signal": "Enterprise push + UK market entry",
    "recent_changelog": [...],
    "heidi_advantages": [...],
    "data_freshness": {"pricing": "live", "g2": "cached"}
}
```

**`get_recent_signals(days: int = 7, severity_filter: str = None) -> list[CompetitorSignal]`**

Returns all competitive signals detected in the past N days, optionally filtered by severity. Used for the `/signal latest` command and the weekly Canvas generation.

**`compare_competitors(competitor_a: str, competitor_b: str) -> ComparisonResult`**

Returns a structured side-by-side comparison of two competitors on pricing, G2, features, threat level, and Heidi's positioning against each. Used for `/signal compare [a] [b]`.

**`get_battlecard(competitor_id: str, deal_context: str = None) -> Battlecard`**

Returns a full battlecard for a competitor. When `deal_context` is provided (the text of recent messages from the deal channel), the LLM tailors the competitive response points to the specific objections and topics being discussed in that deal.

**`search_intelligence(query: str, top_k: int = 5) -> list[IntelligenceChunk]`**

Semantic search across all competitor intelligence chunks using Voyage AI embeddings. Used when a rep asks a freeform question like `/signal does anyone use Epic integration to compete against us?`

**`run_scrape_pipeline(competitor_id: str = None, force: bool = False) -> PipelineResult`**

Triggers the existing Comp Analysis scraping pipeline (or a subset for a single competitor). Called by the weekly cron job and available as an admin command. `force=True` bypasses the 24-hour rate limit on re-scraping.

---

## 7. Slack Primitives Used

| Primitive | Purpose |
|---|---|
| **Slash commands (`/signal`)** | On-demand competitor lookup, comparison, deal registration |
| **Events API** | Monitoring registered deal channels for competitor mention events |
| **RTS API (`assistant.search.context`)** | Semantic competitor mention detection in deal channel messages |
| **Block Kit (ephemeral messages)** | `/signal` responses visible only to the requesting user |
| **Block Kit (channel posts)** | P0/P1 signal alerts in `#competitive-intel` and deal channels |
| **Block Kit (threaded replies)** | Deal-time briefing cards as thread replies on competitor-mention messages |
| **Canvas** | Weekly battlecard digest with competitor cards, threat matrix, pricing table |
| **APScheduler** | Weekly cron at Monday 7:00am for Canvas generation and scrape run |

---

## 8. What's New vs. What's Ported

### Ported directly from Comp Analysis agent (minimal changes)

- All 5 scraping tools (`scrape_pricing.py`, `scrape_changelogs.py`, `scrape_reviews.py`, `scrape_jobs.py`, `scrape_funding.py`)
- `analyze_competitive_landscape.py` — called as a subprocess, output stored to DB
- `competitor_seed_data.json` — unchanged fallback
- `competitors.json` — unchanged registry, synced to `competitors` table on startup
- `fetch_url.py` — exposed as `/signal url [url]` slash command for manual intel drops

### New components

- `signal_app.py` — Slack Bolt entry point, command routing, event handling
- `signal_mcp_server.py` — MCP server, all 6 tool definitions
- `signal_canvas.py` — Monday Canvas renderer (replaces `build_html_report.py`)
- `signal_alerts.py` — Signal severity classifier, deal channel routing, alert dispatcher
- `signal_rts.py` — RTS API integration, competitor mention detector

### Retired (replaced by Slack surface)

- `build_html_report.py` — replaced by `signal_canvas.py`
- `sheets_write_competitive.py` — demoted to secondary output; Canvas is primary

---

## 9. Security & Configuration

**API keys stored as environment variables, never in code:**
- `ANTHROPIC_API_KEY` — LLM calls
- `SLACK_BOT_TOKEN` — Slack Bolt
- `SLACK_APP_TOKEN` — Socket Mode
- `VOYAGE_API_KEY` — Voyage AI embeddings
- `DATABASE_URL` — PostgreSQL connection

**Competitor data is internal only.** No competitive intelligence is posted to customer-facing or shared external channels. `signal_alerts.py` validates that the target channel is an internal workspace channel before posting. Slack Connect channels are excluded from alert delivery.

**Deal channel access is explicit.** SIGNAL only monitors channels that have been registered by an admin via `/signal register-deal`. Unregistered channels receive no monitoring. Registration is logged in `signal_deliveries` for audit.

**Known scraping limitations from production learnings:**
- G2 blocks scrapers — falls back to seed ratings (marked as "cached" in Canvas)
- Most competitor pricing pages are JS-rendered — `requests` gets shell only; Playwright needed for live data in production
- Freed's changelog at `/changelog` returns 404 — use their blog instead
- LinkedIn blocks job scraping — falls back to careers pages directly

---

## 10. Hackathon Delivery Scope

### What to Build (6 weeks)

**Week 1–2: Foundation**
- Slack Bolt app + slash command routing for `/signal [competitor]`
- PostgreSQL schema + competitor registry sync from `competitors.json`
- MCP server with `get_competitor_snapshot()` and `get_recent_signals()`
- Seed the DB with current snapshot data from existing `.tmp/` output files
- Ephemeral Block Kit response card for `/signal` command

**Week 3–4: Alerts + deal channels**
- Deal channel registration: `/signal register-deal`
- RTS API integration for competitor mention detection
- Deal-time briefing card (threaded reply with tailored battlecard)
- P1 signal alert to `#competitive-intel` when scrape detects pricing change

**Week 5: Weekly Canvas**
- `signal_canvas.py` — Monday Canvas renderer
- Run Comp Analysis pipeline, store output to DB, generate Canvas
- Competitor cards with expandable detail sections
- Threat matrix and pricing comparison table

**Week 6: Polish + demo**
- Seed demo environment with realistic signal history
- P0 alert demo trigger (simulate athenaAmbient AU expansion event)
- Deal channel demo (simulate rep mentioning "Freed" in deal channel)
- 3-minute demo video

### What to Leave Out (Post-Hackathon)
- Playwright-based live pricing scraping (use seed data for demo)
- Google Sheets write (Canvas replaces it for the hackathon)
- Multi-workspace / multi-company support
- `/signal url [url]` manual intel drop (stretch goal)

### Demo Script (3 minutes)

1. **(0:00–0:30)** Context: "Heidi's growth team tracks 13 competitors. The old system: a weekly HTML report in a shared folder. Nobody reads it."

2. **(0:30–1:00)** Show `/signal freed` — instant ephemeral card with current pricing (note the price drop from 6 days ago), G2 rating trend, hiring signal (UK expansion), and Heidi's specific advantages. "Anyone on the team, in any channel, in 5 seconds."

3. **(1:00–1:45)** Show a deal channel. Rep types: "The Cedars-Sinai team mentioned they're evaluating Freed as a backup option." SIGNAL detects the mention via RTS API, posts a threaded reply with Freed's current pricing, their G2 weaknesses on specialty templates, and Heidi's advantages specific to this account. "Intelligence finds you, not the other way around."

4. **(1:45–2:30)** Trigger a P0 signal: athenaAmbient extends free tier to AU users. Show the alert card in `#competitive-intel` with severity badge, affected pipeline value, affected deal channels flagged. Click through to full athena battlecard on Canvas.

5. **(2:30–3:00)** Show Monday morning Canvas in `#competitive-intel` — weekly digest with top signals, threat matrix, competitor cards. Close on the Freed card showing the pricing history chart. "The report still exists. But now it comes to you."

---

## 11. Why SIGNAL Wins the Hackathon

**It's built on real, working code.** The Comp Analysis agent is a production system with a real competitor database, working scraping tools (with known failure modes documented), and a structured analysis pipeline. SIGNAL is not a demo — it's a real intelligence system with a new delivery layer. Judges will see seed data from a live system, not synthetic placeholder content.

**The Slack primitives are genuinely used.** RTS API detects competitor mentions semantically — not keyword matching. MCP exposes a real intelligence database, not a static folder. Canvas replaces a broken delivery mechanism with a native one. Every primitive has a specific, defensible reason to exist.

**The problem is universally legible.** Every person on a GTM team has had the experience of finding out a competitor made a move when a customer told them. That's the moment SIGNAL prevents. Judges will feel it.

**Health-tech specificity makes it credible.** The competitor set is real. The threat levels are real. Epic giving away a free AI scribe to 250M patient records customers is a specific, named existential threat — not a generic "the market is competitive" observation. The domain depth signals that this was built by someone who understands the problem, not just the technology.
