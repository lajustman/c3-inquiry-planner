from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from .config import parse_plan_config
from .generator import InquiryPlanner
from .indicators import IndicatorCatalog
from .llm import LLMUnavailable, default_llm_client
from .models import PlanConfig


DEFAULT_PROMPTS = [
    "Share one specific example of this concept from your own experience or community.",
    "Name a question you still have about this concept that we could investigate with evidence.",
]


def normalise_choice_response(raw: str, choices: List[str]) -> str:
    trimmed = raw.strip()
    if trimmed.isdigit():
        idx = int(trimmed)
        if 1 <= idx <= len(choices):
            return choices[idx - 1]
    return trimmed


def build_prompt_sequence(config: PlanConfig) -> List[Dict[str, object]]:
    focus_summary = ", ".join(config.focus_concepts) or "the concept"
    focus_lower = focus_summary.lower()
    guided_prompts: List[Dict[str, object]] = [
        {
            "id": "domain",
            "question": (
                f"Choose a type of situation where {focus_lower} might appear. "
                "Pick a number or describe your idea (connect it to the concept)."
            ),
            "choices": [
                "Community or civic action that changes rules or policies",
                "Environmental or climate challenge that needs collective response",
                "Economic trade-off or decision that affects different groups",
                "Cultural or historical moment where youth voices shaped outcomes",
                "Another idea (describe how it still highlights the concept)",
            ],
            "reminder": "Type the number of the option you like, or describe your idea in one sentence.",
        },
        {
            "id": "audience",
            "question": "Who should hear what you discover? Choose an audience or add your own.",
            "choices": [
                "Local civic leaders (school board, city council, youth commission)",
                "Peers or youth organizations who can take action with you",
                "Families and community members directly affected",
                "Online or media audience that can amplify the message",
                "Another audience (describe and explain why they matter)",
            ],
            "reminder": "Choose a number or describe your audience in a short phrase.",
        },
        {
            "id": "product",
            "question": "How would you most like to share your findings?",
            "choices": [
                "Speech or testimony with cited evidence",
                "Visual or multimedia story (poster, video, digital exhibit)",
                "Evidence-based brief or report with data visualizations",
                "Structured dialogue or workshop plan",
                "Another product (describe how it will include evidence and voices)",
            ],
            "reminder": "Pick a number or describe your product. Make sure you can still cite sources.",
        },
    ]

    custom_prompts = config.interest_prompts or DEFAULT_PROMPTS
    for idx, prompt in enumerate(custom_prompts):
        guided_prompts.append(
            {
                "id": f"custom_{idx}",
                "question": prompt,
                "choices": None,
                "reminder": f"Keep your response tied to {focus_lower}.",
            }
        )
    return guided_prompts


def map_interests_to_nodes(keywords: List[str], focus_concepts: List[str]) -> List[Dict[str, object]]:
    mapped: List[Dict[str, object]] = []
    if not keywords and not focus_concepts:
        return mapped
    lowered_keywords = [kw.lower() for kw in keywords]
    for concept in focus_concepts:
        score = 0.0
        base = concept.lower()
        if any(base in kw for kw in lowered_keywords):
            score = 0.9
        elif any(kw in base for kw in lowered_keywords):
            score = 0.75
        if score > 0:
            mapped.append({"node": concept, "confidence": score})
    if not mapped and focus_concepts:
        mapped.append({"node": focus_concepts[0], "confidence": 0.5})
    for kw in lowered_keywords:
        if kw not in {entry["node"].lower() for entry in mapped}:
            mapped.append({"node": kw, "confidence": 0.4})
    return mapped


