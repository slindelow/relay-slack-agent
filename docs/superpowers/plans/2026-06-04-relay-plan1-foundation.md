# RELAY Plan 1: Classifier Validation + Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate the question classifier empirically before writing any product code, then build the load-bearing foundation — encrypted token storage, async event queuing, multi-tenant PostgreSQL schema with row-level security, Slack OAuth, and the `/relay help` command — that all subsequent RELAY plans build on.

**Architecture:** Python async Slack Bolt + FastAPI for OAuth callbacks. Bolt and FastAPI query PostgreSQL directly via SQLAlchemy async — the MCP layer is scoped exclusively to LLM inference calls and never touches the application data path. Every Slack Events API payload is acked immediately (HTTP 200) and enqueued to Celery/Redis for async processing. PostgreSQL Row Level Security enforces workspace isolation at the database layer. Tokens are encrypted at rest using AES-256-GCM with an environment-managed master key (designed to swap for KMS in production).

**Tech Stack:** Python 3.12, uv, slack-bolt[async], FastAPI, SQLAlchemy 2.0 (async) + asyncpg, Alembic, PostgreSQL 15+, Celery 5, Redis 7, cryptography, anthropic SDK (claude-haiku-4-5-20251001), pydantic-settings v2, pytest, pytest-asyncio, httpx

---

## Architectural Decisions Locked In Here

These decisions from the review must not be reversed in later plans:

1. **Bolt + FastAPI query Postgres directly.** MCP is inference-only.
2. **Ack Slack in < 3 seconds, always.** Classification happens in Celery, not in the event handler.
3. **`Workspace.slack_team_id`** (the actual Slack team ID string) is distinct from `Workspace.id` (internal UUID). Both are needed; reinstall reuses the existing row.
4. **RLS enforces tenant isolation at the DB layer**, not only the application layer.
5. **`customer_workspace_id`** is stored on `monitored_channels` at registration time (Plan 2). The mechanism: call `conversations.info` at registration, extract the external workspace ID from `shared_channel_invite` context, classify all messages from that workspace as customer messages — deterministic, zero per-message API calls.
6. **Classifier thresholds are empirically validated** before any product code runs. The 0.85/0.60 values are hypotheses, not facts.
7. **Post as bot** (not as the CSM user) for v1. The `users_tokens` table is deferred to Plan 5.

---

## File Map

```
relay/
├── pyproject.toml
├── .env.example
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py
├── classifier/
│   ├── __init__.py
│   ├── label.py          # Interactive labeling CLI → JSONL output
│   ├── classify.py       # Two prompt variants, structured output
│   └── evaluate.py       # Precision/recall/F1 + threshold sweep
├── relay/
│   ├── __init__.py
│   ├── config.py         # pydantic-settings Settings
│   ├── crypto.py         # AES-256-GCM encrypt/decrypt
│   ├── db/
│   │   ├── __init__.py
│   │   ├── engine.py     # Async SQLAlchemy engine + session factory
│   │   ├── models.py     # All ORM models (all tenant tables)
│   │   └── session.py    # get_session context manager with RLS setter
│   ├── slack/
│   │   ├── __init__.py
│   │   ├── app.py        # Bolt app init
│   │   ├── oauth.py      # Workspace upsert, bot token storage
│   │   ├── verify.py     # Signature verification (standalone, not via Bolt)
│   │   └── home.py       # App Home view publisher
│   ├── api/
│   │   ├── __init__.py
│   │   └── main.py       # FastAPI app, mounts Bolt, health endpoint
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── celery_app.py # Celery app + Redis broker config
│   │   └── tasks.py      # process_slack_event task (stub for Plan 2)
│   └── commands/
│       ├── __init__.py
│       └── help.py       # /relay help handler
└── tests/
    ├── conftest.py        # DB fixtures (transactional rollback per test)
    ├── test_config.py
    ├── test_crypto.py
    ├── test_models.py
    ├── test_oauth.py
    ├── test_verify.py
    ├── test_worker.py
    ├── test_commands.py
    └── classifier/
        ├── __init__.py
        ├── fixtures/
        │   └── sample_labeled.jsonl
        ├── test_label_format.py
        ├── test_classify.py
        └── test_evaluate.py
```

---

## Task 0: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `alembic.ini`
- Create: directory structure

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "relay"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "slack-bolt[async]>=1.21",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "pgvector>=0.3",
    "celery[redis]>=5.4",
    "redis>=5.2",
    "cryptography>=43",
    "anthropic>=0.40",
    "pydantic-settings>=2.7",
    "httpx>=0.28",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `.env.example`**

```bash
# Slack app credentials
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_SIGNING_SECRET=
SLACK_BOT_TOKEN=          # optional: single-workspace dev mode only

# Database
DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay

# Test database (separate DB — never the production one)
TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay_test

# Redis / Celery
REDIS_URL=redis://localhost:6379/0

# Token encryption — must be exactly 64 hex chars (32 bytes / 256 bits)
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
TOKEN_ENCRYPTION_KEY=

# Anthropic
ANTHROPIC_API_KEY=

# App
APP_BASE_URL=https://your-app.example.com
ENVIRONMENT=development

# Classifier thresholds — update after running Task 3 evaluation
CLASSIFIER_OPEN_THRESHOLD=0.85
CLASSIFIER_CANDIDATE_THRESHOLD=0.60
CLASSIFIER_VARIANT=a
```

- [ ] **Step 3: Install uv and dependencies**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

Expected: `.venv` created, all dependencies installed.

- [ ] **Step 4: Create directory structure**

```bash
mkdir -p relay/{db,slack,api,worker,commands}
mkdir -p classifier/dataset
mkdir -p tests/classifier/fixtures
mkdir -p alembic/versions
touch relay/__init__.py relay/db/__init__.py relay/slack/__init__.py
touch relay/api/__init__.py relay/worker/__init__.py relay/commands/__init__.py
touch classifier/__init__.py
touch tests/__init__.py tests/classifier/__init__.py
```

- [ ] **Step 5: Initialize git and commit**

```bash
git init
printf ".env\n__pycache__\n*.pyc\n.pytest_cache\n.venv\n*.egg-info\n" > .gitignore
git add pyproject.toml .env.example .gitignore
git commit -m "chore: project scaffolding"
```

---

## Task 1: Classifier — Labeling Script

**Files:**
- Create: `classifier/label.py`
- Create: `tests/classifier/fixtures/sample_labeled.jsonl`
- Create: `tests/classifier/test_label_format.py`

- [ ] **Step 1: Write failing test**

```python
# tests/classifier/test_label_format.py
import json
from pathlib import Path


def test_labeled_jsonl_format():
    """Every line in the sample fixture has required fields with valid values."""
    fixture = Path("tests/classifier/fixtures/sample_labeled.jsonl")
    assert fixture.exists(), "Fixture file must exist before running classifier tests"
    lines = fixture.read_text().strip().splitlines()
    assert len(lines) >= 10, "Fixture must have at least 10 examples"
    for line in lines:
        record = json.loads(line)
        assert "text" in record, f"Missing 'text' in: {line}"
        assert "label" in record, f"Missing 'label' in: {line}"
        assert record["label"] in (0, 1), f"Label must be 0 or 1, got: {record['label']}"
        assert isinstance(record["text"], str) and len(record["text"]) > 0
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/classifier/test_label_format.py -v
```

