"""Small deterministic answer helpers for retrieval-backed RELAY responses."""

from __future__ import annotations

import re

from relay.context.contracts import ContextSource

_REPO_STRUCTURE_RE = re.compile(
    r"\b(folder structure|folder setup|repo structure|repo layout|repository structure|"
    r"directory tree|directory layout|file tree|where in (?:the )?repo|where does .* handle)\b",
    re.IGNORECASE,
)
_MULTI_CHANNEL_RE = re.compile(
    r"\b(multiple channels|many channels|several channels|manage .*channels|manual sync|manual syncing|syncing)\b",
    re.IGNORECASE,
)
_CUSTOMER_CONCERN_RE = re.compile(
    r"\b(customer'?s?|account'?s?).*\b(main|top|primary|biggest|concerns?|questions?|asking about|worried about)\b|"
    r"\b(main|top|primary|biggest)\s+(concerns?|questions?)\b",
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
    "customer_history": "Customer History",
}
_TOP_LEVEL_DESCRIPTIONS = {
    "relay": "application code, including Slack handlers, commands, context retrieval, connectors, drafting, workers, and API routes",
    "tests": "the pytest suite covering commands, Slack flows, retrieval, connectors, drafting, and security behavior",
    "docs": "architecture, deployment, beta, demo, and handoff documentation",
    "alembic": "database migrations and schema evolution",
    "scripts": "operational scripts for local startup, manifest generation, deployment checks, and smoke tests",
    "classifier": "question-classification evaluation and labeling utilities",
    "tasks": "implementation plans, status notes, and PRD task breakdowns",
    "memory": "project memory and glossary notes",
    "archive": "older plan snapshots and historical artifacts",
}


def is_repo_structure_query(query: str) -> bool:
    return bool(_REPO_STRUCTURE_RE.search(query))


def is_multi_channel_query(query: str) -> bool:
    return bool(_MULTI_CHANNEL_RE.search(query))


def is_customer_concern_query(query: str) -> bool:
    return bool(_CUSTOMER_CONCERN_RE.search(query))


def escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def terms(text: str) -> set[str]:
    return {
        term
        for term in re.findall(r"[a-z0-9_./-]+", text.lower())
        if len(term) > 1 and term not in _STOPWORDS
    }


def is_structure_source(source: ContextSource) -> bool:
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


def source_relevance_score(query: str, source: ContextSource) -> int:
    query_terms = terms(query)
    source_terms = terms(f"{source.title}\n{source.excerpt}")
    score = len(query_terms & source_terms) * 2

    title = source.title.lower()
    excerpt = source.excerpt.lower()
    repo_query = is_repo_structure_query(query)

    if repo_query:
        if is_structure_source(source):
            score += 18
        if source.provider == "github":
            score += 5
        if any(marker in title or marker in excerpt for marker in ("readme", "architecture", "docs/", "relay/")):
            score += 3
        if source.provider == "relay_memory":
            score -= 6
        if source.provider == "slack_rts":
            score -= 3
    elif is_multi_channel_query(query):
        if source.provider in {"github", "relay_memory"}:
            score += 6
        if any(marker in title or marker in excerpt for marker in ("register", "slack connect", "monitored channels", "manual sync", "sync")):
            score += 6
    elif is_customer_concern_query(query):
        if source.provider == "customer_history":
            score += 20
        if source.provider == "slack_rts":
            score += 4
    elif source.provider == "relay_memory":
        score += 2

    if source.stale:
        score -= 2
    if source.visibility == "internal":
        score -= 1
    return score


def dedupe_and_rank_sources(query: str, chunks: list[ContextSource], *, limit: int = 5) -> list[ContextSource]:
    best_by_key: dict[str, tuple[int, int, ContextSource]] = {}
    min_score = 4 if is_repo_structure_query(query) else 1

    for index, chunk in enumerate(chunks):
        key = f"{chunk.provider}:{chunk.url or chunk.title}".lower()
        score = source_relevance_score(query, chunk)
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


def extract_bullets_after_heading(excerpt: str, heading: str, *, limit: int = 8) -> list[str]:
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


def _path_like_values(text: str) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"(?<![\w.-])([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+/?)", text):
        value = match.group(1).strip().strip("`.,);:")
        if value and not value.startswith(("http://", "https://")):
            values.append(value.rstrip("/"))
    return values


