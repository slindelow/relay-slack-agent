"""Prompt variants for Slack Connect message classification."""

import json
from dataclasses import dataclass
from typing import Any, Literal

import anthropic


@dataclass(frozen=True)
class ClassificationResult:
    is_question: bool
    confidence: float
    reasoning: str
    variant: Literal["a", "b"]


SYSTEM_A = """\
Classify a message sent by a customer in a shared Slack Connect support channel.

Respond with JSON only:
{
  "is_question": <true if the message requires a response from the support team>,
  "confidence": <float 0.0-1.0>,
  "reasoning": <one sentence>
}

A message requires a response if it asks for help/status/information, reports a bug,
requests an action, or expresses a blocker. A message does not require a response if
it is a greeting, thank-you, acknowledgment, customer-side status update, scheduling
logistics, or filler.
"""

SYSTEM_B = """\
You are a customer success operations classifier. Decide if a customer's Slack
message leaves the customer waiting on the internal team.

Respond with exactly this JSON object and nothing else:
{
  "is_question": <boolean>,
  "confidence": <float 0.0-1.0>,
  "reasoning": <string, one sentence>
}
"""


def parse_classification(raw: str, variant: Literal["a", "b"]) -> ClassificationResult:
    text = raw.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:]

    data: dict[str, Any] = json.loads(text)
    confidence = max(0.0, min(1.0, float(data["confidence"])))
    return ClassificationResult(
        is_question=bool(data["is_question"]),
        confidence=confidence,
        reasoning=str(data["reasoning"]),
        variant=variant,
    )


async def classify_message(
    text: str,
    variant: Literal["a", "b"],
    *,
    model: str = "claude-3-5-haiku-latest",
    client: anthropic.AsyncAnthropic | None = None,
) -> ClassificationResult:
    """Classify a message. Tests should pass a mocked client; evaluation uses the real API."""
    system = SYSTEM_A if variant == "a" else SYSTEM_B
    anthropic_client = client or anthropic.AsyncAnthropic()
    response = await anthropic_client.messages.create(
        model=model,
        max_tokens=256,
        system=system,
        messages=[{"role": "user", "content": f"Message:\n{text}"}],
    )
    raw = response.content[0].text
    return parse_classification(raw, variant)

