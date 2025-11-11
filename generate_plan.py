#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from planner.config import ConfigError, load_plan_config
from planner.generator import InquiryPlanner
from planner.indicators import IndicatorCatalog
from planner.synthesis import slug


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a C3 inquiry lesson plan from structured configuration."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the JSON configuration file describing the inquiry context.",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Directory root for generated artifacts (default: output).",
    )
    parser.add_argument(
        "--ontology-dir",
        default="Curriculum-Ontology/c3",
        help="Directory containing the C3 ontology Turtle files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_path = Path(args.config).resolve()
    output_root = Path(args.output_dir).resolve()
    ontology_dir = Path(args.ontology_dir).resolve()

    try:
        plan_config = load_plan_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    catalog = IndicatorCatalog.from_directory(ontology_dir)
    planner = InquiryPlanner(catalog)
    bundle = planner.build_plan(plan_config)

    plan_slug = slug(plan_config.title) or "plan"
    target_dir = output_root / plan_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    teacher_path = target_dir / "teacher_plan.md"
    student_path = target_dir / "student_sheet.md"
    graph_path = target_dir / "learning_graph.json"

    teacher_path.write_text(bundle.teacher_markdown, encoding="utf-8")
    student_path.write_text(bundle.student_markdown, encoding="utf-8")
    graph_path.write_text(json.dumps(bundle.learning_graph, indent=2), encoding="utf-8")

    print("Generated artifacts:")
    print(f" - Teacher plan: {teacher_path}")
    print(f" - Student sheet: {student_path}")
    print(f" - Learning graph: {graph_path}")


if __name__ == "__main__":
    main()
