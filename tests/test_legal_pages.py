"""Tests for legal pages (Plan 7 US-005)."""

import pytest
from fastapi.testclient import TestClient


def _make_client():
    from relay.api.main import api
    return TestClient(api)


def test_privacy_returns_200_with_html():
    client = _make_client()
    resp = client.get("/privacy")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert len(body) > 100
    assert "Privacy Policy" in body
    assert "Sub-processor" in body or "sub-processor" in body


def test_terms_returns_200_with_html():
    client = _make_client()
    resp = client.get("/terms")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert len(body) > 100
    assert "Terms of Service" in body


def test_sub_processors_returns_200_with_html():
    client = _make_client()
    resp = client.get("/sub-processors")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    body = resp.text
    assert len(body) > 100
    assert "Anthropic" in body
    assert "Sentry" in body
