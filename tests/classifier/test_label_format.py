import json
from pathlib import Path


def test_labeled_jsonl_format():
    fixture = Path("tests/classifier/fixtures/sample_labeled.jsonl")
    assert fixture.exists()
    lines = fixture.read_text().strip().splitlines()
    assert len(lines) >= 10
    for line in lines:
        record = json.loads(line)
        assert isinstance(record["text"], str)
        assert record["text"]
        assert record["label"] in (0, 1)

