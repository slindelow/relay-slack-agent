"""Handler logic for the /relay ask subcommand."""

from __future__ import annotations

import logging
import re

from sqlalchemy import select

from relay.context.contracts import ContextSource
from relay.context.service import search_indexed_knowledge, search_slack_context
from relay.context.slack_rts import slack_search_status
from relay.db.models import Workspace
from relay.db.session import get_session

logger = logging.getLogger(__name__)

# Matches "ask" followed by one-or-more spaces (with optional trailing content),
# OR a bare "ask" at end-of-string — both require a word boundary so "asking" is not touched.
_ASK_PREFIX_RE = re.compile(r"^ask(?:\s+|$)", re.IGNORECASE)
_REPO_STRUCTURE_RE = re.compile(
    r"\b(folder structure|folder setup|repo structure|repo layout|repository structure|"
    r"directory tree|directory layout|file tree|where in (?:the )?repo|where does .* handle)\b",
    re.IGNORECASE,
)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "does",
    "for",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "repo",
    "repository",
    "relay",
    "the",
    "this",
    "to",
    "what",
    "where",
    "with",
}
_PROVIDER_LABELS = {
    "github": "GitHub",
    "google_drive": "Google Drive",
    "relay_memory": "Memory",
    "slack_rts": "Slack",
}


def _parse_ask_query(text: str) -> str:
    # Apply prefix regex before stripping so trailing-space-only input ("ask ") works correctly.
    return _ASK_PREFIX_RE.sub("", text.lstrip()).strip()


def _escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _is_repo_structure_query(query: str) -> bool:
    return bool(_REPO_STRUCTURE_RE.search(query))


def _terms(text: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9_./-]+", text.lower())
        if len(term) > 1 and term not in _STOPWORDS
    }


def _is_structure_source(source: ContextSource) -> bool:
    haystack = f"{source.title}\n{source.excerpt}".lower()
    return (
        source.provider == "github"
        and (
            "repository structure" in haystack
            or "top-level entries" in haystack
            or "all directories" in haystack
            or "directory layout" in haystack
        )
    )


def _source_relevance_score(query: str, source: ContextSource) -> int:
    query_terms = _terms(query)
    source_terms = _terms(f"{source.title}\n{source.excerpt}")
    overlap = len(query_terms & source_terms)
    score = overlap * 2

    title = source.title.lower()
    excerpt = source.excerpt.lower()
    repo_query = _is_repo_structure_query(query)

    if repo_query:
        if _is_structure_source(source):
            score += 18
        if source.provider == "github":
            score += 5
        if any(marker in title or marker in excerpt for marker in ("readme", "architecture", "docs/", "relay/")):
            score += 3
        if source.provider == "relay_memory":
            score -= 6
        if source.provider == "slack_rts":
            score -= 3
    elif source.provider == "relay_memory":
        score += 2

    if source.stale:
        score -= 2
    if source.visibility == "internal":
        score -= 1
    return score


def _dedupe_and_rank_sources(query: str, chunks: list[ContextSource], *, limit: int = 5) -> list[ContextSource]:
    best_by_key: dict[str, tuple[int, int, ContextSource]] = {}
    repo_query = _is_repo_structure_query(query)
    min_score = 4 if repo_query else 1

    for index, chunk in enumerate(chunks):
        key = f"{chunk.provider}:{chunk.url or chunk.title}".lower()
        score = _source_relevance_score(query, chunk)
        if score < min_score:
            continue
        existing = best_by_key.get(key)
        if existing is None or score > existing[0]:
            best_by_key[key] = (score, index, chunk)

    ranked = sorted(
        best_by_key.values(),
        key=lambda item: (
            -item[0],
            0 if item[2].provider == "github" else 1,
            item[1],
        ),
    )
    return [chunk for _, _, chunk in ranked[:limit]]


def _extract_bullets_after_heading(excerpt: str, heading: str, *, limit: int = 8) -> list[str]:
    lines = excerpt.splitlines()
    bullets: list[str] = []
    in_section = False
    for raw_line in lines:
        line = raw_line.strip()
        if line.lower().rstrip(":") == heading.lower().rstrip(":"):
            in_section = True
            continue
        if in_section and line and not line.startswith("- "):
            if bullets:
                break
            continue
        if in_section and line.startswith("- "):
            value = line[2:].strip().rstrip("/")
            if value:
                bullets.append(value)
        if len(bullets) >= limit:
            break
    return bullets


def _repo_structure_answer(source: ContextSource) -> str:
    top_level = _extract_bullets_after_heading(source.excerpt, "Top-level entries:", limit=10)
    directories = _extract_bullets_after_heading(source.excerpt, "All directories:", limit=12)
    if top_level:
        top_level_text = ", ".join(f"`{entry}/`" if "." not in entry else f"`{entry}`" for entry in top_level)
        answer = f"The RELAY repo is organized around these top-level entries: {top_level_text}."
    else:
        answer = "The RELAY repo structure is captured in the indexed GitHub repository tree."
    if directories:
        dirs_text = ", ".join(f"`{directory}/`" for directory in directories[:8])
        answer += f" Key directories include {dirs_text}."
    return answer


