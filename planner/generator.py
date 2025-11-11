from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List

from .indicators import IndicatorCatalog
from .models import Indicator, PlanBundle, PlanConfig
from .renderer import render_student_sheet, render_teacher_plan
from .synthesis import build_learning_graph


class InquiryPlanner:
    """High-level coordinator that assembles plan artifacts from configuration data."""

    def __init__(self, catalog: IndicatorCatalog) -> None:
        self.catalog = catalog

    def build_plan(self, config: PlanConfig) -> PlanBundle:
        plan_data = self._assemble_plan_data(config)
        teacher_markdown = render_teacher_plan(plan_data)
        student_markdown = render_student_sheet(plan_data)
        learning_graph = build_learning_graph(plan_data)
        return PlanBundle(
            teacher_markdown=teacher_markdown,
            student_markdown=student_markdown,
            learning_graph=learning_graph,
            plan_data=plan_data,
        )

    def _assemble_plan_data(self, config: PlanConfig) -> Dict[str, object]:
        questions = self._compile_questions(config)
        indicators = self._select_indicators(config)
        stage_minutes = allocate_minutes(config.time_box_minutes)
        sequence = build_sequence(config, questions, stage_minutes)
        performance_task = build_performance_task(config, indicators, sequence)
        rubric = build_rubric(config, performance_task)
        differentiation = build_differentiation(config)
        success_criteria = derive_success_criteria(config, performance_task)
        source_entries = build_source_entries(config)
        exemplars = build_exemplar_playlist(config)
        dok_set = build_dok_assessment(config, exemplars)
        iteration_cycles = build_iteration_cycles(config, dok_set)
        interest_flow = build_interest_flow(config, exemplars)
        prerequisite_status = run_prerequisite_check(config, indicators)
        learning_tiles = build_learning_tiles(config, source_entries, exemplars, prerequisite_status)
        mastery_loop = build_mastery_loop(config, dok_set, rubric)
        return {
            "config": config,
            "metadata": {
                "title": config.title,
                "grade_band": config.grade_band,
                "time_box_minutes": config.time_box_minutes,
                "disciplines": config.disciplines,
                "focus_concepts": config.focus_concepts,
                "anchor_context": config.anchor_context,
                "transfer_context": config.transfer_context,
                "reading_range": config.reading_range,
                "teacher_intent": config.teacher_intent,
                "required_standards": config.required_standards,
            },
            "questions": questions,
            "indicators": indicators,
            "sequence": sequence,
            "performance_task": performance_task,
            "rubric": rubric,
            "differentiation": differentiation,
            "success_criteria": success_criteria,
            "sources": source_entries,
            "exemplars": exemplars,
            "dok_set": dok_set,
            "iteration_cycles": iteration_cycles,
            "interest_flow": interest_flow,
            "prerequisite_status": prerequisite_status,
            "learning_tiles": learning_tiles,
            "mastery_loop": mastery_loop,
        }

    def _compile_questions(self, config: PlanConfig) -> Dict[str, object]:
        compelling = config.compelling_question
        focus_concept = config.focus_concepts[0] if config.focus_concepts else "Concept"
        anchor = config.anchor_context
        transfer = config.transfer_context
        if not compelling:
            compelling = f"How does {focus_concept.lower()} shape events like {anchor}?"
        supporting = list(config.supporting_questions or [])
        if not supporting:
            supporting = [
                f"What prior conditions set up {anchor}?",
                f"Whose perspectives reveal how {focus_concept.lower()} operated in this case?",
                f"Which evidence helps distinguish {focus_concept.lower()} from coincidence in {anchor}?",
                f"In what ways does {transfer} show a similar or different pattern of {focus_concept.lower()}?",
            ]
        return {
            "compelling": compelling,
            "supporting": supporting[:5],
        }

    def _select_indicators(self, config: PlanConfig) -> Dict[str, List[Indicator]]:
        selected: Dict[str, List[Indicator]] = {"D1": [], "D2": [], "D3": [], "D4": []}
        for dimension in selected.keys():
            override_codes = config.indicator_overrides.get(dimension, [])
            if override_codes:
                selected[dimension] = self.catalog.by_codes(override_codes)

        if not selected["D1"]:
            selected["D1"] = self.catalog.by_dimension(
                "D1", grade_band=config.grade_band
            )[:2]

        if not selected["D2"]:
            d2_inds: List[Indicator] = []
            for discipline in config.disciplines:
                indicator = self.catalog.find_first(
                    "D2",
                    config.grade_band,
                    discipline=discipline,
                    concept=config.focus_concepts[0] if config.focus_concepts else None,
                )
                if indicator:
                    d2_inds.append(indicator)
            if not d2_inds:
                d2_inds = self.catalog.by_dimension("D2", grade_band=config.grade_band)[:2]
            selected["D2"] = unique_by_code(d2_inds)

        if not selected["D3"]:
            selected["D3"] = self.catalog.by_dimension(
                "D3", grade_band=config.grade_band
            )[:2]

        if not selected["D4"]:
            selected["D4"] = self.catalog.by_dimension(
                "D4", grade_band=config.grade_band
            )[:2]

        return selected


