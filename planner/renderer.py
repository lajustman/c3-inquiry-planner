from __future__ import annotations

from typing import Dict, List

from .models import PlanConfig


def render_teacher_plan(plan_data: Dict[str, object]) -> str:
    config: PlanConfig = plan_data["config"]
    indicators: Dict[str, List] = plan_data["indicators"]
    sequence: List[Dict[str, object]] = plan_data["sequence"]
    performance = plan_data["performance_task"]
    rubric: List[Dict[str, str]] = plan_data["rubric"]
    differentiation: Dict[str, List[str]] = plan_data["differentiation"]
    sources: List[Dict[str, object]] = plan_data["sources"]
    questions = plan_data["questions"]
    success = plan_data["success_criteria"]
    exemplars: List[Dict[str, object]] = plan_data.get("exemplars", [])
    dok_set: List[Dict[str, object]] = plan_data.get("dok_set", [])
    iteration_cycles: List[Dict[str, object]] = plan_data.get("iteration_cycles", [])
    interest_flow: Dict[str, object] = plan_data.get("interest_flow", {})
    prerequisite_status: Dict[str, object] = plan_data.get("prerequisite_status", {})
    learning_tiles: List[Dict[str, object]] = plan_data.get("learning_tiles", [])
    mastery_loop: Dict[str, object] = plan_data.get("mastery_loop", {})

    lines: List[str] = []
    lines.append(f"# {config.title}")
    lines.append("")
    lines.append(f"- **Grade Band:** {config.grade_band}")
    lines.append(f"- **Time Box:** {config.time_box_minutes} minutes")
    lines.append(f"- **Disciplines:** {', '.join(config.disciplines)}")
    lines.append(f"- **Focus Concepts:** {', '.join(config.focus_concepts)}")
    lines.append(f"- **Anchor Context:** {config.anchor_context}")
    lines.append(f"- **Transfer Context:** {config.transfer_context}")
    lines.append(f"- **Reading Range:** {config.reading_range}")
    if config.teacher_intent:
        lines.append(f"- **Teacher Intent:** {config.teacher_intent}")
    if config.required_standards:
        standards = "; ".join(config.required_standards)
        lines.append(f"- **Required Standards:** {standards}")
    lines.append("")

    lines.append("## Learning Objectives")
    for item in success:
        lines.append(f"- {item}")
    lines.append("")

    lines.append("## Compelling & Supporting Questions")
    lines.append(f"- **Compelling Question:** {questions['compelling']}")
    lines.append("- **Supporting Questions:**")
    for question in questions["supporting"]:
        lines.append(f"  - {question}")
    lines.append("")

    lines.append("## Target C3 Indicators")
    for dimension in ["D1", "D2", "D3", "D4"]:
        entries = indicators.get(dimension, [])
        if not entries:
            continue
        lines.append(f"- **{dimension}:**")
        for entry in entries:
            lines.append(f"  - `{entry.code}` — {entry.label}")
    lines.append("")

    if exemplars:
        lines.append("## Concept Playlist & Exemplars")
        for exemplar in exemplars:
            bullet = f"- **{exemplar['title']}** ({exemplar['role']}) — {exemplar['description']}"
            if exemplar.get("era_or_setting"):
                bullet += f" _(Setting: {exemplar['era_or_setting']})_"
            lines.append(bullet)
        lines.append("")

    lines.append("## Learning Sequence")
    for stage in sequence:
        stage_title = stage["stage"]
        minutes = stage.get("minutes")
        duration = f" ({minutes} min)" if minutes else ""
        lines.append(f"### {stage_title}{duration}")
        lines.append(f"- **Goal:** {stage['goal']}")
        lines.append("- **Activities:**")
        for step in stage["activities"]:
            lines.append(f"  - {step}")
        lines.append(f"- **Product Evidence:** {stage['product']}")
        resources = stage.get("resources") or []
        if resources:
            lines.append("- **Learning Resources:**")
            for resource in resources:
                title = resource.get("title")
                instructions = resource.get("instructions", "Use this resource during independent work.")
                url = resource.get("url")
                if url:
                    lines.append(f"  - [{title}]({url}) — {instructions}")
                else:
                    lines.append(f"  - {title}: {instructions}")
        lines.append("")

    lines.append("## Sources & Evidence Tasks (D3)")
    if sources:
        lines.append("| Source | Type | Origin & Value | Task Prompt |")
        lines.append("| --- | --- | --- | --- |")
        for source in sources:
            origin_value = f"{source['origin']} · {source['value']}"
            task_prompt = source["prompt"]
            lines.append(
                f"| {source['title']} | {source['type']} | {origin_value} | {task_prompt} |"
            )
    else:
        lines.append("_Add at least two sources with origin/value notes._")
    lines.append("")

    lines.append("## Performance Task & Rubric (D4)")
    lines.append(f"- **Product:** {performance['product']}")
    lines.append(f"- **Audience:** {performance['audience']}")
    lines.append(f"- **Prompt:** {performance['prompt']}")
    lines.append("- **Assessed Indicators:** " + ", ".join(performance["assesses"]))
    lines.append("")
    lines.append("| Dimension | Emerging | Developing | Proficient | Advanced |")
    lines.append("| --- | --- | --- | --- | --- |")
    for row in rubric:
        lines.append(
            f"| {row['dimension']} | {row['emerging']} | {row['developing']} | {row['proficient']} | {row['advanced']} |"
        )
    lines.append("")

    lines.append("## Differentiation & Accessibility")
    for category, supports_list in differentiation.items():
        lines.append(f"- **{category}:**")
        for support in supports_list:
            lines.append(f"  - {support}")
    lines.append("")

    if dok_set:
        lines.append("## Webb Depth of Knowledge Assessment Set")
        lines.append("| Level | Prompt | Suggested Products | Scaffolds |")
        lines.append("| --- | --- | --- | --- |")
        for task in dok_set:
            products = "; ".join(task["products"])
            supports = "; ".join(task["supports"])
            lines.append(f"| {task['level']} | {task['prompt']} | {products} | {supports} |")
        lines.append("")

    if iteration_cycles:
        lines.append("## Iterative Learning Cycles toward Mastery")
        for cycle in iteration_cycles:
            lines.append(f"- **{cycle['cycle']}** — {cycle['purpose']}")
            checkpoint = cycle.get("checkpoint", {})
            if checkpoint:
                lines.append(
                    f"  - Checkpoint: {checkpoint.get('level', '')} — {checkpoint.get('prompt', 'See DOK task.')}"
                )
            lines.append(f"  - Feedback moves: {cycle['feedback']}")
            lines.append(f"  - Next step: {cycle['next_step']}")
        lines.append("")

    if mastery_loop:
        lines.append("## Mastery Loop Automation")
        lines.append(f"- **Proficiency Target:** {mastery_loop.get('target', 'Reach rubric proficiency.')}")
        lines.append(f"- **Expectation:** {mastery_loop.get('expectation', '')}")
        dok_tasks = mastery_loop.get("dok_tasks", [])
        if dok_tasks:
            lines.append("- **Automated Sequence:**")
            for task in dok_tasks:
                lines.append(
                    f"  - {task['level']}: {task['prompt']} (Products: {', '.join(task['products'])})"
                )
        lines.append("")

    if interest_flow:
        lines.append("## AI Interest Routing Prompts")
        lines.append("- **Conversation Starters:**")
        for prompt in interest_flow.get("conversation_prompts", []):
            lines.append(f"  - {prompt}")
        lines.append("- **Routing Logic:**")
        for rule in interest_flow.get("routing_logic", []):
            lines.append(f"  - {rule}")
        current = interest_flow.get("current_exemplars")
        if current:
            lines.append("- **Current Exemplar Options:** " + ", ".join(current))
        lines.append("")

    return "\n".join(lines)