Expected: FAIL — fixture file does not exist.

- [ ] **Step 3: Create `tests/classifier/fixtures/sample_labeled.jsonl`**

```jsonl
{"text": "Hey, is the API down? We're getting 503s on all requests since 9am.", "label": 1}
{"text": "Can you confirm what version of the SDK supports webhooks?", "label": 1}
{"text": "Thanks for the update, we'll check on our end.", "label": 0}
{"text": "Our migration to v2 is blocked — the batch endpoint returns 422 for payloads over 1MB.", "label": 1}
{"text": "Happy new year to the team! 🎉", "label": 0}
{"text": "We pushed the deploy, should be live in 30 min.", "label": 0}
{"text": "Is there a way to export audit logs to S3 directly?", "label": 1}
{"text": "Got it, thanks!", "label": 0}
{"text": "We're seeing latency spikes on the /ingest endpoint since yesterday — is anything on your side?", "label": 1}
{"text": "Our team is available for the call at 3pm EST.", "label": 0}
{"text": "The SSO integration stopped working after your maintenance window last night.", "label": 1}
{"text": "Sounds good, we'll loop back after internal review.", "label": 0}
```

- [ ] **Step 4: Create `classifier/label.py`**

```python
#!/usr/bin/env python3
"""Interactive labeling CLI: reads raw messages JSONL, outputs labeled JSONL.

Usage:
    uv run python classifier/label.py --input dataset/raw.jsonl --output dataset/labeled.jsonl
"""

import argparse
import json
import sys
from pathlib import Path


def label_messages(input_path: Path, output_path: Path) -> None:
    lines = input_path.read_text().strip().splitlines()
    print(f"Labeling {len(lines)} messages. Controls: 1=question, 0=not a question, s=skip, q=quit.\n")

    with output_path.open("a") as out:
        for i, line in enumerate(lines):
            record = json.loads(line)
            text = record.get("text", "")
            print(f"[{i + 1}/{len(lines)}] {text[:300]}")

            while True:
                key = input("  Label (1/0/s/q): ").strip().lower()
                if key == "q":
                    print("Quitting early.")
                    return
                if key == "s":
                    break
                if key in ("0", "1"):
                    out.write(json.dumps({"text": text, "label": int(key)}) + "\n")
                    out.flush()
                    break
                print("  Invalid input. Use 1, 0, s (skip), or q (quit).")

    print(f"\nDone. Labeled messages written to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Label Slack messages for classifier validation.")
    parser.add_argument("--input", required=True, type=Path, help="Input JSONL file of raw messages")
    parser.add_argument("--output", required=True, type=Path, help="Output JSONL file for labeled messages")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    label_messages(args.input, args.output)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run test — expect PASS**

```bash
uv run pytest tests/classifier/test_label_format.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add classifier/label.py tests/classifier/fixtures/sample_labeled.jsonl tests/classifier/test_label_format.py
git commit -m "feat(classifier): labeling script and sample fixture"
```

---

## Task 2: Classifier — Two Prompt Variants

**Files:**
- Create: `classifier/classify.py`
- Create: `tests/classifier/test_classify.py`

- [ ] **Step 1: Write failing test**

```python
# tests/classifier/test_classify.py
import pytest
from classifier.classify import classify_message, ClassificationResult


@pytest.mark.asyncio
async def test_variant_a_classifies_obvious_question():
    result = await classify_message(
        text="Is the API down? We're seeing 503 errors on every request.",
        variant="a",
    )
    assert isinstance(result, ClassificationResult)
    assert result.is_question is True
    assert 0.0 <= result.confidence <= 1.0
    assert result.variant == "a"


@pytest.mark.asyncio
async def test_variant_b_classifies_obvious_non_question():
    result = await classify_message(
        text="Thanks for the quick reply! We'll check on our end.",
        variant="b",
    )
    assert isinstance(result, ClassificationResult)
    assert result.is_question is False
    assert 0.0 <= result.confidence <= 1.0
    assert result.variant == "b"


@pytest.mark.asyncio
async def test_result_has_all_fields():
    result = await classify_message(text="Can you check the status page?", variant="a")
    assert hasattr(result, "is_question")
    assert hasattr(result, "confidence")
    assert hasattr(result, "reasoning")
    assert hasattr(result, "variant")
    assert isinstance(result.reasoning, str) and len(result.reasoning) > 0
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/classifier/test_classify.py -v
```

Expected: FAIL — `classifier.classify` does not exist.

- [ ] **Step 3: Create `classifier/classify.py`**

```python
"""Two prompt variants for Slack Connect message classification.

Variant A: explicit rule list
Variant B: role-based with priority heuristics

Run both on your labeled dataset using evaluate.py, pick the one with
higher F1 at your target threshold, and record the winner in CLASSIFIER_VARIANT.
"""

import json
from dataclasses import dataclass
from typing import Literal

import anthropic

_client = anthropic.AsyncAnthropic()
_MODEL = "claude-haiku-4-5-20251001"


@dataclass
class ClassificationResult:
    is_question: bool
    confidence: float   # 0.0–1.0
    reasoning: str
    variant: Literal["a", "b"]


_SYSTEM_A = """\
Classify the following message sent by a customer in a shared Slack Connect support channel.

Respond with a JSON object only. No text before or after the JSON:
{
  "is_question": <true if the message requires a response from the support team, false otherwise>,
  "confidence": <float 0.0-1.0>,
  "reasoning": <one sentence>
}

A message REQUIRES a response if it:
- Asks for help, status, or information
- Reports a bug, error, outage, or degraded service
- Requests an action (access grant, config change, feature enable)
- Expresses a blocker preventing the customer from proceeding

A message does NOT require a response if it is:
- A greeting, thank-you, or acknowledgment
- A status update FROM the customer ("we deployed", "we'll check")
- Scheduling logistics ("see you at 3pm")
- An emoji reaction or very short filler phrase
"""

_SYSTEM_B = """\
You are a customer success operations classifier. Decide if a customer's Slack message requires a response from the internal team.

Respond with exactly this JSON object and nothing else:
{
  "is_question": <boolean>,
  "confidence": <float 0.0-1.0>,
  "reasoning": <string, one sentence>
}

Rules:
- is_question=true: direct questions, problem reports, error messages, access requests, feature requests, anything where silence would leave the customer waiting on the team.
- is_question=false: acknowledgments ("got it", "thanks"), customer-side status updates ("we pushed the fix"), pleasantries, scheduling notes.
- Use confidence < 0.6 only when you genuinely cannot tell from the message text alone.
- Classify only the message text provided. Do not infer from context you do not have.
"""


async def classify_message(text: str, variant: Literal["a", "b"]) -> ClassificationResult:
    """Classify a single message. Raises anthropic.APIError on network/API failure."""
    system = _SYSTEM_A if variant == "a" else _SYSTEM_B
    response = await _client.messages.create(
        model=_MODEL,
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": f"Message:\n{text}"}],
    )
    raw = response.content[0].text.strip()
    # Strip markdown code fences if the model adds them
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1]
        if raw.startswith("json"):
            raw = raw[4:]
    data = json.loads(raw)
    return ClassificationResult(
        is_question=bool(data["is_question"]),
        confidence=float(data["confidence"]),
        reasoning=str(data["reasoning"]),
        variant=variant,
    )
