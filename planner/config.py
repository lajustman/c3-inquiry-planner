from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import ExemplarCase, PlanConfig, SourceSpec


class ConfigError(Exception):
    """Raised when a configuration file is missing required fields."""


def load_plan_config(path: Path) -> PlanConfig:
    data = json.loads(path.read_text(encoding="utf-8"))
    return parse_plan_config(data, source_name=str(path))


def parse_plan_config(data: Dict[str, Any], *, source_name: str = "<dict>") -> PlanConfig:
    try:
        title = data["title"]
        grade_band = data.get("grade_band", "6-8")
        time_box = int(data.get("time_box_minutes", 55))
        disciplines = list(data.get("disciplines", ["History", "Civics"]))
        focus_concepts = list(data.get("focus_concepts", ["Causation"]))
        anchor_context = data.get("anchor_context", "a focal case")
        transfer_context = data.get("transfer_context", "a contrasting case")
    except KeyError as exc:
        raise ConfigError(f"Missing required field {exc!s} in {source_name}") from exc

    teacher_intent = data.get("teacher_intent")
    reading_range = data.get("reading_range", "6-8")
    required_standards = list(data.get("required_standards", []))
    student_needs = dict(data.get("student_needs", {}))
    compelling_question = data.get("compelling_question")
    supporting_questions = data.get("supporting_questions")
    indicator_overrides = dict(data.get("indicator_overrides", {}))
    extend_move = data.get("extend_move")

    raw_sources = data.get("sources", [])
    if len(raw_sources) < 2:
        raise ConfigError("Configuration must include at least two sources with origin/value notes.")
    sources = normalise_sources(raw_sources)

    exemplar_entries = normalise_exemplars(data.get("exemplars", []))
    interest_prompts = list(data.get("interest_prompts", []))
    dok_overrides = dict(data.get("dok_overrides", {}))
    iteration_focus = data.get("iteration_focus")
    selected_exemplars = list(data.get("selected_exemplars", []))

    return PlanConfig(
        title=title,
        grade_band=grade_band,
        time_box_minutes=time_box,
        disciplines=disciplines,
        focus_concepts=focus_concepts,
        anchor_context=anchor_context,
        transfer_context=transfer_context,
        reading_range=reading_range,
        teacher_intent=teacher_intent,
        required_standards=required_standards,
        student_needs=student_needs,
        compelling_question=compelling_question,
        supporting_questions=supporting_questions,
        indicator_overrides=indicator_overrides,
        extend_move=extend_move,
        sources=sources,
        exemplars=exemplar_entries,
        interest_prompts=interest_prompts,
        dok_overrides=dok_overrides,
        iteration_focus=iteration_focus,
        selected_exemplars=selected_exemplars,
    )


def normalise_sources(raw_sources: List[Dict[str, Any]]) -> List[SourceSpec]:
    sources: List[SourceSpec] = []
    for idx, entry in enumerate(raw_sources, start=1):
        source_id = entry.get("id") or f"src.{idx}"
        source = SourceSpec(
            id=source_id,
            title=entry["title"],
            type=entry.get("type", "primary"),
            origin=entry.get("origin", "origin not specified"),
            value=entry.get("value", "value not specified"),
            citation=entry.get("citation"),
            url=entry.get("url"),
            reading_level=entry.get("reading_level"),
            differentiation=entry.get("differentiation"),
        )
        sources.append(source)
    return sources


def normalise_exemplars(raw_exemplars: List[Dict[str, Any]]) -> List[ExemplarCase]:
    exemplars: List[ExemplarCase] = []
    for idx, entry in enumerate(raw_exemplars, start=1):
        exemplar_id = entry.get("id") or f"exemplar.{idx}"
        exemplars.append(
            ExemplarCase(
                id=exemplar_id,
                title=entry.get("title", exemplar_id.title()),
                description=entry.get("description", ""),
                era_or_setting=entry.get("era_or_setting"),
                discipline_emphasis=entry.get("discipline_emphasis"),
            )
        )
    return exemplars
