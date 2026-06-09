from __future__ import annotations

import subprocess
from pathlib import Path


def test_configure_manifest_accepts_url_argument():
    repo_root = Path(__file__).resolve().parents[1]
    generated = repo_root / "slack-app-manifest-generated.yaml"
    if generated.exists():
        generated.unlink()

    try:
        result = subprocess.run(
            ["bash", "scripts/configure-manifest.sh", "https://relay-test.example.com"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert generated.exists()
        contents = generated.read_text()
        assert "https://relay-test.example.com/slack/events" in contents
        assert "https://relay-test.example.com/slack/oauth_redirect" in contents
    finally:
        if generated.exists():
            generated.unlink()