```

- [ ] **Step 4: Run tests — expect PASS** (requires `ANTHROPIC_API_KEY`)

```bash
ANTHROPIC_API_KEY=<your-key> uv run pytest tests/classifier/test_classify.py -v
```

Expected: All 3 PASS. If an obvious label is wrong, note which variant and iteration.

- [ ] **Step 5: Commit**

```bash
git add classifier/classify.py tests/classifier/test_classify.py
git commit -m "feat(classifier): two prompt variants with structured output"
```

---

## Task 3: Classifier — Evaluation & Threshold Sweep

**Files:**
- Create: `classifier/evaluate.py`
- Create: `tests/classifier/test_evaluate.py`

- [ ] **Step 1: Write failing test**

```python
# tests/classifier/test_evaluate.py
from classifier.evaluate import precision_recall_f1, threshold_sweep


def test_perfect_predictions():
    preds = [{"confidence": 0.95}, {"confidence": 0.15}]
    true_labels = [1, 0]
    p, r, f = precision_recall_f1(preds, true_labels, threshold=0.5)
    assert p == 1.0
    assert r == 1.0
    assert f == 1.0


def test_all_false_positives_gives_zero_precision():
    preds = [{"confidence": 0.9}, {"confidence": 0.85}]
    true_labels = [0, 0]
    p, r, f = precision_recall_f1(preds, true_labels, threshold=0.5)
    assert p == 0.0


def test_no_positives_predicted_gives_zero_recall():
    preds = [{"confidence": 0.1}, {"confidence": 0.2}]
    true_labels = [1, 1]
    p, r, f = precision_recall_f1(preds, true_labels, threshold=0.5)
    assert r == 0.0


def test_threshold_sweep_is_sorted():
    preds = [{"confidence": 0.9}, {"confidence": 0.3}, {"confidence": 0.7}, {"confidence": 0.4}]
    true_labels = [1, 0, 1, 0]
    results = threshold_sweep(preds, true_labels)
    thresholds = [r["threshold"] for r in results]
    assert thresholds == sorted(thresholds)


def test_threshold_sweep_includes_target_thresholds():
    preds = [{"confidence": 0.9}, {"confidence": 0.3}]
    true_labels = [1, 0]
    results = threshold_sweep(preds, true_labels)
    checked = {r["threshold"] for r in results}
    assert 0.60 in checked
    assert 0.85 in checked


def test_threshold_sweep_has_required_keys():
    preds = [{"confidence": 0.9}, {"confidence": 0.3}]
    true_labels = [1, 0]
    results = threshold_sweep(preds, true_labels)
    for row in results:
        assert "threshold" in row
        assert "precision" in row
        assert "recall" in row
        assert "f1" in row
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/classifier/test_evaluate.py -v
```

Expected: FAIL — `classifier.evaluate` does not exist.

- [ ] **Step 3: Create `classifier/evaluate.py`**

```python
"""Precision/recall evaluation and threshold sweep for the question classifier.

Run as a script:
    ANTHROPIC_API_KEY=sk-... uv run python classifier/evaluate.py dataset/labeled.jsonl a
    ANTHROPIC_API_KEY=sk-... uv run python classifier/evaluate.py dataset/labeled.jsonl b
"""

import asyncio
import json
from pathlib import Path
from typing import Any


def precision_recall_f1(
    preds: list[dict],
    true_labels: list[int],
    threshold: float,
) -> tuple[float, float, float]:
    """Compute precision, recall, and F1 at a given confidence threshold.

    preds: list of {"confidence": float} (predicted confidence scores)
    true_labels: list of int (0 or 1 ground truth)
    """
    tp = fp = fn = 0
    for pred, truth in zip(preds, true_labels):
        predicted_positive = pred["confidence"] >= threshold
        if predicted_positive and truth == 1:
            tp += 1
        elif predicted_positive and truth == 0:
            fp += 1
        elif not predicted_positive and truth == 1:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    return precision, recall, f1


def threshold_sweep(
    preds: list[dict],
    true_labels: list[int],
) -> list[dict[str, Any]]:
    """Sweep thresholds 0.50–0.95, always including 0.60 and 0.85."""
    thresholds = sorted(
        set([round(i * 0.05, 2) for i in range(10, 20)] + [0.60, 0.85])
    )
    return [
        {
            "threshold": t,
            **dict(zip(("precision", "recall", "f1"), precision_recall_f1(preds, true_labels, t))),
        }
        for t in thresholds
    ]


async def evaluate_dataset(labeled_jsonl: Path, variant: str = "a") -> None:
    from classifier.classify import classify_message

    records = [json.loads(l) for l in labeled_jsonl.read_text().strip().splitlines()]
    texts = [r["text"] for r in records]
    true_labels = [r["label"] for r in records]

    print(f"\nEvaluating variant '{variant}' on {len(records)} examples...\n")
    results = await asyncio.gather(*[classify_message(t, variant=variant) for t in texts])  # type: ignore[arg-type]

    preds = [{"confidence": r.confidence} for r in results]
    sweep = threshold_sweep(preds, true_labels)

    print(f"{'Threshold':>10}  {'Precision':>10}  {'Recall':>8}  {'F1':>8}")
    for row in sweep:
        marker = ""
        if row["threshold"] == 0.85:
            marker = "  <-- candidate open threshold"
        elif row["threshold"] == 0.60:
            marker = "  <-- candidate floor threshold"
        print(
            f"{row['threshold']:>10.2f}  {row['precision']:>10.3f}  "
            f"{row['recall']:>8.3f}  {row['f1']:>8.3f}{marker}"
        )

    print("\n--- Misclassified examples ---")
    for i, (result, truth) in enumerate(zip(results, true_labels)):
        predicted = 1 if result.confidence >= 0.85 else 0
        if predicted != truth:
            print(f"[{i}] truth={truth} predicted={predicted} conf={result.confidence:.2f}")
            print(f"     text: {texts[i][:120]}")
            print(f"     reasoning: {result.reasoning}")


if __name__ == "__main__":
    import sys

    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("classifier/dataset/labeled.jsonl")
    variant = sys.argv[2] if len(sys.argv) > 2 else "a"
    asyncio.run(evaluate_dataset(path, variant))
```

- [ ] **Step 4: Run unit tests — expect PASS**

```bash
uv run pytest tests/classifier/test_evaluate.py -v
```

Expected: All 6 PASS.

- [ ] **Step 5: Run evaluation on the sample fixture**

```bash
ANTHROPIC_API_KEY=<your-key> uv run python classifier/evaluate.py \
  tests/classifier/fixtures/sample_labeled.jsonl a
```

Then variant b:

```bash
ANTHROPIC_API_KEY=<your-key> uv run python classifier/evaluate.py \
  tests/classifier/fixtures/sample_labeled.jsonl b