def allocate_minutes(total: int) -> Dict[str, int]:
    ratios = {
        "Orientation": 0.18,
        "Independent Learning": 0.55,
        "Mastery Check": 0.27,
    }
    allocated: Dict[str, int] = {}
    remaining = total
    stages = list(ratios.items())
    for idx, (stage, ratio) in enumerate(stages):
        if idx == len(stages) - 1:
            minutes = remaining
        else:
            minutes = max(5, int(round(total * ratio)))
            remaining -= minutes
        allocated[stage] = minutes
    return allocated


def build_sequence(
    config: PlanConfig,
    questions: Dict[str, object],
    stage_minutes: Dict[str, int],
) -> List[Dict[str, object]]:
    focus = config.focus_concepts[0] if config.focus_concepts else "Concept"
    anchor = config.anchor_context
    transfer = config.transfer_context
    success_focus = config.iteration_focus or f"Apply {focus.lower()} independently."
    sequence: List[Dict[str, object]] = []
    orientation_steps = [
        "Review the learning objectives and success criteria in student-friendly language.",
        f"Read the compelling question aloud: \"{questions['compelling']}\".",
        "Generate at least two of your own questions about the topic and record them.",
    ]
    sequence.append(
        {
            "stage": "Orientation & Inquiry Setup",
            "mode": "orientation",
            "minutes": stage_minutes.get("Orientation", 8),
            "goal": "Ensure learners understand the objectives and essential questions before diving into sources.",
            "activities": orientation_steps,
            "product": "Personal inquiry notes (objectives + student-generated questions)",
        }
    )
    independent_steps = [
        "Work independently through the curated sources, annotating for causes, perspectives, and consequences.",
        "Use a graphic organizer to track origin, purpose, and corroborative value for each source.",
        f"Draft a claim that connects {focus.lower()} to {anchor}, citing at least two pieces of evidence.",
    ]
    resources: List[Dict[str, object]] = []
    for source in config.sources:
        if source.url:
            resources.append(
                {
                    "title": source.title,
                    "type": source.type,
                    "url": source.url,
                    "instructions": f"Review this source for evidence about {focus.lower()}",
                }
            )
    sequence.append(
        {
            "stage": "Independent Learning Mission",
            "mode": "independent",
            "minutes": stage_minutes.get("Independent Learning", 30),
            "goal": f"Independently investigate sources to trace {focus.lower()} across contexts.",
            "activities": independent_steps,
            "product": "Independent evidence log and draft claim",
            "resources": resources,
        }
    )
    mastery_steps = [
        f"Complete the mastery check by comparing {anchor} with {transfer}, citing one similarity and one difference.",
        "Respond to the DOK challenges provided, citing evidence for each prompt.",
    ]
    sequence.append(
        {
            "stage": "Mastery Check",
            "mode": "assessment",
            "minutes": stage_minutes.get("Mastery Check", 15),
            "goal": "Demonstrate mastery of the concept through evidence-based responses.",
            "activities": mastery_steps,
            "product": "Mastery check submission (quick write or performance task segment)",
        }
    )
    if config.extend_move or success_focus:
        iteration_steps = [
            f"Review feedback and identify one indicator to strengthen. {success_focus}",
        ]
        if config.extend_move:
            iteration_steps.append(config.extend_move)
        sequence.append(
            {
                "stage": "Iteration & Extension Planning",
                "mode": "iteration",
                "minutes": 0,
                "goal": "Plan next steps to reach mastery and optional informed action.",
                "activities": iteration_steps,
                "product": "Iteration goal tracker or action outline",
            }
        )
    return sequence