def _extractive_answer(query: str, chunks: list[ContextSource]) -> str:
    repo_query = _is_repo_structure_query(query)
    if repo_query:
        structure_source = next((chunk for chunk in chunks if _is_structure_source(chunk)), None)
        if structure_source is not None:
            return _repo_structure_answer(structure_source)

    sentences: list[str] = []
    seen: set[str] = set()
    for chunk in chunks[:3]:
        normalized_excerpt = re.sub(r"\s+", " ", chunk.excerpt).strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized_excerpt):
            sentence = sentence.strip(" -")
            if len(sentence) < 25:
                continue
            key = sentence.lower()
            if key in seen:
                continue
            seen.add(key)
            sentences.append(sentence)
            break
        if len(sentences) >= 3:
            break

    if not sentences:
        titles = [chunk.title for chunk in chunks[:3] if chunk.title]
        if titles:
            return "I found relevant RELAY context in " + ", ".join(titles) + "."
        return "I found relevant RELAY context, but the retrieved excerpts were too thin to summarize confidently."
    return " ".join(sentences)


def _provider_label(provider: str) -> str:
    return _PROVIDER_LABELS.get(provider, provider.replace("_", " ").title())


def _citation_line(index: int, chunk: ContextSource) -> str:
    title = _escape_mrkdwn(chunk.title or "Retrieved source")
    if chunk.url and chunk.url.startswith("https://"):
        title_text = f"<{chunk.url}|{title}>"
    else:
        title_text = title
    return f"{index}. {title_text} ({_provider_label(chunk.provider)})"


def _format_result_blocks(
    query: str,
    chunks: list[ContextSource],
    *,
    slack_search_connected: bool = True,
) -> list[dict]:
    ranked_chunks = _dedupe_and_rank_sources(query, chunks)
    if not ranked_chunks:
        return []
    answer = _escape_mrkdwn(_extractive_answer(query, ranked_chunks))
    citation_lines = [_citation_line(index, chunk) for index, chunk in enumerate(ranked_chunks[:3], start=1)]

    blocks: list[dict] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Answer*\n{answer}"}},
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Citations*\n" + "\n".join(citation_lines)},
        },
    ]
    if not slack_search_connected:
        blocks.append(
            {
                "type": "context",
                "elements": [{
                    "type": "mrkdwn",
                    "text": "Connect Slack Search in `/relay settings` to include internal Slack context.",
                }],
            }
        )

    return blocks


async def handle_ask(ack, respond, command) -> None:
    """Handle `/relay ask <question>` without creating workflow records."""
    await ack()

    query = _parse_ask_query(command.get("text") or "")
    if not query:
        await respond(response_type="ephemeral", text="Usage: /relay ask <your question>")
        return

    slack_team_id = command.get("team_id")
    if not slack_team_id:
        await respond(response_type="ephemeral", text="Unable to ask: missing Slack workspace id.")
        return

    try:
        async with get_session() as session:
            workspace_result = await session.execute(
                select(Workspace).where(Workspace.slack_team_id == slack_team_id)
            )
            workspace = workspace_result.scalar_one_or_none()
            if workspace is None:
                await respond(response_type="ephemeral", text="RELAY is not installed for this workspace yet.")
                return

        async with get_session(workspace_id=workspace.id) as session:
            status = await slack_search_status(
                session,
                workspace_id=workspace.id,
                slack_user_id=command.get("user_id", ""),
            )
            indexed_chunks = await search_indexed_knowledge(
                workspace.id,
                query,
                session,
                top_k=8 if _is_repo_structure_query(query) else 5,
                actor_slack_user_id=command.get("user_id", ""),
            )
            slack_chunks = await search_slack_context(
                workspace.id,
                command.get("user_id", ""),
                query,
                session,
                top_k=5,
            )
            chunks = _dedupe_and_rank_sources(query, [*indexed_chunks, *slack_chunks])
            slack_search_connected = status.connected
    except Exception as exc:
        logger.exception("ask_failed team=%s", slack_team_id)
        await respond(response_type="ephemeral", text=f"Ask failed: {type(exc).__name__}")
        return

    if not chunks:
        text = "No relevant sources found in connected knowledge base."
        if not slack_search_connected:
            text += " Connect Slack Search in `/relay settings` to include internal Slack context."
        await respond(response_type="ephemeral", text=text)
        return

    await respond(
        response_type="ephemeral",
        blocks=_format_result_blocks(query, chunks, slack_search_connected=slack_search_connected),
    )
