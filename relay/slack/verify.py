"""Slack request signature verification."""

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
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError) as exc:
        raise SignatureVerificationError("Invalid timestamp format") from exc

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

