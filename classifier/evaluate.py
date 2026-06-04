"""Precision/recall evaluation and threshold sweep for the question classifier."""

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Literal

from classifier.classify import classify_message


def precision_recall_f1(
    preds: list[dict[str, float]],
    true_labels: list[int],
    threshold: float,
) -> tuple[float, float, float]:
    tp = fp = fn = 0
    for pred, truth in zip(preds, true_labels, strict=True):
        predicted_positive = pred["confidence"] >= threshold
        if predicted_positive and truth == 1:
            tp += 1
        elif predicted_positive and truth == 0:
            fp += 1
        elif not predicted_positive and truth == 1:
            fn += 1

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def threshold_sweep(preds: list[dict[str, float]], true_labels: list[int]) -> list[dict[str, Any]]:
    thresholds = sorted(set([round(i * 0.05, 2) for i in range(10, 20)] + [0.60, 0.85]))
    results = []
    for threshold in thresholds:
        precision, recall, f1 = precision_recall_f1(preds, true_labels, threshold)
        results.append(
            {
                "threshold": threshold,
                "precision": precision,
                "recall": recall,
                "f1": f1,
            }
        )
    return results


async def evaluate_dataset(
    labeled_jsonl: Path,
    variant: Literal["a", "b"],
    model: str,
) -> None:
    records = [json.loads(line) for line in labeled_jsonl.read_text().splitlines() if line.strip()]
    true_labels = [int(record["label"]) for record in records]
    texts = [str(record["text"]) for record in records]

    print(f"\nEvaluating variant '{variant}' on {len(records)} examples with {model}...\n")
    results = await asyncio.gather(
        *[classify_message(text, variant=variant, model=model) for text in texts]
    )

    preds = [{"confidence": result.confidence} for result in results]
    print(f"{'Threshold':>10}  {'Precision':>10}  {'Recall':>8}  {'F1':>8}")
    for row in threshold_sweep(preds, true_labels):
        marker = ""
        if row["threshold"] == 0.85:
            marker = "  <-- candidate open threshold"
        elif row["threshold"] == 0.60:
            marker = "  <-- candidate floor threshold"
        print(
            f"{row['threshold']:>10.2f}  {row['precision']:>10.3f}  "
            f"{row['recall']:>8.3f}  {row['f1']:>8.3f}{marker}"
        )

    print("\n--- Misclassified examples at 0.85 ---")
    for index, (result, truth, text) in enumerate(zip(results, true_labels, texts, strict=True)):
        predicted = 1 if result.confidence >= 0.85 else 0
        if predicted != truth:
            print(f"[{index}] truth={truth} predicted={predicted} conf={result.confidence:.2f}")
            print(f"     text: {text[:160]}")
            print(f"     reasoning: {result.reasoning}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RELAY question classifier.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("variant", choices=["a", "b"])
    parser.add_argument("--model", default="claude-3-5-haiku-latest")
    args = parser.parse_args()

    asyncio.run(evaluate_dataset(args.dataset, args.variant, args.model))


if __name__ == "__main__":
    main()