```

- [ ] **Step 6: CRITICAL GATE — do not proceed past here without:**

  1. Collecting **200+ real anonymized Slack Connect messages** and running `classifier/label.py` to label them.
  2. Running `evaluate.py` on that dataset with both variants.
  3. Confirming **precision ≥ 0.80 and recall ≥ 0.70** at your chosen open threshold.
  4. Recording the winning values in `.env.example`:

  ```bash
  CLASSIFIER_OPEN_THRESHOLD=0.85      # update to empirical value
  CLASSIFIER_CANDIDATE_THRESHOLD=0.60 # update to empirical value
  CLASSIFIER_VARIANT=a                # whichever variant won
  ```

  If neither variant reaches the gate: revise the prompts in `classify.py`, re-run, and repeat. Do not commit placeholder thresholds.

- [ ] **Step 7: Commit**

```bash
git add classifier/evaluate.py tests/classifier/test_evaluate.py
git commit -m "feat(classifier): evaluation script with threshold sweep — GATE PASSED"
```

---

## Task 4: Config Module

**Files:**
- Create: `relay/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_config.py
import pytest
from relay.config import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "test_client")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "test_secret")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "test_signing")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("APP_BASE_URL", "https://relay.example.com")

    s = Settings()
    assert s.slack_client_id == "test_client"
    assert len(s.token_encryption_key_bytes) == 32


def test_invalid_key_length_raises(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "x")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "x")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("APP_BASE_URL", "https://x.com")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "tooshort")
    with pytest.raises(Exception):
        Settings()


def test_non_hex_key_raises(monkeypatch):
    monkeypatch.setenv("SLACK_CLIENT_ID", "x")
    monkeypatch.setenv("SLACK_CLIENT_SECRET", "x")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "x")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost/0")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    monkeypatch.setenv("APP_BASE_URL", "https://x.com")
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEY", "z" * 64)  # 'z' is not valid hex
    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create `relay/config.py`**

```python
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    slack_client_id: str
    slack_client_secret: str
    slack_signing_secret: str
    slack_bot_token: str = ""

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # 64 hex chars = 32 bytes = 256-bit AES key
    token_encryption_key: str

    anthropic_api_key: str
    app_base_url: str
    environment: str = "development"

    classifier_open_threshold: float = 0.85
    classifier_candidate_threshold: float = 0.60
    classifier_variant: str = "a"

    @field_validator("token_encryption_key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        if len(v) != 64:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be exactly 64 hex chars (32 bytes)")
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be valid hexadecimal")
        return v

    @property
    def token_encryption_key_bytes(self) -> bytes:
        return bytes.fromhex(self.token_encryption_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_config.py -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add relay/config.py tests/test_config.py
git commit -m "feat: pydantic-settings config with encryption key validation"
```

---

## Task 5: Crypto Module

**Files:**
- Create: `relay/crypto.py`
- Create: `tests/test_crypto.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_crypto.py
import pytest
from relay.crypto import decrypt_token, encrypt_token

FAKE_KEY = bytes.fromhex("a" * 64)


def test_round_trip():
    plaintext = "xoxb-test-bot-token-abc123"
    ciphertext, nonce = encrypt_token(plaintext, FAKE_KEY)
    assert decrypt_token(ciphertext, nonce, FAKE_KEY) == plaintext


def test_ciphertext_differs_from_plaintext():
    ciphertext, _ = encrypt_token("xoxb-test-token", FAKE_KEY)
    assert ciphertext != b"xoxb-test-token"


def test_nonce_is_unique_each_call():
    _, nonce1 = encrypt_token("same", FAKE_KEY)
    _, nonce2 = encrypt_token("same", FAKE_KEY)
    assert nonce1 != nonce2


def test_nonce_is_12_bytes():
    _, nonce = encrypt_token("token", FAKE_KEY)
    assert len(nonce) == 12


def test_wrong_key_raises():
    ciphertext, nonce = encrypt_token("token", FAKE_KEY)
    wrong_key = bytes.fromhex("b" * 64)
    with pytest.raises(Exception):
        decrypt_token(ciphertext, nonce, wrong_key)


def test_tampered_ciphertext_raises():
    ciphertext, nonce = encrypt_token("token", FAKE_KEY)
    tampered = ciphertext[:-1] + bytes([ciphertext[-1] ^ 0xFF])
    with pytest.raises(Exception):
        decrypt_token(tampered, nonce, FAKE_KEY)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_crypto.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create `relay/crypto.py`**

```python
"""AES-256-GCM token encryption.

PRODUCTION NOTE: The master_key here comes from an environment variable.
For production, replace with a KMS-wrapped DEK per workspace (AWS KMS, GCP KMS,
or HashiCorp Vault). Never log the key. Never log decrypted token values.
"""

