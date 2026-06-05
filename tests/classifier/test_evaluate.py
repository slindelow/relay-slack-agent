from classifier.classify import ClassificationResult
from classifier.evaluate import evaluate_dataset, main, precision_recall_f1, threshold_sweep


def test_perfect_predictions():
    p, r, f = precision_recall_f1([{"confidence": 0.95}, {"confidence": 0.15}], [1, 0], 0.5)
    assert p == 1.0
    assert r == 1.0
    assert f == 1.0


def test_all_false_positives_gives_zero_precision():
    p, _, _ = precision_recall_f1([{"confidence": 0.9}, {"confidence": 0.85}], [0, 0], 0.5)
    assert p == 0.0


def test_no_positives_predicted_gives_zero_recall():
    _, r, _ = precision_recall_f1([{"confidence": 0.1}, {"confidence": 0.2}], [1, 1], 0.5)
    assert r == 0.0


def test_threshold_sweep_shape():
    results = threshold_sweep([{"confidence": 0.9}, {"confidence": 0.3}], [1, 0])
    thresholds = [row["threshold"] for row in results]
    assert thresholds == sorted(thresholds)
    assert 0.60 in thresholds
    assert 0.85 in thresholds
    assert {"threshold", "precision", "recall", "f1"}.issubset(results[0])


async def test_evaluate_dataset_uses_classifier_and_prints_sweep(tmp_path, monkeypatch, capsys):
    dataset = tmp_path / "labeled.jsonl"
    dataset.write_text(
        '{"text": "Is the API down?", "label": 1}\n'
        '{"text": "Thanks!", "label": 0}\n'
    )
    calls = []

    async def fake_classify_message(text, variant, model):
        calls.append((text, variant, model))
        if "API" in text:
            return ClassificationResult(True, 0.91, "Question.", variant)
        return ClassificationResult(False, 0.12, "Acknowledgment.", variant)

    monkeypatch.setattr("classifier.evaluate.classify_message", fake_classify_message)
    await evaluate_dataset(dataset, "a", "fake-model")

    output = capsys.readouterr().out
    assert "Evaluating variant 'a'" in output
    assert "Threshold" in output
    assert calls == [
        ("Is the API down?", "a", "fake-model"),
        ("Thanks!", "a", "fake-model"),
    ]


async def test_evaluate_dataset_prints_misclassified_examples(tmp_path, monkeypatch, capsys):
    dataset = tmp_path / "labeled.jsonl"
    dataset.write_text('{"text": "Is this broken?", "label": 1}\n')

    async def fake_classify_message(text, variant, model):
        return ClassificationResult(False, 0.10, "Missed question.", variant)

    monkeypatch.setattr("classifier.evaluate.classify_message", fake_classify_message)
    await evaluate_dataset(dataset, "b", "fake-model")

    output = capsys.readouterr().out
    assert "Misclassified examples" in output
    assert "truth=1 predicted=0" in output


def test_main_parses_args_and_runs_evaluation(tmp_path, monkeypatch):
    dataset = tmp_path / "labeled.jsonl"
    dataset.write_text('{"text": "Thanks", "label": 0}\n')
    calls = []

    async def fake_evaluate_dataset(path, variant, model):
        calls.append((path, variant, model))

    monkeypatch.setattr("classifier.evaluate.evaluate_dataset", fake_evaluate_dataset)
    monkeypatch.setattr(
        "sys.argv",
        ["evaluate.py", str(dataset), "a", "--model", "fake-model"],
    )
    main()

    assert calls == [(dataset, "a", "fake-model")]