def build_performance_task(
    config: PlanConfig,
    indicators: Dict[str, List[Indicator]],
    sequence: List[Dict[str, object]],
) -> Dict[str, object]:
    audience = "city youth advisory council" if "Civics" in config.disciplines else "community history podcast audience"
    product = "Two-voice evidence brief" if "Civics" in config.disciplines else "Analytical claim brief"
    prompt = (
        f"Compose a {product.lower()} that answers the compelling question by citing at least two sources, "
        f"addressing a counterclaim, and recommending how insights from {config.anchor_context} "
        f"could inform responses to {config.transfer_context}."
    )
    assessed = [indicator.code for inds in indicators.values() for indicator in inds]
    return {
        "product": product,
        "audience": audience,
        "prompt": prompt,
        "assesses": assessed,
    }


def build_rubric(config: PlanConfig, performance_task: Dict[str, object]) -> List[Dict[str, object]]:
    focus = config.focus_concepts[0] if config.focus_concepts else "the concept"
    anchor = config.anchor_context
    transfer = config.transfer_context
    return [
        {
            "dimension": "D1 Questions",
            "emerging": "Lists topic facts without forming questions.",
            "developing": "Distinguishes between compelling and supporting questions with guidance.",
            "proficient": f"Frames compelling and supporting questions that target {focus.lower()} in {anchor}.",
            "advanced": f"Refines questions during the inquiry and anticipates evidence needed about {focus.lower()}.",
        },
        {
            "dimension": "D2 Concepts/Tools",
            "emerging": "Names disciplinary terms with limited connection to evidence.",
            "developing": f"Uses a disciplinary tool with scaffolds to analyze {anchor}.",
            "proficient": f"Selects appropriate disciplinary tools to explain how {focus.lower()} operated in {anchor}.",
            "advanced": f"Applies multiple tools flexibly and evaluates their limits when comparing to {transfer}.",
        },
        {
            "dimension": "D3 Evidence",
            "emerging": "Cites one source or includes unsupported claims.",
            "developing": "Cites multiple sources with basic relevance noted.",
            "proficient": "Corroborates sources, explains origin/authority, and selects evidence for claims and counterclaims.",
            "advanced": f"Weighs competing evidence, notes gaps, and explains implications for understanding {focus.lower()}.",
        },
        {
            "dimension": "D4 Communicate/Act",
            "emerging": "States a conclusion for a general classroom audience.",
            "developing": "Explains reasoning for the class with limited attention to audience needs.",
            "proficient": f"Tailors the {performance_task['product'].lower()} to the {performance_task['audience']}, addressing counterclaims.",
            "advanced": f"Proposes feasible next steps that adapt insights from {anchor} to {transfer}.",
        },
    ]


def build_differentiation(config: PlanConfig) -> Dict[str, List[str]]:
    supports: Dict[str, List[str]] = {
        "Language": [
            "Provide sentence starters for citing sources (e.g., 'According to Source A...').",
            "Offer vocabulary cards with visuals for key concepts and roles.",
        ],
        "Reading": [
            "Offer leveled summaries or audio versions of lengthy sources without removing core evidence.",
            "Use a graphic organizer that prompts for origin, purpose, and value of each source.",
        ],
        "Processing": [
            "Chunk investigation tasks with timed checkpoints and color-coded roles.",
            "Allow think time before discussions and capture ideas on shared boards.",
        ],
        "Extension": [
            f"Invite students to connect {config.anchor_context} to a community case they research independently.",
            "Provide optional datasets or articles that extend the comparison context.",
        ],
    }
    for key, custom in config.student_needs.items():
        label = key.capitalize()
        supports.setdefault(label, [])
        supports[label].append(custom)
    return supports


