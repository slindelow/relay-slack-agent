"""Unit tests for the text chunking utility."""

import pytest

from relay.connectors.chunking import _get_encoding, chunk_text

_enc = _get_encoding()


def _token_len(text: str) -> int:
    return len(_enc.encode(text))


def test_empty_input():
    assert chunk_text("") == []


def test_whitespace_only():
    assert chunk_text("   \n\t  ") == []


def test_short_text_single_chunk():
    text = "Hello, world!"
    result = chunk_text(text, max_tokens=800)
    assert result == [text]


def test_multi_chunk():
    # Build a text that is clearly longer than 10 tokens
    word = "token "
    text = word * 30  # ~30 tokens
    result = chunk_text(text, max_tokens=10, overlap_tokens=2)
    assert len(result) > 1
    for chunk in result:
        assert _token_len(chunk) <= 10


def test_overlap_boundary():
    """Last overlap_tokens of chunk N must appear at start of chunk N+1."""
    word = "word "
    text = word * 40
    result = chunk_text(text, max_tokens=15, overlap_tokens=5)
    assert len(result) >= 2
    # The tail of chunk 0 and the head of chunk 1 should share tokens
    tail_tokens = _enc.encode(result[0])[-5:]
    head_tokens = _enc.encode(result[1])[:5]
    assert tail_tokens == head_tokens


def test_exact_max_tokens_boundary():
    """Text of exactly max_tokens produces exactly one chunk."""
    tokens = _enc.encode("a ") * 50  # 100 tokens
    text = _enc.decode(tokens[:100])
    result = chunk_text(text, max_tokens=100, overlap_tokens=10)
    assert len(result) == 1
    assert _token_len(result[0]) <= 100


@pytest.mark.parametrize(
    ("max_tokens", "overlap_tokens"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_invalid_chunk_parameters_raise(max_tokens, overlap_tokens):
    with pytest.raises(ValueError):
        chunk_text("hello world", max_tokens=max_tokens, overlap_tokens=overlap_tokens)
