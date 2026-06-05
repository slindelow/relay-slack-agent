#!/usr/bin/env python3
"""Interactive labeling CLI for Slack message classifier datasets."""

import argparse
import json
import sys
from pathlib import Path


def label_messages(input_path: Path, output_path: Path) -> None:
    lines = [line for line in input_path.read_text().splitlines() if line.strip()]
    print(
        f"Labeling {len(lines)} messages. Controls: 1=question, 0=not a question, s=skip, q=quit.\n"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as out:
        for index, line in enumerate(lines):
            record = json.loads(line)
            text = record.get("text", "")
            print(f"[{index + 1}/{len(lines)}] {text[:300]}")

            while True:
                key = input("  Label (1/0/s/q): ").strip().lower()
                if key == "q":
                    print("Quitting early.")
                    return
                if key == "s":
                    break
                if key in ("0", "1"):
                    out.write(json.dumps({"text": text, "label": int(key)}) + "\n")
                    out.flush()
                    break
                print("  Invalid input. Use 1, 0, s, or q.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Label Slack messages for classifier validation.")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: {args.input} not found.", file=sys.stderr)
        sys.exit(1)

    label_messages(args.input, args.output)


if __name__ == "__main__":
    main()