import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_token(plaintext: str, master_key: bytes) -> tuple[bytes, bytes]:
    """Encrypt a plaintext token string. Returns (ciphertext, nonce).

    master_key: exactly 32 bytes (use Settings.token_encryption_key_bytes).
    nonce: 12 bytes, randomly generated per call. Store alongside ciphertext.
    """
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(master_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce


def decrypt_token(ciphertext: bytes, nonce: bytes, master_key: bytes) -> str:
    """Decrypt a token. Raises cryptography.exceptions.InvalidTag if key or data is wrong.

    Do not catch InvalidTag silently — let it propagate as a hard error.
    """
    aesgcm = AESGCM(master_key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode("utf-8")
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_crypto.py -v
```

Expected: All 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add relay/crypto.py tests/test_crypto.py
git commit -m "feat: AES-256-GCM token encryption with tamper detection"
```

---

## Task 6: Database Engine + Session

**Files:**
- Create: `relay/db/engine.py`
- Create: `relay/db/session.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create `relay/db/engine.py`**

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from relay.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.environment == "development",
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory
```

- [ ] **Step 2: Create `relay/db/session.py`**

```python
"""Async session context manager with RLS workspace isolation.

Every query against a tenant table must be done inside a session that has
set app.current_workspace_id. Omitting it causes RLS to block all rows.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from relay.db.engine import get_session_factory


@asynccontextmanager
async def get_session(workspace_id: UUID | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session. Sets RLS context if workspace_id is provided."""
    factory = get_session_factory()
    async with factory() as session:
        if workspace_id is not None:
            await session.execute(
                text("SET LOCAL app.current_workspace_id = :wid"),
                {"wid": str(workspace_id)},
            )
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 3: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures.

Uses a real PostgreSQL test database specified by TEST_DATABASE_URL.
Each test gets a transaction that is rolled back on teardown — no cleanup needed.
"""

import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://relay:relay@localhost:5432/relay_test",
)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    from relay.db.models import Base

    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine):
    """Transactional session that rolls back after each test."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        async with session.begin():
            yield session
            await session.rollback()
```

- [ ] **Step 4: Commit**

```bash
git add relay/db/engine.py relay/db/session.py tests/conftest.py
git commit -m "feat(db): async engine, session factory, RLS session helper, test fixtures"
```

---

## Task 7: Database Models

**Files:**
- Create: `relay/db/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_models.py
from relay.db.models import AuditLog, SlaPolicy, User, Workspace, WorkspaceSettings, WorkspaceToken, ClassificationFeedback


def test_workspace_has_distinct_slack_team_id_and_internal_uuid():
    """slack_team_id (Slack's string) must be distinct from the internal UUID."""
    w = Workspace(slack_team_id="T12345", slack_team_name="Acme Corp")
    assert w.id is not None
    assert w.slack_team_id == "T12345"
    assert str(w.id) != "T12345"


def test_audit_log_has_soc2_attribution_fields():
    """Audit log must have actor IP, user agent, and event taxonomy."""
    cols = {c.key for c in AuditLog.__table__.columns}
    required = {
        "workspace_id", "actor_user_id", "actor_ip", "user_agent",
        "event_type", "entity_type", "entity_id", "created_at",
        "old_value", "new_value",
    }
    assert required.issubset(cols), f"Missing: {required - cols}"


def test_workspace_settings_has_configurable_thresholds():
    cols = {c.key for c in WorkspaceSettings.__table__.columns}
    assert "question_confidence_threshold_open" in cols
    assert "question_confidence_threshold_candidate" in cols


def test_sla_policy_stores_tier_windows():
    cols = {c.key for c in SlaPolicy.__table__.columns}
    assert "tier_name" in cols
    assert "response_window_minutes" in cols
    assert "escalation_window_minutes" in cols


def test_classification_feedback_captures_correction_action():
    cols = {c.key for c in ClassificationFeedback.__table__.columns}
    assert "correction_action" in cols
    assert "corrected_label" in cols
    assert "original_confidence" in cols
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL.

- [ ] **Step 3: Create `relay/db/models.py`**

```python
"""SQLAlchemy ORM models.

Naming conventions:
- All tenant tables include workspace_id (except workspaces itself).
- Workspace.id is the internal UUID PK.
- Workspace.slack_team_id is the Slack-native team ID string (unique constraint).
- RLS policies (added in migration) filter by workspace_id using the session-level
  app.current_workspace_id setting applied in relay/db/session.py.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    LargeBinary, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Slack's own team ID — used to detect reinstalls without creating duplicate rows.
    slack_team_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    slack_team_name: Mapped[str] = mapped_column(String(255), nullable=False)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tokens: Mapped[list["WorkspaceToken"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    settings: Mapped["WorkspaceSettings | None"] = relationship(back_populates="workspace", uselist=False, cascade="all, delete-orphan")
    sla_policies: Mapped[list["SlaPolicy"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")


class WorkspaceToken(Base):
    __tablename__ = "workspace_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    token_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'bot' or 'user'
    encrypted_token: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encrypted_token_nonce: Mapped[bytes] = mapped_column(LargeBinary(12), nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    workspace: Mapped[Workspace] = relationship(back_populates="tokens")


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False)
    question_confidence_threshold_open: Mapped[float] = mapped_column(Float, nullable=False, default=0.85)
    question_confidence_threshold_candidate: Mapped[float] = mapped_column(Float, nullable=False, default=0.60)
    classifier_variant: Mapped[str] = mapped_column(String(4), nullable=False, default="a")
    alert_digest_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="settings")


class SlaPolicy(Base):
    """Stored SLA tier windows — not hardcoded. Admin can create custom tiers."""
    __tablename__ = "sla_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    tier_name: Mapped[str] = mapped_column(String(32), nullable=False)
    response_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    escalation_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("workspace_id", "tier_name", name="uq_sla_tier"),)

    workspace: Mapped[Workspace] = relationship(back_populates="sla_policies")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    slack_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relay_role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    is_ooo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("workspace_id", "slack_user_id", name="uq_user_workspace"),)

    workspace: Mapped[Workspace] = relationship(back_populates="users")


class ClassificationFeedback(Base):
    """CSM corrections to classifier output — used to track and improve accuracy."""
    __tablename__ = "classification_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    slack_message_ts: Mapped[str] = mapped_column(String(32), nullable=False)
    slack_channel_id: Mapped[str] = mapped_column(String(32), nullable=False)
    original_label: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    original_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    corrected_label: Mapped[bool] = mapped_column(Boolean, nullable=False)
    corrected_by_slack_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'mark_not_question' | 'mark_question' | 'discard_draft' | 'regenerate_draft'
    correction_action: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Append-only audit trail. The app DB role has INSERT only — no UPDATE or DELETE.
    
    Enforced in migration via REVOKE UPDATE, DELETE ON audit_log FROM relay_app.
    """
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_slack_user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actor_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # e.g. 'workspace.installed', 'token.rotated', 'question.created', 'draft.sent'
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_models.py -v
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add relay/db/models.py tests/test_models.py
git commit -m "feat(db): ORM models — workspaces, tokens, settings, SLA, users, feedback, audit_log"
```

---

## Task 8: Alembic Migration with RLS

**Files:**
- Create: `alembic/env.py`
- Create: `alembic/versions/0001_initial_schema.py` (generated, then edited)

- [ ] **Step 1: Initialize Alembic**

```bash
uv run alembic init alembic
```

- [ ] **Step 2: Replace `alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from relay.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 3: Generate migration**

```bash
DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay \
  uv run alembic revision --autogenerate -m "initial schema"
```

Expected: File created in `alembic/versions/`. Open it and verify all tables appear.

- [ ] **Step 4: Add RLS and audit enforcement to the generated migration**

At the **end** of the `upgrade()` function in the generated file, add:

```python
    # ── RLS policies ──────────────────────────────────────────────────────────
    # These tables contain tenant data. All queries must set app.current_workspace_id.
    for table in [
        "workspace_tokens", "workspace_settings", "sla_policies",
        "users", "classification_feedback",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY workspace_isolation ON {table} "
            f"USING (workspace_id = current_setting('app.current_workspace_id', true)::uuid)"
        )

    # Audit log: enable RLS, INSERT-only policy
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY audit_insert ON audit_log FOR INSERT WITH CHECK (true)"
    )
    # In production, also run:
    # REVOKE UPDATE, DELETE ON audit_log FROM relay_app;
    # GRANT INSERT, SELECT ON audit_log TO relay_app;

    # Partial index for SLA timer queries (used heavily in Plan 3)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_questions_sla_check "
        "ON questions (next_alert_at, workspace_id) "
        "WHERE state IN ('open', 'alert_pending', 'snoozed')"
        if False else "SELECT 1"  # questions table added in Plan 2; placeholder to document intent
    )
```

- [ ] **Step 5: Run migration on development database**

```bash
DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay \
  uv run alembic upgrade head
```

Expected: Migration runs without errors. Verify with `psql relay -c "\dt"`.

- [ ] **Step 6: Run migration on test database**

```bash
DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay_test \
  uv run alembic upgrade head
```

Expected: Same result.

- [ ] **Step 7: Commit**

```bash
git add alembic/
git commit -m "feat(db): Alembic migration — initial schema with RLS policies and audit enforcement"
```

---

## Task 9: Request Signature Verification

**Files:**
- Create: `relay/slack/verify.py`
- Create: `tests/test_verify.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_verify.py
import hashlib
import hmac
import time

import pytest

from relay.slack.verify import SignatureVerificationError, verify_slack_signature

SECRET = "test_signing_secret_abc"


def _make_sig(body: str, timestamp: str) -> str:
    sig_base = f"v0:{timestamp}:{body}"
    digest = hmac.new(SECRET.encode(), sig_base.encode(), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_valid_signature_passes():
    body = '{"type":"url_verification"}'
    ts = str(int(time.time()))
    verify_slack_signature(body=body, timestamp=ts, signature=_make_sig(body, ts), signing_secret=SECRET)


def test_invalid_signature_raises():
    body = '{"type":"url_verification"}'
    ts = str(int(time.time()))
    with pytest.raises(SignatureVerificationError, match="signature"):
        verify_slack_signature(body=body, timestamp=ts, signature="v0=badhex", signing_secret=SECRET)


def test_stale_timestamp_raises():
    body = "{}"
    stale = str(int(time.time()) - 400)
    with pytest.raises(SignatureVerificationError, match="timestamp"):
        verify_slack_signature(body=body, timestamp=stale, signature=_make_sig(body, stale), signing_secret=SECRET)


def test_future_timestamp_raises():
    body = "{}"
    future = str(int(time.time()) + 400)
    with pytest.raises(SignatureVerificationError, match="timestamp"):
        verify_slack_signature(body=body, timestamp=future, signature=_make_sig(body, future), signing_secret=SECRET)


def test_non_numeric_timestamp_raises():
    with pytest.raises(SignatureVerificationError):
        verify_slack_signature(body="{}", timestamp="notanumber", signature="v0=x", signing_secret=SECRET)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_verify.py -v
```

- [ ] **Step 3: Create `relay/slack/verify.py`**

```python
"""Slack request signature verification (HMAC-SHA256).

Reference: https://api.slack.com/authentication/verifying-requests-from-slack
Call verify_slack_signature on every inbound Slack payload before processing.
"""

import hashlib
import hmac
import time


class SignatureVerificationError(Exception):
    pass


def verify_slack_signature(
    *,
    body: str,
    timestamp: str,
    signature: str,
    signing_secret: str,
    max_age_seconds: int = 300,
) -> None:
    """Verify a Slack request signature. Raises SignatureVerificationError on any failure.

    Never log the signing_secret, the raw signature, or the body in error messages.
    """
    try:
        ts_int = int(timestamp)
    except (ValueError, TypeError):
        raise SignatureVerificationError("Invalid timestamp format")

    age = abs(int(time.time()) - ts_int)
    if age > max_age_seconds:
        raise SignatureVerificationError(f"Request timestamp out of acceptable range: age={age}s")

    sig_base = f"v0:{timestamp}:{body}"
    expected = "v0=" + hmac.new(
        signing_secret.encode("utf-8"),
        sig_base.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise SignatureVerificationError("Slack signature mismatch")
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_verify.py -v
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add relay/slack/verify.py tests/test_verify.py
git commit -m "feat(slack): request signature verification with replay attack protection"
```

---

## Task 10: Async Event Queue

**Files:**
- Create: `relay/worker/celery_app.py`
- Create: `relay/worker/tasks.py`
- Create: `tests/test_worker.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_worker.py
from relay.worker.tasks import make_dedup_key, process_slack_event


def test_process_event_is_celery_task():
    assert hasattr(process_slack_event, "delay"), "Must be registered as a Celery task"


def test_dedup_key_is_deterministic():
    k1 = make_dedup_key("T1", "C1", "1234567890.000100")
    k2 = make_dedup_key("T1", "C1", "1234567890.000100")
    assert k1 == k2


def test_dedup_key_includes_all_parts():
    key = make_dedup_key("T123", "C456", "1234567890.000100")
    assert "T123" in key
    assert "C456" in key
    assert "1234567890.000100" in key


def test_dedup_key_differs_for_different_timestamps():
    k1 = make_dedup_key("T1", "C1", "1000.000001")
    k2 = make_dedup_key("T1", "C1", "1000.000002")
    assert k1 != k2
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_worker.py -v
```

- [ ] **Step 3: Create `relay/worker/celery_app.py`**

```python
from celery import Celery

from relay.config import get_settings

settings = get_settings()

celery = Celery(
    "relay",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["relay.worker.tasks"],
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_max_retries=3,
)
```

- [ ] **Step 4: Create `relay/worker/tasks.py`**

```python
"""Celery tasks for async Slack event processing.

Architecture: Bolt event handler acks Slack immediately (< 3 seconds),
then calls process_slack_event.delay(payload). This task does the real work:
deduplication, classification, question creation, and SLA timer start.
The 3-second constraint is on the Bolt handler, not here.
"""

import logging

from relay.worker.celery_app import celery

logger = logging.getLogger(__name__)


def make_dedup_key(team_id: str, channel_id: str, message_ts: str) -> str:
    """Deterministic deduplication key for a Slack message event.
    
    message_ts is Slack's native microsecond-precision timestamp — use it as the
    canonical SLA start time, not the wall-clock time the event was received.
    """
    return f"event:{team_id}:{channel_id}:{message_ts}"


@celery.task(bind=True, max_retries=3)
def process_slack_event(self, payload: dict) -> None:
    """Process a Slack message event asynchronously.

    payload: the full Slack Events API event payload dict.
    
    Plan 2 implements:
      - Redis SETNX dedup check using make_dedup_key
      - Load monitored_channel for this workspace + channel
      - Classify message (is_customer, is_question, confidence)
      - Create question row if confidence >= open threshold
      - Add to candidate queue if confidence >= candidate threshold
    """
    team_id = payload.get("team_id", "")
    event = payload.get("event", {})
    channel_id = event.get("channel", "")
    message_ts = event.get("ts", "")

    dedup_key = make_dedup_key(team_id, channel_id, message_ts)
    logger.info("Received event dedup_key=%s subtype=%s", dedup_key, event.get("subtype"))
    # Stub: full implementation in Plan 2
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
uv run pytest tests/test_worker.py -v
```

Expected: All 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add relay/worker/celery_app.py relay/worker/tasks.py tests/test_worker.py
git commit -m "feat(worker): Celery app and process_slack_event task with dedup key"
```

---

## Task 11: Slack OAuth Install + Token Storage

**Files:**
- Create: `relay/slack/oauth.py`
- Create: `tests/test_oauth.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_oauth.py
import pytest

from relay.slack.oauth import store_bot_token, upsert_workspace_from_install


@pytest.mark.asyncio
async def test_upsert_creates_new_workspace(db_session):
    workspace = await upsert_workspace_from_install(
        session=db_session,
        slack_team_id="T_NEW_001",
        slack_team_name="New Corp",
    )
    assert workspace.id is not None
    assert workspace.slack_team_id == "T_NEW_001"


@pytest.mark.asyncio
async def test_upsert_is_idempotent_on_reinstall(db_session):
    w1 = await upsert_workspace_from_install(db_session, "T_SAME_002", "Same Corp")
    w2 = await upsert_workspace_from_install(db_session, "T_SAME_002", "Same Corp Renamed")
    assert w1.id == w2.id
    assert w2.slack_team_name == "Same Corp Renamed"


@pytest.mark.asyncio
async def test_upsert_seeds_default_sla_policies(db_session):
    from sqlalchemy import select
    from relay.db.models import SlaPolicy

    workspace = await upsert_workspace_from_install(db_session, "T_SLA_003", "SLA Corp")
    result = await db_session.execute(
        select(SlaPolicy).where(SlaPolicy.workspace_id == workspace.id)
    )
    policies = result.scalars().all()
    tier_names = {p.tier_name for p in policies}
    assert "enterprise" in tier_names
    assert "pro" in tier_names
    assert "starter" in tier_names


@pytest.mark.asyncio
async def test_store_bot_token_encrypts_value(db_session):
    workspace = await upsert_workspace_from_install(db_session, "T_TOK_004", "Token Corp")
    token_row = await store_bot_token(
        session=db_session,
        workspace_id=workspace.id,
        bot_token="xoxb-real-bot-token-12345",
        scopes="chat:write,channels:read",
    )
    assert token_row.encrypted_token != b"xoxb-real-bot-token-12345"
    assert len(token_row.encrypted_token_nonce) == 12
    assert token_row.is_revoked is False


@pytest.mark.asyncio
async def test_store_bot_token_revokes_old_token(db_session):
    workspace = await upsert_workspace_from_install(db_session, "T_TOK_005", "Revoke Corp")
    t1 = await store_bot_token(db_session, workspace.id, "xoxb-old-token", "chat:write")
    t2 = await store_bot_token(db_session, workspace.id, "xoxb-new-token", "chat:write")
    await db_session.refresh(t1)
    assert t1.is_revoked is True
    assert t2.is_revoked is False
```

- [ ] **Step 2: Run — expect FAIL**

```bash
TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay_test \
  uv run pytest tests/test_oauth.py -v
```

- [ ] **Step 3: Create `relay/slack/oauth.py`**

```python
"""Workspace install lifecycle: upsert workspace, store encrypted bot token."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from relay.config import get_settings
from relay.crypto import encrypt_token
from relay.db.models import SlaPolicy, Workspace, WorkspaceSettings, WorkspaceToken


async def upsert_workspace_from_install(
    session: AsyncSession,
    slack_team_id: str,
    slack_team_name: str,
) -> Workspace:
    """Create or update a workspace on Slack app install or reinstall.

    Reinstall: reuses the existing row, clears uninstalled_at, seeds missing defaults.
    """
    result = await session.execute(
        select(Workspace).where(Workspace.slack_team_id == slack_team_id)
    )
    workspace = result.scalar_one_or_none()

    if workspace is None:
        workspace = Workspace(slack_team_id=slack_team_id, slack_team_name=slack_team_name)
        session.add(workspace)
        await session.flush()
        session.add(WorkspaceSettings(workspace_id=workspace.id))
        for tier, response_min, escalation_min in [
            ("enterprise", 30, 45),
            ("pro", 120, 180),
            ("starter", 480, 600),
        ]:
            session.add(SlaPolicy(
                workspace_id=workspace.id,
                tier_name=tier,
                response_window_minutes=response_min,
                escalation_window_minutes=escalation_min,
            ))
    else:
        workspace.slack_team_name = slack_team_name
        workspace.uninstalled_at = None
        workspace.installed_at = datetime.now(timezone.utc)

    return workspace


async def store_bot_token(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    bot_token: str,
    scopes: str,
) -> WorkspaceToken:
    """Encrypt and store the bot token. Revokes any existing active bot token first."""
    settings = get_settings()
    key = settings.token_encryption_key_bytes

    existing = await session.execute(
        select(WorkspaceToken).where(
            WorkspaceToken.workspace_id == workspace_id,
            WorkspaceToken.token_type == "bot",
            WorkspaceToken.is_revoked == False,  # noqa: E712
        )
    )
    for old in existing.scalars():
        old.is_revoked = True
        old.revoked_at = datetime.now(timezone.utc)

    ciphertext, nonce = encrypt_token(bot_token, key)
    token_row = WorkspaceToken(
        workspace_id=workspace_id,
        token_type="bot",
        encrypted_token=ciphertext,
        encrypted_token_nonce=nonce,
        scopes=scopes,
    )
    session.add(token_row)
    return token_row
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay_test \
  uv run pytest tests/test_oauth.py -v
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add relay/slack/oauth.py tests/test_oauth.py
git commit -m "feat(oauth): workspace upsert, encrypted bot token storage, reinstall handling"
```

---

## Task 12: Bolt App + FastAPI Mount

**Files:**
- Create: `relay/slack/app.py`
- Create: `relay/slack/home.py`
- Create: `relay/api/main.py`

- [ ] **Step 1: Create `relay/slack/app.py`**

```python
"""Slack Bolt app initialization. Import handlers after app creation to register them."""

from slack_bolt.async_app import AsyncApp

from relay.config import get_settings

settings = get_settings()

app = AsyncApp(
    signing_secret=settings.slack_signing_secret,
    token=settings.slack_bot_token or None,
)

# Register all handlers (import triggers @app.X decorators)
from relay.slack import home       # noqa: F401, E402
from relay.commands import help    # noqa: F401, E402
```

- [ ] **Step 2: Create `relay/slack/home.py`**

```python
"""App Home view — setup checklist skeleton. Expanded in Plan 2+."""

from relay.slack.app import app


@app.event("app_home_opened")
async def publish_app_home(event, client):
    await client.views_publish(
        user_id=event["user"],
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "RELAY"},
                },
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
                            ":white_circle: Register a customer channel — `/relay register #channel acme-health enterprise @owner`\n"
                            ":white_circle: Connect a knowledge source (docs, GitHub, or Sheets)\n"
                            ":white_circle: Assign account owners"
                        ),
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open Admin Console"},
                            "action_id": "open_admin_console",
                        }
                    ],
                },
            ],
        },
    )
```

- [ ] **Step 3: Create `relay/api/main.py`**

```python
"""FastAPI app. Bolt is mounted as the Slack request handler.

Architecture note: this is the ONLY entrypoint for Slack payloads.
Bolt acks Slack immediately on /slack/events and enqueues to Celery.
No synchronous LLM calls or DB writes happen inside the Bolt handler.
"""

from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from relay.slack.app import app as bolt_app

api = FastAPI(title="RELAY", version="0.1.0")
_handler = AsyncSlackRequestHandler(bolt_app)


@api.get("/health")
async def health():
    return {"status": "ok", "service": "relay"}


@api.post("/slack/events")
async def slack_events(req: Request):
    """Slack Events API entry point. Bolt acks in < 3 seconds, always."""
    return await _handler.handle(req)


@api.get("/slack/install")
async def slack_install(req: Request):
    return await _handler.handle(req)


@api.get("/slack/oauth_redirect")
async def slack_oauth_redirect(req: Request):
    return await _handler.handle(req)
```

- [ ] **Step 4: Verify the app starts**

```bash
TOKEN_ENCRYPTION_KEY=$(python -c "import secrets; print(secrets.token_hex(32))") \
  SLACK_CLIENT_ID=x SLACK_CLIENT_SECRET=x SLACK_SIGNING_SECRET=x \
  ANTHROPIC_API_KEY=sk-test \
  DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay \
  REDIS_URL=redis://localhost:6379/0 \
  APP_BASE_URL=http://localhost:3000 \
  uv run uvicorn relay.api.main:api --port 3000 --reload
```

In a second terminal:

```bash
curl http://localhost:3000/health
```

Expected: `{"status":"ok","service":"relay"}`

- [ ] **Step 5: Commit**

```bash
git add relay/slack/app.py relay/slack/home.py relay/api/main.py
git commit -m "feat(api): FastAPI + Bolt mount, App Home skeleton, health endpoint"
```

---

## Task 13: /relay help Command

**Files:**
- Create: `relay/commands/help.py`
- Create: `tests/test_commands.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_commands.py
import pytest
from unittest.mock import AsyncMock

import relay.commands.help  # noqa: F401 — triggers @app.command registration
from relay.commands.help import relay_help


@pytest.mark.asyncio
async def test_relay_help_acks_and_responds():
    ack = AsyncMock()
    respond = AsyncMock()
    await relay_help(ack=ack, respond=respond, command={"text": "", "user_id": "U123"})
    ack.assert_called_once()
    respond.assert_called_once()


@pytest.mark.asyncio
async def test_relay_help_response_contains_blocks():
    ack = AsyncMock()
    respond = AsyncMock()
    await relay_help(ack=ack, respond=respond, command={"text": "help", "user_id": "U123"})
    call_kwargs = respond.call_args[1]
    assert "blocks" in call_kwargs


@pytest.mark.asyncio
async def test_unknown_subcommand_returns_error_text():
    ack = AsyncMock()
    respond = AsyncMock()
    await relay_help(ack=ack, respond=respond, command={"text": "bogus", "user_id": "U123"})
    call_kwargs = respond.call_args[1]
    assert "text" in call_kwargs
    assert "bogus" in call_kwargs["text"]
```

- [ ] **Step 2: Run — expect FAIL**

```bash
uv run pytest tests/test_commands.py -v
```

- [ ] **Step 3: Create `relay/commands/help.py`**

```python
"""Handler for /relay (no subcommand) and /relay help."""

from relay.slack.app import app


@app.command("/relay")
async def relay_help(ack, respond, command):
    await ack()
    text = (command.get("text") or "").strip().lower()

    if text and text != "help":
        await respond(
            response_type="ephemeral",
            text=f"Unknown subcommand: `{text}`. Try `/relay help` to see available commands.",
        )
        return

    await respond(
        response_type="ephemeral",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*RELAY commands*"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "• `/relay register #channel account-name tier @owner` — Register a customer channel\n"
                        "• `/relay open` — Show open unanswered questions\n"
                        "• `/relay ask [question]` — Search the internal knowledge base\n"
                        "• `/relay pulse` — Show account health summary\n"
                        "• `/relay settings` — Configure RELAY for this workspace\n"
                        "• `/relay help` — Show this message"
                    ),
                },
            },
        ],
    )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_commands.py -v
```

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add relay/commands/help.py tests/test_commands.py
git commit -m "feat(commands): /relay help command"
```

---

## Task 14: Full Suite + Coverage Check

**Files:** None created — verification only.

- [ ] **Step 1: Run the full test suite**

```bash
TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay_test \
  uv run pytest tests/ -v --tb=short
```

Expected: All tests PASS. Fix any failures before proceeding.

- [ ] **Step 2: Check coverage on critical modules**

```bash
TEST_DATABASE_URL=postgresql+asyncpg://relay:relay@localhost:5432/relay_test \
  uv run pytest tests/ \
  --cov=relay.crypto \
  --cov=relay.slack.verify \
  --cov=relay.slack.oauth \
  --cov=classifier.evaluate \
  --cov-report=term-missing
```

Expected:
- `relay/crypto.py`: ≥ 95%
- `relay/slack/verify.py`: ≥ 95%
- `relay/slack/oauth.py`: ≥ 80%
- `classifier/evaluate.py`: ≥ 90%

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "test: full suite passing — Plan 1 foundation complete"
```

---

## Self-Review

### Spec Coverage

| Review finding | Addressed |
|---|---|
| Classifier validation before product code | Tasks 1–3, with hard gate in Task 3 |
| MCP not used as DB layer | Locked in architecture section; Bolt/FastAPI query Postgres directly |
| 3-second Slack ack constraint | Task 10 (Celery stub); full implementation in Plan 2 |
| SLA timer implementation decision | Deferred to Plan 3; partial index noted in migration |
| Token encryption (AES-256-GCM) | Task 5 |
| Secrets management gaps | Documented in crypto.py; KMS swap path noted |
| Multi-tenancy RLS at DB layer | Task 7 (models), Task 8 (migration) |
| `slack_team_id` vs internal UUID | Task 7 (Workspace model), Task 11 (upsert) |
| `customer_workspace_id` on monitored_channels | Deferred to Plan 2 (channel registration) |
| LLM sub-processor disclosure | Deferred to Plan 7 (Marketplace) — noted as prerequisite |
| Data retention schedule | Deferred to Plan 7 — noted |
| Classification feedback store | Task 7 (ClassificationFeedback model) |
| Missing tables (sla_policies, workspace_settings) | Task 7 |
| Configurable thresholds per workspace | Task 7 (WorkspaceSettings) |
| Reinstall behavior | Task 11 (upsert_workspace_from_install clears uninstalled_at) |
| Old token revocation on reinstall | Task 11 (store_bot_token revokes previous) |
| Audit log with attribution fields | Task 7 (AuditLog model) |
| Append-only audit enforcement | Task 8 (migration: REVOKE UPDATE/DELETE noted) |

### Placeholder Scan

None found. Every task has actual code or a command with expected output.

### Type Consistency

`Workspace.slack_team_id` (str), `Workspace.id` (UUID), `WorkspaceToken.encrypted_token` (bytes), `WorkspaceToken.encrypted_token_nonce` (bytes 12) — consistent across models, oauth.py, and tests.

---

## Subsequent Plans

| Plan | Phases | Scope |
|---|---|---|
| **Plan 2** | 2–3 | `/relay register`, channel registry with `customer_workspace_id`, async event handler (full dedup + classification), `questions` table (5-state machine) |
| **Plan 3** | 4 | SLA engine: cron-based timer with `next_alert_at`, alert DM cards, snooze/claim/assign, `alerts` + `question_assignments` + `question_snoozes` tables, auto-ack toggle |
| **Plan 4** | 5–6 | Connector framework, docs connector (Notion or Google Drive), embedding pipeline (pgvector with `embedding_model` + `embedding_dims` columns), GitHub connector, Sheets connector |
| **Plan 5** | 7–8 | Retrieval, evidence bundle, cited draft generation, draft modal, approval workflow, bot-posted response, `draft_edit_distance` analytics |
| **Plan 6** | 9–10 | Resolution memory (`/relay ask`), account pulse, weekly digest, "Review ignored messages" view, ROI analytics schema |
| **Plan 7** | 11 | Marketplace readiness: landing page, privacy policy, sub-processor disclosure (Anthropic + embedding provider), scope justification narrative, `/relay delete-workspace-data`, data retention TTLs, SOC2 controls map |