def run_interest_session(
    config_json: Dict[str, object],
    plan_data: Dict[str, object],
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> Dict[str, object]:
    config = parse_plan_config(config_json, source_name="<interactive>")
    conversation: List[Dict[str, str]] = []
    focus_summary = ", ".join(config.focus_concepts) or "the concept"
    prompt_sequence = build_prompt_sequence(config)
    success_criteria: List[str] = plan_data.get("success_criteria", [])
    questions_data: Dict[str, object] = plan_data.get("questions", {})
    sequence: List[Dict[str, object]] = plan_data.get("sequence", [])
    dok_set: List[Dict[str, object]] = plan_data.get("dok_set", [])
    iteration_cycles: List[Dict[str, object]] = plan_data.get("iteration_cycles", [])
    interest_flow: Dict[str, object] = plan_data.get("interest_flow", {})
    prerequisite_status: Dict[str, object] = plan_data.get("prerequisite_status", {})
    learning_tiles: List[Dict[str, object]] = plan_data.get("learning_tiles", [])
    mastery_loop: Dict[str, object] = plan_data.get("mastery_loop", {})

    output_fn("=== Interest Planner ===")
    output_fn("Let's co-design additional contexts that stay anchored to our C3 indicators.\n")
    output_fn(f"Focus concepts: {focus_summary}")
    output_fn(f"Launch exemplar: {config.anchor_context}")
    output_fn(f"Transfer check exemplar: {config.transfer_context}")
    output_fn("You'll answer a few guided questions. Your choices should stay within these exemplars or those recommended by the AI assistant.")

    if success_criteria:
        output_fn("\nLearning objectives for this lesson:")
        for item in success_criteria:
            output_fn(f"- {item}")
    if questions_data:
        output_fn("\nEssential questions to consider:")
        output_fn(f"* Compelling: {questions_data.get('compelling', '')}")
        supporting = questions_data.get("supporting", [])
        if supporting:
            for sq in supporting:
                output_fn(f"* Supporting: {sq}")

    if prerequisite_status.get("primers"):
        output_fn("\nQuick primer suggestions before you dive in:")
        for primer in prerequisite_status["primers"]:
            output_fn(f"- {primer}")

    if learning_tiles:
        output_fn("\nIndependent learning tiles available:")
        for tile in learning_tiles:
            output_fn(f"- {tile['title']}: {tile['description']}")

    if mastery_loop:
        output_fn("\nMastery goal:")
        output_fn(f"- {mastery_loop.get('target', 'Reach proficiency')}")

    student_questions: List[str] = []
    output_fn("\nWhat questions do you have about this topic? (Press Enter on an empty line to continue.)")
    while True:
        question = input_fn("> ").strip()
        if not question:
            break
        student_questions.append(question)
    for question in student_questions:
        conversation.append({"prompt": "Student-generated question", "response": question})

    interest_texts: List[str] = []
    interest_texts.extend(student_questions)
    for block in prompt_sequence:
        output_fn(f"\n{block['question']}")
        choices = block.get("choices") or []
        if choices:
            for idx, choice in enumerate(choices, start=1):
                output_fn(f"  {idx}. {choice}")
        reminder = block.get("reminder")
        if reminder:
            output_fn(reminder)
        response_raw = input_fn("> ").strip()
        response = (
            normalise_choice_response(response_raw, choices) if choices else response_raw
        )
        if not response:
            response = "(no response provided)"
        conversation.append({"prompt": block["question"], "response": response})
        if response not in {"(no response provided)", ""}:
            interest_texts.append(response)

    combined = " ".join(interest_texts)
    keywords = extract_keywords(combined)

    routing_summary = map_interests_to_nodes(keywords, config.focus_concepts)
    if routing_summary:
        output_fn("\nMapped your interests to lesson concepts:")
        for entry in routing_summary:
            output_fn(f"- {entry['node']} (confidence {entry['confidence']:.2f})")

    existing_exemplars = list(config_json.get("exemplars", []))
    selected_ids: List[str] = list(dict.fromkeys(config_json.get("selected_exemplars", [])))

    llm_client = default_llm_client()
    ai_entries: List[Dict[str, object]] = []
    if llm_client:
        try:
            ideas = llm_client.suggest_exemplars(config, conversation, keywords)
            for idea in ideas:
                entry = idea.to_dict()
                entry["origin"] = "ai"
                ai_entries.append(entry)
        except LLMUnavailable as exc:
            output_fn(f"\n[AI assistant unavailable] {exc}")

    selection_catalog: List[Dict[str, object]] = []
    scored_existing = score_exemplars(existing_exemplars, keywords)
    for score, exemplar in scored_existing:
        selection_catalog.append({"entry": exemplar, "source": "existing", "score": score})
    if ai_entries:
        ai_scored = score_exemplars(ai_entries, keywords)
        for score, exemplar in ai_scored:
            selection_catalog.append({"entry": exemplar, "source": "ai", "score": score})

    selection_catalog.sort(key=lambda item: item["score"], reverse=True)
    positive_matches = [item for item in selection_catalog if item["score"] > 0]
    if positive_matches:
        selection_catalog = positive_matches[:5]
    else:
        selection_catalog = selection_catalog[:3]

    if not selection_catalog:
        output_fn("\nThere are no additional exemplars yet. Please let your teacher know if you need more options.")
    else:
        output_fn("\nHere are exemplar options and how well they match your interests:")
        for idx, item in enumerate(selection_catalog, start=1):
            exemplar = item["entry"]
            title = exemplar.get("title", f"Exemplar {idx}")
            description = exemplar.get("description", "").strip()
            detail = f" — {description}" if description else ""
            source_label = "AI suggestion" if item["source"] == "ai" else "Match"
            output_fn(
                f"  {idx}. {title}{detail} ({source_label}, score: {item['score']:.2f})"
            )

    if selection_catalog:
        choice_raw = input_fn(
            "\nSelect exemplar numbers to prioritize (comma-separated) or press Enter to keep options open.\n> "
        ).strip()
        if choice_raw.lower() not in {"", "skip"}:
            picked = parse_selection(choice_raw, len(selection_catalog))
            for idx in picked:
                item = selection_catalog[idx - 1]
                entry = item["entry"]
                if item["source"] == "ai":
                    selected_ids.extend(add_ai_exemplar(config_json, entry, output_fn))
                else:
                    exemplar_id = entry.get("id")
                    if exemplar_id:
                        selected_ids.append(exemplar_id)

    if selected_ids:
        output_fn("\nGreat! We'll feature these exemplars in the next plan:")
        for exemplar in config_json.get("exemplars", []):
            if exemplar.get("id") in selected_ids:
                output_fn(f"  - {exemplar.get('title', exemplar.get('id'))}")
        config_json["selected_exemplars"] = list(dict.fromkeys(selected_ids))
    else:
        output_fn("\nKeeping existing exemplar list without prioritization.")
        config_json.setdefault("selected_exemplars", [])

    config_json["interest_responses"] = conversation
    config_json["student_questions"] = student_questions
    config_json["prerequisite_status"] = prerequisite_status
    config_json["interest_routing"] = routing_summary
    if ai_entries:
        config_json["ai_suggestions"] = [
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "description": entry.get("description"),
                "era_or_setting": entry.get("era_or_setting"),
                "discipline_emphasis": entry.get("discipline_emphasis"),
            }
            for entry in ai_entries
        ]

    independent_stages = [stage for stage in sequence if stage.get("mode") == "independent"]
    assessment_stage = next((stage for stage in sequence if stage.get("mode") == "assessment"), None)
    iteration_stage = next((stage for stage in sequence if stage.get("mode") == "iteration"), None)

    if independent_stages:
        output_fn("\n=== Independent Learning Mission ===")
        for stage in independent_stages:
            minutes = stage.get("minutes")
            timing = f" ({minutes} min)" if minutes else ""
            output_fn(f"* {stage['stage']}{timing}: {stage['goal']}")
            for step in stage["activities"]:
                output_fn(f"  - {step}")
            output_fn(f"  - Evidence to produce: {stage['product']}")
            for resource in stage.get("resources") or []:
                if resource.get("url"):
                    output_fn(f"    • Launch: {resource['url']} ({resource.get('title')})")

    if assessment_stage or dok_set:
        output_fn("\n=== Mastery Check ===")
        if assessment_stage:
            minutes = assessment_stage.get("minutes")
            timing = f" ({minutes} min)" if minutes else ""
            output_fn(f"* {assessment_stage['stage']}{timing}: {assessment_stage['goal']}")
            for step in assessment_stage["activities"]:
                output_fn(f"  - {step}")
        for task in dok_set:
            output_fn(
                f"* {task['level']}: {task['prompt']} (Products: {', '.join(task['products'])})"
            )

    if iteration_cycles or iteration_stage or mastery_loop:
        output_fn("\n=== Iterate to Mastery ===")
        if mastery_loop:
            output_fn(f"- Target: {mastery_loop.get('target', 'Reach proficiency')}")
            if mastery_loop.get("expectation"):
                output_fn(f"- Expectation: {mastery_loop['expectation']}")
            for task in mastery_loop.get("dok_tasks", []):
                output_fn(
                    f"  - {task['level']}: {task['prompt']} (Products: {', '.join(task['products'])})"
                )
        if iteration_stage:
            output_fn(f"- {iteration_stage['goal']}")
            for step in iteration_stage["activities"]:
                output_fn(f"  - {step}")
        for cycle in iteration_cycles:
            checkpoint = cycle.get("checkpoint", {})
            check_desc = checkpoint.get("prompt", checkpoint.get("level", "Checkpoint"))
            output_fn(f"- {cycle['cycle']}: {cycle['purpose']}")
            if check_desc:
                output_fn(f"  - Checkpoint: {check_desc}")
            output_fn(f"  - Feedback: {cycle['feedback']}")
            output_fn(f"  - Next step: {cycle['next_step']}")

    return config_json