def build_source_entries(config: PlanConfig) -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    focus = config.focus_concepts[0] if config.focus_concepts else "the concept"
    for source in config.sources:
        data = asdict(source)
        prompt = (
            f"Extract a quotation or detail that illustrates {focus.lower()} and note why this source is credible "
            f"based on its origin ({source.origin}). Compare it with another source to confirm or challenge the claim."
        )
        data["prompt"] = prompt
        entries.append(data)
    return entries


def build_exemplar_playlist(config: PlanConfig) -> List[Dict[str, object]]:
    focus = config.focus_concepts[0] if config.focus_concepts else "Inquiry Concept"
    playlist: List[Dict[str, object]] = []
    selected_ids = set(config.selected_exemplars)
    playlist.append(
        {
            "id": "exemplar.anchor",
            "title": config.anchor_context,
            "role": "Launch anchor",
            "description": f"Core case used to surface prior knowledge and introduce how {focus.lower()} operates.",
            "discipline_emphasis": ", ".join(config.disciplines),
        }
    )
    playlist.append(
        {
            "id": "exemplar.transfer",
            "title": config.transfer_context,
            "role": "Transfer check",
            "description": f"Parallel context to verify that students can trace {focus.lower()} beyond the initial case.",
            "discipline_emphasis": ", ".join(config.disciplines),
        }
    )
    selected_entries: List[Dict[str, object]] = []
    optional_entries: List[Dict[str, object]] = []
    for exemplar in config.exemplars:
        entry = {
            "id": exemplar.id,
            "title": exemplar.title,
            "role": "Choice-driven exemplar",
            "description": exemplar.description or "Additional context supplied by teacher or students.",
            "discipline_emphasis": exemplar.discipline_emphasis or ", ".join(config.disciplines),
            "era_or_setting": exemplar.era_or_setting,
            "selected": False,
        }
        if exemplar.id in selected_ids:
            entry["role"] = "Student-selected exemplar"
            entry["selected"] = True
            selected_entries.append(entry)
        else:
            optional_entries.append(entry)
    playlist.extend(selected_entries)
    playlist.extend(optional_entries)
    return playlist


