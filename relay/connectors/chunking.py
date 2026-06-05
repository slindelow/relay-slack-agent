"""Token-aware text chunking with overlap for the embedding pipeline."""

from __future__ import annotations

_ENCODING_NAME = "cl100k_base"


class _WhitespaceEncoding:
    """Small fallback for local test/dev environments without tiktoken.

    Production installs should include tiktoken; this keeps import-time behavior
    deterministic in constrained environments.
    """

    def encode(self, text: str) -> list[str]:
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        return " ".join(tokens)


def _get_encoding():
    try:
        import tiktoken
    except ModuleNotFoundError:
        return _WhitespaceEncoding()
    return tiktoken.get_encoding(_ENCODING_NAME)


def chunk_text(
    text: str,
    max_tokens: int = 800,
    overlap_tokens: int = 100,
) -> list[str]:
    """Split text into overlapping token-bounded chunks.

    Empty or whitespace-only input returns [].
    The last chunk may be shorter than max_tokens.
    """
    if not text or not text.strip():
        return []

    enc = _get_encoding()
    tokens = enc.encode(text)

    if len(tokens) <= max_tokens:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        if end == len(tokens):
            break
        start = end - overlap_tokens

    return chunks