def extract_keywords(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z]{3,}", text.lower())
    seen: Dict[str, None] = {}
    for token in tokens:
        seen.setdefault(token, None)
    return list(seen.keys())


def score_exemplars(
    exemplars: List[Dict[str, object]],
    keywords: List[str],
) -> List[Tuple[float, Dict[str, object]]]:
    if not keywords:
        return [(0.0, exemplar) for exemplar in exemplars]
    scores: List[Tuple[float, Dict[str, object]]] = []
    for exemplar in exemplars:
        text = " ".join(
            str(exemplar.get(key, "")) for key in ("title", "description", "era_or_setting", "discipline_emphasis")
        ).lower()
        match_count = sum(1 for keyword in keywords if keyword in text)
        score = match_count / len(keywords)
        scores.append((score, exemplar))
    scores.sort(key=lambda item: item[0], reverse=True)
    return scores


def parse_selection(raw: str, max_index: int) -> List[int]:
    selections: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part.isdigit():
            continue
        value = int(part)
        if 1 <= value <= max_index:
            selections.append(value)
    return list(dict.fromkeys(selections))


def add_ai_exemplar(
    config_json: Dict[str, object],
    entry: Dict[str, object],
    output_fn: Callable[[str], None],
) -> List[str]:
    exemplars = config_json.setdefault("exemplars", [])
    clean_entry = {
        "id": entry.get("id") or "exemplar.ai",
        "title": entry.get("title") or "AI Suggested Exemplar",
        "description": entry.get("description") or "Generated exemplar context.",
        "era_or_setting": entry.get("era_or_setting"),
        "discipline_emphasis": entry.get("discipline_emphasis"),
    }
    clean_entry["id"] = ensure_unique_id(exemplars, clean_entry["id"])
    exemplars.append(clean_entry)
    output_fn(f"Added AI exemplar '{clean_entry['title']}'.")
    return [clean_entry["id"]]


SLUG_RE = re.compile(r"[^a-z0-9]+")


def ensure_unique_id(exemplars: List[Dict[str, object]], title: str) -> str:
    existing_ids = {ex.get("id") for ex in exemplars if ex.get("id")}
    raw = (title or "").strip().lower()
    if raw.startswith("exemplar."):
        candidate = raw
    else:
        base = SLUG_RE.sub("_", raw).strip("_") or "exemplar"
        candidate = f"exemplar.{base}"
    counter = 2
    unique = candidate
    while unique in existing_ids:
        unique = f"{candidate}_{counter}"
        counter += 1
    return unique


def load_and_run_interest_session(
    config_path: Path,
    output_path: Path,
    ontology_dir: Path,
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    config_json = json.loads(config_path.read_text(encoding="utf-8"))
    plan_config = parse_plan_config(config_json)
    catalog = IndicatorCatalog.from_directory(ontology_dir)
    planner = InquiryPlanner(catalog)
    bundle = planner.build_plan(plan_config)
    updated = run_interest_session(
        config_json,
        bundle.plan_data,
        input_fn=input_fn,
        output_fn=output_fn,
    )
    output_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    output_fn(f"\nUpdated configuration saved to {output_path}")