def build_dok_assessment(
    config: PlanConfig,
    exemplars: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    focus = config.focus_concepts[0] if config.focus_concepts else "the concept"
    anchor = exemplars[0]["title"] if exemplars else config.anchor_context
    transfer = exemplars[1]["title"] if len(exemplars) > 1 else config.transfer_context
    choice = exemplars[2]["title"] if len(exemplars) > 2 else config.transfer_context
    default_tasks = {
        "Level 1": f"Identify one concrete example of {focus.lower()} in {anchor} and cite the line or detail that proves it.",
        "Level 2": f"Compare how {focus.lower()} appears in {anchor} and {transfer}. Explain one similarity and one difference.",
        "Level 3": f"Evaluate two sources that disagree about the strength of {focus.lower()} in {anchor}. Decide which is more convincing and why.",
        "Level 4": f"Design a plan to investigate {focus.lower()} in a context of your choosing (for example, {choice}). Outline the questions, evidence needed, and how findings could inform action.",
    }
    tasks: List[Dict[str, object]] = []
    for level in ("Level 1", "Level 2", "Level 3", "Level 4"):
        prompt = config.dok_overrides.get(level, default_tasks[level])
        tasks.append(
            {
                "level": level,
                "prompt": prompt,
                "products": suggest_products_for_dok(level),
                "supports": suggest_scaffolds_for_dok(level),
            }
        )
    return tasks


def suggest_products_for_dok(level: str) -> List[str]:
    mapping = {
        "Level 1": ["Annotated excerpt", "Quick oral check-in"],
        "Level 2": ["Venn diagram with citations", "Concept map caption"],
        "Level 3": ["Evidence-based argumentative paragraph", "Socratic seminar summary notes"],
        "Level 4": ["Inquiry proposal", "Action brief or multimedia presentation"],
    }
    return mapping.get(level, ["Student choice product"])


def suggest_scaffolds_for_dok(level: str) -> List[str]:
    mapping = {
        "Level 1": ["Provide sentence frames for citing evidence.", "Offer highlighted text for key details."],
        "Level 2": ["Use a compare/contrast organizer with guiding questions.", "Model think-aloud for noting similarities."],
        "Level 3": ["Give criteria checklist for evaluating credibility.", "Facilitate peer review of claims and counterclaims."],
        "Level 4": ["Conference on research plan milestones.", "Provide timeline template for extended inquiry."],
    }
    return mapping.get(level, ["Co-develop success criteria with students."])


def build_iteration_cycles(
    config: PlanConfig,
    dok_set: List[Dict[str, object]],
) -> List[Dict[str, object]]:
    focus = config.focus_concepts[0] if config.focus_concepts else "the concept"
    iteration_focus = config.iteration_focus or f"Move learners toward independent application of {focus.lower()}."
    cycles: List[Dict[str, object]] = []
    cycles.append(
        {
            "cycle": "Discover",
            "purpose": "Surface prior knowledge and identify misconceptions.",
            "checkpoint": dok_set[0] if dok_set else {"level": "Level 1"},
            "feedback": "Immediate oral feedback; invite students to request clarifications.",
            "next_step": "Group mini-lesson or modeling targeting misconceptions.",
        }
    )
    cycles.append(
        {
            "cycle": "Develop",
            "purpose": "Practice applying the concept with structured support.",
            "checkpoint": dok_set[1] if len(dok_set) > 1 else {"level": "Level 2"},
            "feedback": "Provide annotated exemplars and success criteria tied to rubric.",
            "next_step": "Students choose an exemplar case to rework using feedback.",
        }
    )
    cycles.append(
        {
            "cycle": "Deepen",
            "purpose": "Engage in strategic reasoning and collaborative critique.",
            "checkpoint": dok_set[2] if len(dok_set) > 2 else {"level": "Level 3"},
            "feedback": "Structured peer review plus teacher conferencing.",
            "next_step": "Adjust claims/counterclaims; prepare for performance task.",
        }
    )
    cycles.append(
        {
            "cycle": "Transfer",
            "purpose": iteration_focus,
            "checkpoint": dok_set[3] if len(dok_set) > 3 else {"level": "Level 4"},
            "feedback": "Rubric-aligned commentary focusing on independence and audience awareness.",
            "next_step": "Students set personal goals or action steps; optional reteach path for targeted indicators.",
        }
    )
    return cycles


def build_interest_flow(
    config: PlanConfig,
    exemplars: List[Dict[str, object]],
) -> Dict[str, object]:
    prompts = config.interest_prompts or [
        "What communities, time periods, or issues make you curious right now?",
        "Where have you seen similar ideas or challenges outside of class?",
        "Who might be impacted if this concept showed up in your world?",
    ]
    exemplar_titles = [ex["title"] for ex in exemplars]
    selected_titles = [ex["title"] for ex in exemplars if ex.get("selected")]
    return {
        "conversation_prompts": prompts,
        "routing_logic": [
            "Map student interest keywords to available exemplars or create a new mini-case using the same indicators.",
            "Ensure each student selects at least one exemplar beyond the anchor to analyze for transfer.",
            "Save AI-chat summaries as evidence of question refinement aligned to D1 indicators.",
        ],
        "current_exemplars": exemplar_titles,
        "student_selected_exemplars": selected_titles,
        "routing_summary": [],
    }


def build_mastery_loop(
    config: PlanConfig,
    dok_set: List[Dict[str, object]],
    rubric: List[Dict[str, object]],
) -> Dict[str, object]:
    rubric_map = {row["dimension"]: row for row in rubric}
    target_statement = rubric_map.get("D3 Evidence", {}).get(
        "proficient",
        "Corroborate evidence with origin/authority explanations.",
    )
    loop_tasks = []
    for task in dok_set:
        loop_tasks.append(
            {
                "level": task["level"],
                "prompt": task["prompt"],
                "products": task["products"],
                "supports": task["supports"],
            }
        )
    return {
        "target": target_statement,
        "expectation": "Repeat mastery checks until the rubric shows 'Proficient' or higher for each dimension.",
        "dok_tasks": loop_tasks,
    }


def run_prerequisite_check(
    config: PlanConfig,
    indicators: Dict[str, List[Indicator]],
) -> Dict[str, object]:
    primer_notes: List[str] = []
    for key, note in config.student_needs.items():
        if any(trigger in key.lower() for trigger in ("prereq", "primer", "background")):
            primer_notes.append(note)

    status = "clear" if not primer_notes else "primer_recommended"
    indicator_codes = [indicator.code for inds in indicators.values() for indicator in inds]
    return {
        "status": status,
        "primers": primer_notes,
        "indicators": indicator_codes,
    }


def build_learning_tiles(
    config: PlanConfig,
    sources: List[Dict[str, object]],
    exemplars: List[Dict[str, object]],
    prerequisite_status: Dict[str, object],
) -> List[Dict[str, object]]:
    focus = ", ".join(config.focus_concepts) or "Key concept"
    tiles: List[Dict[str, object]] = []

    concept_resources: List[Dict[str, object]] = []
    if exemplars:
        concept_resources.append(
            {
                "title": exemplars[0]["title"],
                "instructions": f"Review how {focus.lower()} shows up in this anchor case.",
                "url": None,
            }
        )

    tiles.append(
        {
            "id": "tile.concept",
            "title": "Concept Mini-Lesson",
            "kind": "concept",
            "dimension": "D2",
            "description": f"Explore what {focus.lower()} means in this lesson and connect it to real civic situations.",
            "resources": concept_resources,
            "activities": [
                "Read the mini-lesson overview on key concepts and vocabulary.",
                "Complete a short sorting task to match concepts with examples.",
            ],
            "competencies": config.focus_concepts,
        }
    )

    source_resources: List[Dict[str, object]] = []
    for source in sources:
        if source.get("url"):
            source_resources.append(
                {
                    "title": source["title"],
                    "url": source["url"],
                    "instructions": source.get("prompt", "Examine this source for evidence."),
                }
            )

    tiles.append(
        {
            "id": "tile.source_analysis",
            "title": "Source Analysis",
            "kind": "source",
            "dimension": "D3",
            "description": "Analyze primary and secondary sources to gather evidence for the compelling question.",
            "resources": source_resources,
            "activities": [
                "Annotate each source focusing on origin, purpose, and audience.",
                "Log evidence that supports or challenges your initial ideas.",
            ],
            "competencies": ["Evidence Evaluation", "Source Corroboration"],
        }
    )

    tiles.append(
        {
            "id": "tile.practice",
            "title": "Practice & Apply",
            "kind": "practice",
            "dimension": "D2/D3",
            "description": "Use mini-practice items to apply the concept and prepare for the mastery check.",
            "resources": [],
            "activities": [
                "Complete auto-scored practice questions that classify examples and non-examples.",
                "Write a short constructed response that cites at least one source.",
            ],
            "competencies": ["Argumentation", "Application"],
        }
    )

    if prerequisite_status.get("primers"):
        tiles.insert(
            0,
            {
                "id": "tile.primer",
                "title": "Primer Boost",
                "kind": "primer",
                "dimension": "Bridge",
                "description": "Catch up on prerequisite knowledge before starting the independent mission.",
                "resources": [],
                "activities": prerequisite_status["primers"],
                "competencies": ["Prerequisite Knowledge"],
            },
        )

    return tiles


def derive_success_criteria(
    config: PlanConfig,
    performance_task: Dict[str, object],
) -> List[str]:
    focus = config.focus_concepts[0] if config.focus_concepts else "the concept"
    audience = performance_task["audience"]
    return [
        f"I can frame compelling and supporting questions that make {focus.lower()} visible in our case studies.",
        f"I can use disciplinary tools to explain how {focus.lower()} operates across contexts.",
        "I can corroborate evidence by citing origin, authority, and corroborative value from multiple sources.",
        f"I can tailor my product for the {audience} and address at least one counterclaim.",
    ]


def unique_by_code(indicators: List[Indicator]) -> List[Indicator]:
    seen: Dict[str, Indicator] = {}
    for indicator in indicators:
        if indicator.code not in seen:
            seen[indicator.code] = indicator
    return list(seen.values())
