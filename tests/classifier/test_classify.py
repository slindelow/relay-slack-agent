from types import SimpleNamespace

import pytest

from classifier.classify import ClassificationResult, classify_message, parse_classification


class FakeMessages:
    def __init__(self, text: str):
        self.text = text

    async def create(self, **kwargs):
        return SimpleNamespace(content=[SimpleNamespace(text=self.text)])


class FakeAnthropic:
    def __init__(self, text: str):
        self.messages = FakeMessages(text)


def test_parse_json_result():
    result = parse_classification(
        '{"is_question": true, "confidence": 0.91, "reasoning": "Asks for help."}',
        "a",
    )
    assert result == ClassificationResult(True, 0.91, "Asks for help.", "a")


@pytest.mark.asyncio
async def test_variant_a_classifies_obvious_question():
    result = await classify_message(
        "Is the API down?",
        "a",
        client=FakeAnthropic('{"is_question": true, "confidence": 0.93, "reasoning": "Reports outage."}'),
    )
    assert result.is_question is True
    assert result.variant == "a"


@pytest.mark.asyncio
async def test_variant_b_classifies_obvious_non_question():
    result = await classify_message(
        "Thanks!",
        "b",
        client=FakeAnthropic('{"is_question": false, "confidence": 0.88, "reasoning": "Acknowledgment."}'),
    )
    assert result.is_question is False
    assert result.variant == "b"