def _top_level_entries_from_sources(sources: list[ContextSource]) -> list[str]:
    entries: list[str] = []
    seen: set[str] = set()
    for source in sources:
        explicit = extract_bullets_after_heading(source.excerpt, "Top-level entries:", limit=12)
        candidates = [*explicit]
        candidates.extend(path.split("/")[0] for path in _path_like_values(f"{source.title}\n{source.excerpt}"))
        for candidate in candidates:
            candidate = candidate.strip().rstrip("/")
            if not candidate or candidate.startswith(".") or candidate in seen:
                continue
            if candidate in _TOP_LEVEL_DESCRIPTIONS or "." not in candidate:
                entries.append(candidate)
                seen.add(candidate)
    return entries


def _notable_paths(sources: list[ContextSource], *, limit: int = 8) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for source in sources:
        directories = extract_bullets_after_heading(source.excerpt, "All directories:", limit=limit)
        candidates = [*directories, *_path_like_values(source.excerpt)]
        for candidate in candidates:
            path = candidate.strip().rstrip("/")
            if not path or path in seen or path.split("/")[0].startswith("."):
                continue
            if "/" in path:
                paths.append(path)
                seen.add(path)
            if len(paths) >= limit:
                return paths
    return paths


def _format_path(path: str) -> str:
    return f"`{path}`" if "." in path.rsplit("/", 1)[-1] else f"`{path}/`"


def repo_structure_answer(sources: list[ContextSource]) -> str:
    top_level = _top_level_entries_from_sources(sources)
    notable = _notable_paths(sources)

    if not top_level:
        return (
            "I found the indexed GitHub repository-structure source, but the retrieved excerpt "
            "did not include enough directory detail to summarize the layout. Re-sync GitHub "
            "from `/relay settings` so RELAY can retrieve the latest tree summary."
        )

    described = [
        f"`{entry}/` is {_TOP_LEVEL_DESCRIPTIONS[entry]}"
        for entry in top_level
        if entry in _TOP_LEVEL_DESCRIPTIONS
    ]
    unknown = [f"`{entry}/`" if "." not in entry else f"`{entry}`" for entry in top_level if entry not in _TOP_LEVEL_DESCRIPTIONS]
    parts: list[str] = []
    if described:
        parts.append("The RELAY repo is organized around " + "; ".join(described[:7]) + ".")
    if unknown:
        parts.append("Other top-level entries shown in the indexed tree include " + ", ".join(unknown[:6]) + ".")
    if notable:
        parts.append(
            "Useful subdirectories surfaced by retrieval include "
            + ", ".join(_format_path(path) for path in notable[:6])
            + "."
        )
    return " ".join(parts)


def multi_channel_answer() -> str:
    return (
        "RELAY can monitor multiple Slack Connect customer channels at the same time. "
        "Each channel is added once with `/relay add #channel Account Name tier @owner` so RELAY can map it to the right customer account and SLA policy. "
        "After a channel is registered, monitoring is event-driven: Slack sends new messages to RELAY automatically, so customer-channel monitoring does not require manual syncing. "
        "Manual sync is only for knowledge sources such as GitHub when you want to refresh indexed docs."
    )


def customer_concern_answer(sources: list[ContextSource]) -> str:
    history = [source for source in sources if source.provider == "customer_history"]
    if not history:
        return extractive_answer("", sources)
    excerpt = history[0].excerpt
    bullets = []
    for line in excerpt.splitlines():
        line = line.strip().lstrip("- ").strip()
        if line:
            bullets.append(line)
        if len(bullets) >= 5:
            break
    if not bullets:
        return "I found recent customer-channel history, but the stored excerpts were too thin to summarize confidently."
    return "Based on recent registered customer-channel messages, the customer has mainly been asking about: " + "; ".join(bullets) + "."


def extractive_answer(query: str, chunks: list[ContextSource]) -> str:
    if is_multi_channel_query(query):
        return multi_channel_answer()
    if is_customer_concern_query(query):
        return customer_concern_answer(chunks)

    if is_repo_structure_query(query):
        structure_sources = [chunk for chunk in chunks if is_structure_source(chunk) or chunk.provider == "github"]
        if structure_sources:
            return repo_structure_answer(structure_sources)

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


def provider_label(provider: str) -> str:
    return _PROVIDER_LABELS.get(provider, provider.replace("_", " ").title())


def prepared_answer_for_sources(query: str, sources: list[ContextSource]) -> str | None:
    ranked = dedupe_and_rank_sources(query, sources)
    if not ranked:
        return None
    return extractive_answer(query, ranked)
