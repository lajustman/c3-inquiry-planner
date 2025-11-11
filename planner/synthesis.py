from __future__ import annotations

import re
from typing import Dict, List

from .models import PlanConfig


def build_learning_graph(plan_data: Dict[str, object]) -> Dict[str, object]:
    config: PlanConfig = plan_data["config"]
    indicators: Dict[str, List] = plan_data["indicators"]
    sequence: List[Dict[str, object]] = plan_data["sequence"]
    sources: List[Dict[str, object]] = plan_data["sources"]
    performance = plan_data["performance_task"]
    exemplars: List[Dict[str, object]] = plan_data.get("exemplars", [])
    dok_set: List[Dict[str, object]] = plan_data.get("dok_set", [])

    concept_nodes = []
    concept_ids = []
    for concept in config.focus_concepts:
        concept_id = f"concept.{slug(concept)}"
        concept_nodes.append(
            {
                "id": concept_id,
                "label": concept,
                "notes": f"Emphasized using {config.anchor_context} and {config.transfer_context}",
            }
        )
        concept_ids.append(concept_id)

    indicator_nodes = []
    for dimension, items in indicators.items():
        for indicator in items:
            indicator_nodes.append(
                {
                    "id": f"ind:{indicator.code}",
                    "dimension": dimension,
                    "text": indicator.label,
                }
            )

    question_block = {
        "compelling": plan_data["questions"]["compelling"],
        "supporting": plan_data["questions"]["supporting"],
    }

    source_nodes = []
    for entry in sources:
        source_nodes.append(
            {
                "id": entry["id"],
                "title": entry["title"],
                "type": entry["type"],
                "origin": entry["origin"],
                "value": entry["value"],
            }
        )

    context_nodes = []
    context_ids = []
    for exemplar in exemplars:
        context_id = f"context.{slug(exemplar['title'])}"
        context_nodes.append(
            {
                "id": context_id,
                "title": exemplar["title"],
                "role": exemplar.get("role"),
                "description": exemplar.get("description"),
            }
        )
        context_ids.append(context_id)

    tasks = []
    edges = []
    task_ids = set()

    for stage in sequence:
        task_id = f"task.{slug(stage['stage'])}"
        tasks.append(
            {
                "id": task_id,
                "stage": stage["stage"],
                "product": stage["product"],
                "prompts": stage["activities"],
                "assesses": match_indicators_for_stage(stage["stage"], indicators),
            }
        )
        task_ids.add(task_id)
        for concept_id in concept_ids:
            edges.append(
                {
                    "from": concept_id,
                    "to": task_id,
                    "type": "applies",
                }
            )

    performance_id = "task.performance"
    tasks.append(
        {
            "id": performance_id,
            "product": performance["product"],
            "stage": "Performance",
            "prompts": [performance["prompt"]],
            "assesses": [f"ind:{code}" for code in performance["assesses"]],
        }
    )
    task_ids.add(performance_id)

    for concept_id in concept_ids:
        edges.append({"from": concept_id, "to": performance_id, "type": "applies"})

    for source in sources:
        edges.append({"from": source["id"], "to": "task.investigation", "type": "supports"})
        edges.append({"from": source["id"], "to": performance_id, "type": "supports"})

    for context_id in context_ids:
        for concept_id in concept_ids:
            edges.append({"from": context_id, "to": concept_id, "type": "illustrates"})

    for task in dok_set:
        task_id = f"task.dok_{slug(task['level'])}"
        tasks.append(
            {
                "id": task_id,
                "stage": task["level"],
                "product": "; ".join(task["products"]),
                "prompts": [task["prompt"]],
                "assesses": match_indicators_for_dok(task["level"], indicators),
            }
        )
        task_ids.add(task_id)
        for concept_id in concept_ids:
            edges.append({"from": concept_id, "to": task_id, "type": "applies"})
        for context_id in context_ids:
            edges.append({"from": context_id, "to": task_id, "type": "supports"})

    for dimension, items in indicators.items():
        for indicator in items:
            ind_id = f"ind:{indicator.code}"
            targets = targets_for_dimension(dimension)
            for task_target in targets:
                if task_target in task_ids:
                    edges.append({"from": ind_id, "to": task_target, "type": "assesses"})

    rubric_nodes = []
    for row in plan_data["rubric"]:
        rubric_nodes.append(
            {
                "id": f"rubric.{slug(row['dimension'])}",
                "dimension": row["dimension"],
                "levels": [
                    row["emerging"],
                    row["developing"],
                    row["proficient"],
                    row["advanced"],
                ],
            }
        )

    graph = {
        "metadata": {
            "title": config.title,
            "grade_band": config.grade_band,
            "time_box_minutes": config.time_box_minutes,
            "discipline": config.disciplines,
        },
        "concepts": concept_nodes,
        "indicators": indicator_nodes,
        "questions": question_block,
        "sources": source_nodes,
        "tasks": tasks,
        "rubricCriteria": rubric_nodes,
        "contexts": context_nodes,
        "edges": edges,
    }
    return graph


SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    base = text.lower()
    base = SLUG_RE.sub("_", base)
    return base.strip("_") or "item"


def match_indicators_for_stage(stage: str, indicators: Dict[str, List]) -> List[str]:
    stage_lower = stage.lower()
    matches: List[str] = []
    if "orientation" in stage_lower:
        matches.extend(f"ind:{indicator.code}" for indicator in indicators.get("D1", []))
    if "independent" in stage_lower:
        matches.extend(f"ind:{indicator.code}" for indicator in indicators.get("D2", []))
        matches.extend(f"ind:{indicator.code}" for indicator in indicators.get("D3", []))
    if "mastery" in stage_lower:
        matches.extend(f"ind:{indicator.code}" for indicator in indicators.get("D3", []))
        matches.extend(f"ind:{indicator.code}" for indicator in indicators.get("D4", []))
    if "iteration" in stage_lower:
        matches.extend(f"ind:{indicator.code}" for indicator in indicators.get("D4", []))
    return list(dict.fromkeys(matches))


def match_indicators_for_dok(level: str, indicators: Dict[str, List]) -> List[str]:
    mapping = {
        "Level 1": ["D1"],
        "Level 2": ["D1", "D2", "D3"],
        "Level 3": ["D2", "D3"],
        "Level 4": ["D3", "D4"],
    }
    dims = mapping.get(level, ["D1", "D2", "D3", "D4"])
    matches: List[str] = []
    for dim in dims:
        matches.extend(f"ind:{indicator.code}" for indicator in indicators.get(dim, []))
    return list(dict.fromkeys(matches))


def targets_for_dimension(dimension: str) -> List[str]:
    mapping = {
        "D1": ["task.orientation_inquiry_setup", "task.dok_level_1"],
        "D2": ["task.independent_learning_mission", "task.dok_level_2", "task.dok_level_3"],
        "D3": [
            "task.independent_learning_mission",
            "task.mastery_check",
            "task.dok_level_2",
            "task.dok_level_3",
            "task.dok_level_4",
        ],
        "D4": [
            "task.mastery_check",
            "task.iteration_extension_planning",
            "task.performance",
            "task.dok_level_4",
        ],
    }
    return mapping.get(dimension, ["task.performance"])
