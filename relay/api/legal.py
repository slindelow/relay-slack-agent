"""Legal pages — privacy policy, ToS, sub-processor disclosure (Plan 7 US-005)."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from relay.config import get_settings

router = APIRouter()

_STYLE = """
<style>
  body { font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #333; line-height: 1.6; }
  h1 { color: #1a1a2e; } h2 { color: #2c3e50; margin-top: 2em; }
  table { border-collapse: collapse; width: 100%; } td, th { border: 1px solid #ddd; padding: 8px; text-align: left; }
  th { background: #f5f5f5; }
</style>
"""


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    settings = get_settings()
    contact = settings.relay_contact_email
    html = f"""<!DOCTYPE html><html><head><title>RELAY Privacy Policy</title>{_STYLE}</head><body>
<h1>RELAY Privacy Policy</h1>
<p><em>Last updated: June 2026</em></p>

<h2>What data RELAY collects</h2>
<p>RELAY collects the following data to provide its service:</p>
<ul>
  <li><strong>Message excerpts</strong> — First 500 characters of messages in registered Slack Connect channels, used for question detection and draft generation. Retained for 90 days.</li>
  <li><strong>Question metadata</strong> — State, timestamps, SLA data, and assignment records. Retained for 1 year.</li>
  <li><strong>Customer account data</strong> — Account name, tier, ARR, renewal date, and CRM identifiers. Retained for the lifetime of the workspace.</li>
  <li><strong>Drafts and responses</strong> — Draft content, evidence bundles, and sent responses. Retained for 1 year.</li>
  <li><strong>User profile data</strong> — Slack display name, email, and role within RELAY. Retained for the lifetime of the workspace.</li>
  <li><strong>Knowledge entries</strong> — Approved response summaries used for future retrieval. Retained for 1 year.</li>
</ul>

<h2>Retention policy</h2>
<table>
  <tr><th>Data type</th><th>Retention</th></tr>
  <tr><td>Raw message excerpts</td><td>90 days</td></tr>
  <tr><td>Question metadata, events</td><td>1 year</td></tr>
  <tr><td>Drafts, responses, knowledge entries</td><td>1 year</td></tr>
  <tr><td>Audit logs</td><td>2 years</td></tr>
  <tr><td>Customer account data</td><td>Workspace lifetime</td></tr>
  <tr><td>Connector credentials (encrypted)</td><td>Until disconnected</td></tr>
</table>

<h2>Sub-processors</h2>
<p>See our <a href="/sub-processors">sub-processor list</a> for details on all third-party processors.</p>

<h2>Your rights</h2>
<p>You have the right to request deletion of your data at any time:</p>
<ul>
  <li><strong>Workspace deletion:</strong> Use <code>/relay delete-workspace-data</code> to permanently delete all data for your workspace.</li>
  <li><strong>Individual user erasure (GDPR Art. 17):</strong> Admins can request PII erasure via <code>DELETE /relay/admin/users/{{slack_user_id}}/erase</code>.</li>
</ul>

<h2>Contact</h2>
<p>For data privacy requests or DPA inquiries, contact us at <a href="mailto:{contact}">{contact}</a>.</p>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service():
    settings = get_settings()
    contact = settings.relay_contact_email
    html = f"""<!DOCTYPE html><html><head><title>RELAY Terms of Service</title>{_STYLE}</head><body>
<h1>RELAY Terms of Service</h1>
<p><em>Last updated: June 2026</em></p>

<h2>Service description</h2>
<p>RELAY is a Slack-native customer success tool that detects unanswered customer questions in Slack Connect channels, retrieves context from connected knowledge sources, drafts cited responses, and enforces SLA tracking with human approval before any response is sent.</p>

<h2>Acceptable use</h2>
<p>You agree to use RELAY only for legitimate customer success activities within your organization. You must not use RELAY to:</p>
<ul>
  <li>Send unsolicited or deceptive messages to customers.</li>
  <li>Circumvent human review of AI-drafted responses.</li>
  <li>Connect knowledge sources you do not have authorization to access.</li>
  <li>Violate Slack's Platform Policy or any applicable laws.</li>
</ul>

<h2>Liability</h2>
<p>RELAY is provided "as is." We are not liable for any direct, indirect, or consequential damages arising from use of the service. All AI-generated drafts require explicit human approval before delivery — you are responsible for reviewing and approving content before it is sent to customers.</p>

<h2>Termination</h2>
<p>Either party may terminate use of RELAY at any time. Upon uninstalling the Slack app, all workspace data will be permanently deleted within 24 hours. You may also trigger immediate deletion using <code>/relay delete-workspace-data</code>.</p>

<h2>Contact</h2>
<p>Questions? Contact us at <a href="mailto:{contact}">{contact}</a>.</p>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/sub-processors", response_class=HTMLResponse)
async def sub_processors():
    html = f"""<!DOCTYPE html><html><head><title>RELAY Sub-processors</title>{_STYLE}</head><body>
<h1>RELAY Sub-processor List</h1>
<p><em>Last updated: June 2026</em></p>
<p>RELAY uses the following third-party sub-processors:</p>

<table>
  <tr><th>Sub-processor</th><th>Service</th><th>Data sent</th><th>Region</th><th>Notes</th></tr>
  <tr>
    <td><strong>Anthropic</strong></td>
    <td>LLM inference (question classification, draft generation)</td>
    <td>Message excerpts, retrieved content snippets (no customer PII)</td>
    <td>US</td>
    <td>Zero Data Retention (ZDR) enabled; Anthropic does not train on API data</td>
  </tr>
  <tr>
    <td><strong>Voyage AI</strong> (default) or <strong>OpenAI</strong></td>
    <td>Text embeddings for semantic search</td>
    <td>Text chunks from connected knowledge sources</td>
    <td>US</td>
    <td>Configurable via EMBEDDING_PROVIDER; no training on API data</td>
  </tr>
  <tr>
    <td><strong>Cloud hosting provider</strong></td>
    <td>Infrastructure (application server, database, message queue)</td>
    <td>All application data</td>
    <td>Configured at deployment time</td>
    <td>Single-region deployment; see your deployment configuration</td>
  </tr>
  <tr>
    <td><strong>Sentry</strong> (optional)</td>
    <td>Error monitoring</td>
    <td>Stack traces, request metadata (no message content)</td>
    <td>US</td>
    <td>Only enabled when SENTRY_DSN is configured</td>
  </tr>
</table>

<p>For DPA inquiries, contact <a href="mailto:privacy@relay.app">privacy@relay.app</a>.</p>
</body></html>"""
    return HTMLResponse(content=html)
