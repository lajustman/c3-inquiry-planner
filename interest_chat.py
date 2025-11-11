#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from planner.interest import load_and_run_interest_session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Facilitate an interactive interest-based exemplar selection session."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the JSON configuration file to personalize.",
    )
    parser.add_argument(
        "--output",
        help="Path to write the updated configuration. Defaults to <config>._personalized.json",
    )
    parser.add_argument(
        "--ontology-dir",
        default="Curriculum-Ontology/c3",
        help="Directory containing the C3 ontology Turtle files (default: Curriculum-Ontology/c3)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        output_path = config_path.with_name(f"{config_path.stem}_personalized.json")

    ontology_dir = Path(args.ontology_dir).resolve()
    if not ontology_dir.exists():
        raise SystemExit(f"Ontology directory not found: {ontology_dir}")

    load_and_run_interest_session(config_path, output_path, ontology_dir)


if __name__ == "__main__":
    main()
