import hashlib
import hmac
import time

import pytest

from relay.slack.verify import SignatureVerificationError, verify_slack_signature

SECRET = "test_signing_secret"


def make_sig(body: str, timestamp: str) -> str:
    sig_base = f"v0:{timestamp}:{body}"
    digest = hmac.new(SECRET.encode(), sig_base.encode(), hashlib.sha256).hexdigest()
    return f"v0={digest}"


def test_valid_signature_passes():
    body = '{"type":"url_verification"}'
    ts = str(int(time.time()))
    verify_slack_signature(body=body, timestamp=ts, signature=make_sig(body, ts), signing_secret=SECRET)


def test_invalid_signature_raises():
    with pytest.raises(SignatureVerificationError, match="signature"):
        verify_slack_signature(body="{}", timestamp=str(int(time.time())), signature="v0=bad", signing_secret=SECRET)


def test_stale_timestamp_raises():
    body = "{}"
    ts = str(int(time.time()) - 400)
    with pytest.raises(SignatureVerificationError, match="timestamp"):
        verify_slack_signature(body=body, timestamp=ts, signature=make_sig(body, ts), signing_secret=SECRET)


def test_future_timestamp_raises():
    body = "{}"
    ts = str(int(time.time()) + 400)
    with pytest.raises(SignatureVerificationError, match="timestamp"):
        verify_slack_signature(body=body, timestamp=ts, signature=make_sig(body, ts), signing_secret=SECRET)


def test_non_numeric_timestamp_raises():
    with pytest.raises(SignatureVerificationError):
        verify_slack_signature(body="{}", timestamp="not", signature="v0=x", signing_secret=SECRET)

