"""Check whether an operator shell is ready for private-beta launch steps."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ENV = [
    "APP_BASE_URL",
    "DATABASE_URL",
    "REDIS_URL",
    "SLACK_CLIENT_ID",
    "SLACK_CLIENT_SECRET",
    "SLACK_SIGNING_SECRET",
    "TOKEN_ENCRYPTION_KEY",
    "ANTHROPIC_API_KEY",
    "KMS_PROVIDER",
    "KMS_KEY_ID",
]

OPTIONAL_ENV = [
    "SENTRY_DSN",
    "HUBSPOT_CLIENT_ID",
    "HUBSPOT_CLIENT_SECRET",
    "VOYAGE_API_KEY",
    "ERASURE_SECRET",
    "PRIVACY_CONTACT_EMAIL",
    "LEGAL_CONTACT_EMAIL",
]

REQUIRED_COMMANDS = ["curl", "git"]
DEPLOY_COMMANDS = ["aws", "docker"]


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    message: str
    marker: str | None = None


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"env file not found: {path}")
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _check_required_env() -> list[CheckResult]:
    results: list[CheckResult] = []
    for name in REQUIRED_ENV:
        value = _env(name)
        if not value:
            results.append(CheckResult(False, f"{name} is missing"))
            continue
        if name == "TOKEN_ENCRYPTION_KEY" and len(value) != 64:
            results.append(CheckResult(False, "TOKEN_ENCRYPTION_KEY must be 64 hex characters"))
            continue
        if name == "KMS_PROVIDER" and value != "aws":
            results.append(CheckResult(False, "KMS_PROVIDER must be aws for beta launch"))
            continue
        results.append(CheckResult(True, f"{name} is set"))
    return results


def _check_optional_env() -> list[CheckResult]:
    return [
        CheckResult(True, f"{name} {'is set' if _env(name) else 'is not set'}", None if _env(name) else "WARN")
        for name in OPTIONAL_ENV
    ]


def _check_commands(names: list[str], *, required: bool) -> list[CheckResult]:
    results: list[CheckResult] = []
    for name in names:
        exists = shutil.which(name) is not None
        ok = exists or not required
        suffix = "available" if exists else "not on PATH"
        marker = None if exists or required else "WARN"
        results.append(CheckResult(ok, f"{name} {suffix}", marker))
    return results


def _check_manifest_generated(app_base_url: str) -> CheckResult:
    manifest = REPO_ROOT / "slack-app-manifest-generated.yaml"
    if not manifest.exists():
        return CheckResult(False, "slack-app-manifest-generated.yaml is missing")
    contents = manifest.read_text()
    if app_base_url.rstrip("/") not in contents:
        return CheckResult(False, "generated Slack manifest does not include APP_BASE_URL")
    return CheckResult(True, "generated Slack manifest matches APP_BASE_URL")


def _check_health(app_base_url: str, *, timeout: int) -> CheckResult:
    url = f"{app_base_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            if response.status != 200:
                return CheckResult(False, f"/health returned HTTP {response.status}")
    except (urllib.error.URLError, TimeoutError) as exc:
        return CheckResult(False, f"/health failed: {exc}")
    if '"db":"ok"' not in body.replace(" ", "") or '"redis":"ok"' not in body.replace(" ", ""):
        return CheckResult(False, "/health did not report db=ok and redis=ok")
    return CheckResult(True, "/health reports db=ok and redis=ok")


def _check_kms_smoke() -> CheckResult:
    command = [sys.executable, str(REPO_ROOT / "scripts" / "smoke_kms.py")]
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        return CheckResult(False, f"KMS smoke failed: {message}")
    return CheckResult(True, result.stdout.strip())


def run_checks(*, live: bool, timeout: int) -> tuple[list[CheckResult], list[CheckResult]]:
    required = [
        *_check_required_env(),
        *_check_commands(REQUIRED_COMMANDS, required=True),
        *_check_commands(DEPLOY_COMMANDS, required=False),
    ]
    optional = _check_optional_env()

    app_base_url = _env("APP_BASE_URL")
    if app_base_url:
        required.append(_check_manifest_generated(app_base_url))
    if live and app_base_url:
        required.append(_check_health(app_base_url, timeout=timeout))
        required.append(_check_kms_smoke())
    return required, optional


def _print_section(title: str, results: list[CheckResult]) -> None:
    print(title)
    for result in results:
        marker = result.marker or ("PASS" if result.ok else "FAIL")
        print(f"  [{marker}] {result.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="load beta env vars from a local ignored file")
    parser.add_argument("--live", action="store_true", help="also call /health and run KMS smoke")
    parser.add_argument("--timeout", type=int, default=5, help="HTTP timeout for live checks")
    args = parser.parse_args()

    if args.env_file:
        try:
            load_env_file(args.env_file)
        except FileNotFoundError as exc:
            print(f"Preflight failed: {exc}", file=sys.stderr)
            return 1

    required, optional = run_checks(live=args.live, timeout=args.timeout)
    _print_section("Required", required)
    _print_section("Optional", optional)
    return 0 if all(result.ok for result in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