def render_student_sheet(plan_data: Dict[str, object]) -> str:
    config: PlanConfig = plan_data["config"]
    sequence: List[Dict[str, object]] = plan_data["sequence"]
    questions = plan_data["questions"]
    success = plan_data["success_criteria"]
    sources = plan_data["sources"]
    dok_set: List[Dict[str, object]] = plan_data.get("dok_set", [])
    iteration_cycles: List[Dict[str, object]] = plan_data.get("iteration_cycles", [])
    interest_flow: Dict[str, object] = plan_data.get("interest_flow", {})
    prerequisite_status: Dict[str, object] = plan_data.get("prerequisite_status", {})

    orientation_stage = next((stage for stage in sequence if stage.get("mode") == "orientation"), None)
    independent_stages = [stage for stage in sequence if stage.get("mode") == "independent"]
    assessment_stage = next((stage for stage in sequence if stage.get("mode") == "assessment"), None)
    iteration_stage = next((stage for stage in sequence if stage.get("mode") == "iteration"), None)
    mastery_loop = plan_data.get("mastery_loop", {})

    lines: List[str] = []
    lines.append(f"# Student Lesson Flow: {config.title}")
    lines.append("")

    lines.append("## Learning Objectives")
    for item in success:
        trimmed = item.strip()
        if trimmed.lower().startswith("i can"):
            lines.append(f"- {trimmed.rstrip('.') }.")
        else:
            text = trimmed.rstrip(".")
            if text:
                text = studentify_phrase(text)
            lines.append(f"- I can {text}.")
    lines.append("")

    lines.append("## Compelling & Supporting Questions")
    lines.append(f"- **Compelling:** {questions['compelling']}")
    for question in questions["supporting"]:
        lines.append(f"- {question}")
    lines.append("")

    lines.append("## Ask Your Own Questions")
    if orientation_stage:
        lines.append(orientation_stage["goal"])
        lines.append("Use this space to capture your questions:")
    else:
        lines.append("Record any questions you have about the topic before you dive into the sources.")
    lines.append("- ______________________________")
    lines.append("- ______________________________")
    lines.append("- ______________________________")
    lines.append("")

    lines.append("## Personalize Your Learning")
    prompts = interest_flow.get("conversation_prompts", [])
    if prompts:
        lines.append("Use these prompts to share interests with the AI assistant or your teacher:")
        for prompt in prompts:
            lines.append(f"- {prompt}")
    else:
        lines.append("Share interests or examples that connect this concept to your world.")
    selected = interest_flow.get("student_selected_exemplars")
    if selected:
        lines.append("")
        lines.append("Prioritized exemplars:")
        for title in selected:
            lines.append(f"- {title}")
    lines.append("")

    if prerequisite_status.get("primers"):
        lines.append("## Quick Primer (2-minute catch-up)")
        for primer in prerequisite_status["primers"]:
            lines.append(f"- {primer}")
        lines.append("")

    lines.append("## Independent Learning Mission")
    if independent_stages:
        for stage in independent_stages:
            minutes = stage.get("minutes")
            timing = f" ({minutes} min)" if minutes else ""
            lines.append(f"### {stage['stage']}{timing}")
            lines.append(f"- Goal: {stage['goal']}")
            lines.append("- Tasks:")
            for step in stage["activities"]:
                lines.append(f"  - {step}")
            lines.append(f"- Evidence to produce: {stage['product']}")
            resources = stage.get("resources") or []
            if resources:
                lines.append("- Launch these resources:")
                for resource in resources:
                    url = resource.get("url")
                    title = resource.get("title")
                    instructions = resource.get("instructions", "")
                    if url:
                        lines.append(f"  - [{title}]({url}) — {instructions}")
                    else:
                        lines.append(f"  - {title}: {instructions}")
            lines.append("")
    else:
        lines.append("- Follow the teacher-provided investigation steps and log your evidence.")
        lines.append("")

    lines.append("## Mastery Check")
    if assessment_stage:
        minutes = assessment_stage.get("minutes")
        timing = f" ({minutes} min)" if minutes else ""
        lines.append(f"- {assessment_stage['stage']}{timing}: {assessment_stage['goal']}")
        for step in assessment_stage["activities"]:
            lines.append(f"- {step}")
    if dok_set:
        lines.append("")
        lines.append("Complete these challenges:")
        for task in dok_set:
            lines.append(
                f"- **{task['level']}**: {task['prompt']} (Suggested products: {', '.join(task['products'])})"
            )
    lines.append("")

    lines.append("## Iterate to Mastery")
    if mastery_loop:
        lines.append(
            f"- Stay in the mastery loop until you meet this target: {mastery_loop.get('target', 'Reach proficiency')}"
        )
        if mastery_loop.get("expectation"):
            lines.append(f"- Expectation: {mastery_loop['expectation']}")
        dok_tasks = mastery_loop.get("dok_tasks", [])
        if dok_tasks:
            lines.append("- Loop through these tasks in order; repeat as needed:")
            for task in dok_tasks:
                lines.append(
                    f"  - {task['level']}: {task['prompt']} (Products: {', '.join(task['products'])})"
                )
    if mastery_loop:
        lines.append(
            f"- Stay in the mastery loop until you meet this target: {mastery_loop.get('target', 'reach proficiency')}"
        )
        if mastery_loop.get("expectation"):
            lines.append(f"- Expectation: {mastery_loop['expectation']}")
        dok_tasks = mastery_loop.get("dok_tasks", [])
        if dok_tasks:
            lines.append("- Repeat these tasks as needed:")
            for task in dok_tasks:
                lines.append(
                    f"  - {task['level']}: {task['prompt']} (Products: {', '.join(task['products'])})"
                )
    if iteration_stage:
        lines.append(f"- {iteration_stage['goal']}")
        for step in iteration_stage["activities"]:
            lines.append(f"  - {step}")
    if iteration_cycles:
        lines.append("")
        lines.append("Mastery cycle checkpoints:")
        for cycle in iteration_cycles:
            checkpoint = cycle.get("checkpoint", {})
            check_desc = checkpoint.get("prompt", checkpoint.get("level", "Checkpoint"))
            lines.append(f"- **{cycle['cycle']}**: {cycle['purpose']}")
            if check_desc:
                lines.append(f"  - Checkpoint: {check_desc}")
            lines.append(f"  - Feedback moves: {cycle['feedback']}")
            lines.append(f"  - Next step: {cycle['next_step']}")
    lines.append("")

    lines.append("## Source Tracker")
    if sources:
        for source in sources:
            lines.append(
                f"- {source['title']} ({source['type']}): capture a key detail and explain why the source is trustworthy."
            )
    else:
        lines.append("- Add evidence from each source you analyze.")
    lines.append("")

    lines.append("## Final Task Reminder")
    performance = plan_data["performance_task"]
    lines.append(
        f"Create a {performance['product'].lower()} for the {performance['audience']} that answers the compelling question with cited evidence and a counterclaim."
    )
    lines.append("")

    return "\n".join(lines)


def studentify_phrase(text: str) -> str:
    if not text:
        return text
    parts = text.split(" ", 1)
    verb = parts[0]
    rest = parts[1] if len(parts) > 1 else ""
    verb_lower = verb.lower()
    irregulars = {
        "frames": "frame",
        "distinguishes": "distinguish",
        "selects": "select",
        "corroborates": "corroborate",
        "tailors": "tailor",
        "explains": "explain",
        "constructs": "construct",
        "uses": "use",
        "evaluates": "evaluate",
        "applies": "apply",
    }
    if verb_lower in irregulars:
        base = irregulars[verb_lower]
    elif verb_lower.endswith("es"):
        base = verb_lower[:-2]
    elif verb_lower.endswith("s"):
        base = verb_lower[:-1]
    else:
        base = verb_lower
    if rest:
        return f"{base} {rest}"
    return base
    if prerequisite_status:
        lines.append("## Prerequisite Check")
        status = prerequisite_status.get("status", "clear").replace("_", " ").title()
        lines.append(f"- **Status:** {status}")
        primers = prerequisite_status.get("primers", [])
        if primers:
            lines.append("- **Required Primers:**")
            for primer in primers:
                lines.append(f"  - {primer}")
        lines.append("- **Indicators Covered:** " + ", ".join(prerequisite_status.get("indicators", [])))
        lines.append("")

    if learning_tiles:
        lines.append("## Independent Learning Tiles")
        for tile in learning_tiles:
            lines.append(f"- **{tile['title']}** ({tile['kind'].capitalize()}) — {tile['description']}")
            if tile.get("activities"):
                lines.append("  - Activities:")
                for activity in tile["activities"]:
                    lines.append(f"    - {activity}")
            resources = tile.get("resources") or []
            if resources:
                lines.append("  - Resources:")
                for resource in resources:
                    title = resource.get("title")
                    instructions = resource.get("instructions", "")
                    url = resource.get("url")
                    if url:
                        lines.append(f"    - [{title}]({url}) — {instructions}")
                    else:
                        lines.append(f"    - {title}: {instructions}")
            lines.append("  - Competencies: " + ", ".join(tile.get("competencies", [])))
        lines.append("")
