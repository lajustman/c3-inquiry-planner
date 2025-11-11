from __future__ import annotations

import ast
import copy
import json
import mimetypes
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import quote_plus, urlparse
import urllib.error
import urllib.request

from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional, Set, Tuple

from flask import Flask, abort, g, has_request_context, jsonify, redirect, render_template, request, session, url_for
from markupsafe import Markup, escape
from mutagen import File as MutagenFile

from planner.config import load_plan_config
from planner.generator import InquiryPlanner
from planner.indicators import IndicatorCatalog
from planner.llm import LLMUnavailable, default_llm_client
from planner.models import Indicator, PlanConfig
from planner.resource_finder import RESOURCE_FINDER
from .standards_catalog import ExpectationEntry, get_michigan_catalog

try:
    from .learning_agents import StageAgentCoordinator, StageAgentUnavailable
except ImportError:  # pragma: no cover - optional dependency
    StageAgentCoordinator = StageAgentUnavailable = None

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = APP_ROOT / "examples" / "middle_school_causation.json"
DEFAULT_ONTOLOGY_DIR = APP_ROOT / "Curriculum-Ontology" / "c3"
MICHIGAN_ONTOLOGY_DIR = APP_ROOT / "Curriculum-Ontology" / "michigan"

_INDICATOR_CATALOG = IndicatorCatalog.from_directory(DEFAULT_ONTOLOGY_DIR)
_INQUIRY_PLANNER = InquiryPlanner(_INDICATOR_CATALOG)

app = Flask(__name__)
app.secret_key = "c3-inquiry-secret"

if StageAgentCoordinator:
    try:
        STAGE_AGENT = StageAgentCoordinator()
    except StageAgentUnavailable as exc:  # pragma: no cover - optional dependency
        app.logger.warning("LangChain stage agents disabled: %s", exc)
        STAGE_AGENT = None
else:
    STAGE_AGENT = None


def load_plan_bundle(config_path: Path = DEFAULT_CONFIG) -> Tuple[Dict[str, object], PlanConfig]:
    plan_config = load_plan_config(config_path)
    bundle = _INQUIRY_PLANNER.build_plan(plan_config)
    return bundle.plan_data, plan_config


def prepare_plan(plan_data: Dict[str, object]) -> Dict[str, object]:
    def serialise_indicators(raw: Dict[str, List]) -> Dict[str, List[Dict[str, str]]]:
        result: Dict[str, List[Dict[str, str]]] = {}
        for dimension, entries in raw.items():
            serialised: List[Dict[str, str]] = []
            for indicator in entries:
                serialised.append({"code": indicator.code, "label": indicator.label})
            result[dimension] = serialised
        return result

    def serialise_sequence(raw: List[Dict[str, object]]) -> List[Dict[str, object]]:
        output: List[Dict[str, object]] = []
        for stage in raw:
            copy = {
                "stage": stage.get("stage"),
                "mode": stage.get("mode"),
                "minutes": stage.get("minutes"),
                "goal": stage.get("goal"),
                "activities": list(stage.get("activities", [])),
                "product": stage.get("product"),
                "resources": stage.get("resources", []),
            }
            output.append(copy)
        return output

    metadata = plan_data.get("metadata", {})

    prepared = {
        "title": plan_data["metadata"]["title"],
        "objectives": plan_data.get("success_criteria", []),
        "questions": plan_data.get("questions", {}),
        "indicators": serialise_indicators(plan_data.get("indicators", {})),
        "sequence": serialise_sequence(plan_data.get("sequence", [])),
        "sources": plan_data.get("sources", []),
        "exemplars": plan_data.get("exemplars", []),
        "dok_set": plan_data.get("dok_set", []),
        "iteration_cycles": plan_data.get("iteration_cycles", []),
        "interest_flow": plan_data.get("interest_flow", {}),
        "prerequisite_status": plan_data.get("prerequisite_status", {}),
        "learning_tiles": plan_data.get("learning_tiles", []),
        "mastery_loop": plan_data.get("mastery_loop", {}),
        "grade_band": metadata.get("grade_band"),
        "disciplines": metadata.get("disciplines", []),
        "focus_concepts": metadata.get("focus_concepts", []),
        "anchor_context": metadata.get("anchor_context"),
        "transfer_context": metadata.get("transfer_context"),
        "teacher_intent": metadata.get("teacher_intent"),
        "time_box_minutes": metadata.get("time_box_minutes"),
    }
    return prepared


def resolve_vocab_url(term: str) -> str:
    slug = quote_plus(term.lower())
    plain = term.replace(" ", "")
    if term.isalpha() and " " not in term:
        return f"https://www.dictionary.com/browse/{slug}"
    search = quote_plus(term)
    return f"https://en.wikipedia.org/wiki/Special:Search?search={search}"


def build_vocab_list(
    vocab_defs: Dict[str, str],
    priority_terms: Optional[List[Tuple[str, str]]] = None,
) -> List[Dict[str, str]]:
    terms: List[Tuple[str, Optional[str]]] = []
    if priority_terms:
        terms.extend(priority_terms)
    base_terms = [
        ("Causation", vocab_defs.get("causation")),
        ("Civic Participation", vocab_defs.get("civic participation")),
        ("Evidence", vocab_defs.get("evidence")),
        ("Corroborate", vocab_defs.get("corroborate")),
    ]
    terms.extend(base_terms)
    extras = [
        (term.title(), definition)
        for term, definition in vocab_defs.items()
        if term
        and definition
        and term
        not in {"causation", "civic participation", "evidence", "corroborate", "counterclaim", "indicator"}
    ]
    terms.extend(extras)
    seen: set[str] = set()
    vocab_items: List[Dict[str, str]] = []
    for term, definition in terms:
        if not term or not definition:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        vocab_items.append({
            "term": term,
            "definition": definition,
            "url": resolve_vocab_url(term),
        })
    return vocab_items


BASE_VOCAB_DEFS = {
    "causation": "How one event leads to another or produces an effect.",
    "civic participation": "Actions people take to influence their community or government decisions.",
    "evidence": "Information that supports a claim.",
    "corroborate": "Confirm a claim by checking multiple sources.",
    "counterclaim": "An argument that responds to or challenges another claim.",
    "indicator": "A skill or standard we are targeting in this lesson.",
}

VOCAB_STOPWORDS = {
    "the",
    "and",
    "that",
    "with",
    "from",
    "will",
    "have",
    "this",
    "into",
    "their",
    "about",
    "which",
    "they",
    "help",
    "inform",
    "others",
    "students",
    "people",
    "community",
    "communities",
    "evidence",
    "analysis",
    "using",
    "information",
    "actions",
    "plan",
    "learn",
    "learning",
    "question",
    "questions",
    "sources",
    "civic",
    "discipline",
    "participate",
    "participation",
    "projects",
}

LESSON_LIBRARY = {
    "8-P4.2.3": {
        "title": "Youth Activism and Change: Birmingham to Today",
        "summary": "Participate in civic action projects by connecting historical youth activism to current student safety movements.",
        "config_path": DEFAULT_CONFIG,
    },
}

LESSON_ALIASES = {
    "default": "8-P4.2.3",
    "8p4.2.3": "8-P4.2.3",
    "8_p4.2.3": "8-P4.2.3",
}
DEFAULT_PLAN_KEY = "8-P4.2.3"


@dataclass
class PlanRuntime:
    key: str
    plan: Dict[str, object]
    config: PlanConfig
    raw: Dict[str, object]
    vocab_defs: Dict[str, str]
    exemplar_terms: Set[str]


PLAN_CACHE: Dict[str, PlanRuntime] = {}


def build_vocab_definitions(plan: Dict[str, object]) -> Dict[str, str]:
    vocab = dict(BASE_VOCAB_DEFS)
    for concept in plan.get("focus_concepts", []):
        label = str(concept or "").strip()
        if not label:
            continue
        if re.search(r"\d", label):
            # Standard-like tokens belong to the standards drawer, not vocab.
            continue
        vocab.setdefault(label.lower(), f"A key concept in this lesson: {label}.")
    return vocab


def _extract_vocab_terms(text: str, limit: int = 5) -> List[str]:
    if not text:
        return []
    seen: Set[str] = set()
    terms: List[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z'-]+", text):
        lower = word.lower()
        if lower in VOCAB_STOPWORDS or len(lower) < 4:
            continue
        if lower not in seen:
            seen.add(lower)
            terms.append(word.title())
        if len(terms) >= limit:
            break
    return terms


def _build_expectation_vocab_entries(expectation: ExpectationEntry, selection: Dict[str, object]) -> List[Tuple[str, str]]:
    entries: List[Tuple[str, str]] = []
    seen: Set[str] = set()

    def add(term: Optional[str], definition: str) -> None:
        clean = str(term or "").strip()
        if not clean:
            return
        key = clean.lower()
        if key in seen:
            return
        seen.add(key)
        entries.append((clean, definition))

    trimmed_label = expectation.label.split("(", 1)[0].strip()
    add(trimmed_label, expectation.text)
    tokens = _extract_vocab_terms(expectation.text)
    for token in tokens[:4]:
        add(token, f"A key word from this expectation that helps you discuss {trimmed_label.lower()}.")
    return entries


def _build_standard_entries(
    codes: Iterable[str],
    description: str,
    grade_level: Optional[str] = None,
) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for code in codes:
        clean_code = str(code or "").strip()
        if not clean_code:
            continue
        entries.append(
            {
                "code": clean_code,
                "description": description,
                "grade": grade_level or "",
            }
        )
    return entries


def extract_exemplar_terms(plan: Dict[str, object]) -> Set[str]:
    terms: Set[str] = set()
    for exemplar in plan.get("exemplars", []):
        title = exemplar.get("title", "")
        for token in re.findall(r"[A-Za-z]+", str(title).lower()):
            terms.add(token)
    return terms


def _normalise_lesson_code(code: str) -> str:
    return code.replace(" ", "").upper()


def _normalise_expectation_code(code: str) -> str:
    return re.sub(r"\s+", "", str(code or "")).upper()


def _find_expectation_entry(expectation_code: str) -> Tuple[Optional[str], Optional[Dict[str, object]]]:
    catalog = get_michigan_catalog(MICHIGAN_ONTOLOGY_DIR)
    normalised_target = _normalise_expectation_code(expectation_code)
    for full_code, payload in catalog.expectation_index.items():
        if _normalise_expectation_code(full_code) == normalised_target:
            return full_code, payload
    return None, None


def _sentence_case(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    return stripped[0].lower() + stripped[1:]

VERB_HINTS = {
    "apply",
    "ask",
    "analyze",
    "build",
    "compare",
    "construct",
    "create",
    "describe",
    "determine",
    "develop",
    "evaluate",
    "explain",
    "gather",
    "identify",
    "investigate",
    "participate",
    "plan",
    "summarize",
    "trace",
    "use",
    "write",
}


def _clean_expectation_phrase(text: str) -> str:
    phrase = str(text or "").strip()
    if not phrase:
        return ""
    phrase = re.sub(r"\s+", " ", phrase)
    phrase = phrase.replace("...", "")
    phrase = re.sub(r"\([^)]{15,}\)", "", phrase)
    phrase = re.sub(r"(?i)keep\s+(?:our\s+)?inquiry\s+on[^,;.]+", "", phrase)
    phrase = re.sub(r"(?i)grade[-\s]*(?:level\s*)?(k|[0-9]+)", "", phrase)
    phrase = re.sub(r"\s+", " ", phrase)
    return phrase.strip(" ,;:-")


def _is_title_case_list(phrase: str) -> bool:
    words = re.findall(r"[A-Za-z]+", phrase)
    if not words:
        return False
    lower_exceptions = {"and", "or", "of", "to", "the", "a", "an", "for", "in", "on", "with"}
    for word in words:
        if len(word) == 1:
            continue
        if word.lower() in lower_exceptions:
            continue
        if not (word[0].isupper() and word[1:].islower()):
            return False
    return True


def _is_likely_fragment(phrase: str) -> bool:
    lower = phrase.lower()
    if not lower:
        return True
    for verb in VERB_HINTS:
        if lower.startswith(f"{verb} ") or f" {verb} " in lower:
            return False
    if " to " in lower:
        return False
    if re.search(r"\\b[a-z]+ing\\b", lower):
        return False
    return True


def _normalise_list_phrase(phrase: str) -> str:
    cleaned = phrase.strip().rstrip(".")
    if _is_title_case_list(cleaned):
        return cleaned.lower()
    return cleaned


def _student_objective_phrase(expectation_text: str, expectation_label: str) -> str:
    primary = _clean_expectation_phrase(expectation_text)
    alternate = _clean_expectation_phrase(expectation_label)
    phrase = primary if primary else alternate
    if not phrase:
        return ""
    if _is_likely_fragment(phrase):
        phrase = f"practice {_normalise_list_phrase(phrase)}"
    if phrase.lower().startswith(("the ", "a ", "an ")):
        phrase = f"use {phrase.lower()}"
    phrase = re.sub(r"\s+", " ", phrase).strip()
    phrase = phrase.rstrip(".")
    return _to_student_phrase(phrase)


def _to_gerund(word: str) -> str:
    lower = word.lower()
    if lower.endswith("ing"):
        return lower
    if lower.endswith("ie"):
        return lower[:-2] + "ying"
    if lower.endswith("ee"):
        return lower + "ing"
    if lower.endswith("e") and len(lower) > 2:
        return lower[:-1] + "ing"
    if (
        len(lower) > 2
        and lower[-1] not in "aeiouwxy"
        and lower[-2] in "aeiou"
        and lower[-3] not in "aeiou"
        and len(lower) <= 4
    ):
        return lower + lower[-1] + "ing"
    return lower + "ing"


def _to_gerund_phrase(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    words = stripped.split()
    first = words[0]
    words[0] = _to_gerund(first)
    return " ".join(words)


def _to_student_phrase(text: str) -> str:
    stripped = str(text or "").strip()
    if not stripped:
        return ""
    words = stripped.split()
    words[0] = words[0].lower()
    return " ".join(words)


def _clean_indicator_text(text: str) -> str:
    stripped = str(text or "").strip().rstrip(".")
    if stripped.lower().startswith("students will "):
        stripped = stripped[13:]
    if stripped.lower().startswith("students "):
        stripped = stripped[9:]
    return _sentence_case(stripped)


def _build_supporting_objectives(
    indicator_map: Dict[str, List[Indicator]],
    expectation_text: str,
    anchor_context: Optional[str],
    discipline_label: Optional[str],
) -> Tuple[List[str], List[str]]:
    objectives: List[str] = []
    questions: List[str] = []
    focus = expectation_text
    discipline_phrase = (discipline_label or "disciplinary ideas").lower()
    templates = {
        "D1": "ask important questions that help me {action_phrase}.",
        "D2": "use {discipline} ideas to {action_phrase}.",
        "D3": "evaluate sources and evidence by {action_gerund}.",
        "D4": "share what I learned and plan next steps by {action_gerund}.",
    }
    question_templates = {
        "D1": "What questions can I ask to help me {action_phrase}?",
        "D2": "Which {discipline} tools or sources will help me {action_phrase}?",
        "D3": "How can I check the strength of evidence while {action_phrase}?",
        "D4": "How will I share what I learned and plan next steps while {action_phrase}?",
    }
    for dimension in ("D1", "D2", "D3", "D4"):
        indicators = indicator_map.get(dimension, [])
        if not indicators:
            continue
        indicator = indicators[0]
        base = _clean_indicator_text(indicator.label)
        action_phrase = _to_student_phrase(base)
        action_gerund = _to_gerund_phrase(base)
        template = templates.get(dimension)
        if template:
            objectives.append(
                template.format(
                    action_phrase=action_phrase,
                    action_gerund=action_gerund,
                    discipline=discipline_phrase,
                )
            )
        else:
            objectives.append(action_phrase)
        question_template = question_templates.get(dimension)
        if question_template:
            questions.append(
                question_template.format(
                    focus=focus,
                    discipline=discipline_phrase,
                    action_phrase=action_phrase,
                )
            )
    seen: Set[str] = set()
    unique_objectives: List[str] = []
    for obj in objectives:
        key = obj.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique_objectives.append(obj)
    seen.clear()
    unique_questions: List[str] = []
    for question in questions:
        key = question.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique_questions.append(question)
    return unique_objectives, unique_questions


def load_plan_runtime(plan_key: str) -> PlanRuntime:
    if plan_key in PLAN_CACHE:
        return PLAN_CACHE[plan_key]

    resolved_key = LESSON_ALIASES.get(plan_key, plan_key)
    if resolved_key in PLAN_CACHE:
        return PLAN_CACHE[resolved_key]

    entry = LESSON_LIBRARY.get(resolved_key)
    if not entry:
        if resolved_key in PLAN_CACHE:
            return PLAN_CACHE[resolved_key]
        if resolved_key != DEFAULT_PLAN_KEY:
            raise ValueError(f"No lesson registered for key {plan_key}")
        entry = LESSON_LIBRARY[DEFAULT_PLAN_KEY]
        if DEFAULT_PLAN_KEY in PLAN_CACHE:
            return PLAN_CACHE[DEFAULT_PLAN_KEY]

    cached = PLAN_CACHE.get(resolved_key)
    if cached:
        return cached

    config_path = entry["config_path"]
    if not isinstance(config_path, Path):
        config_path = Path(config_path)

    plan_data_raw, plan_config = load_plan_bundle(config_path)
    plan = prepare_plan(plan_data_raw)
    vocab_defs = build_vocab_definitions(plan)
    plan["vocabulary"] = build_vocab_list(vocab_defs)
    plan["standards"] = _build_standard_entries(
        plan_config.required_standards or [],
        plan_config.teacher_intent or plan_config.compelling_question or plan_config.title,
        grade_level=plan_config.grade_band,
    )
    exemplar_terms = extract_exemplar_terms(plan)
    runtime = PlanRuntime(
        key=resolved_key,
        plan=plan,
        config=plan_config,
        raw=plan_data_raw,
        vocab_defs=vocab_defs,
        exemplar_terms=exemplar_terms,
    )
    PLAN_CACHE[resolved_key] = runtime
    return runtime


def active_plan_runtime() -> PlanRuntime:
    runtime = getattr(g, "plan_runtime", None)
    if runtime is not None:
        return runtime
    if has_request_context():
        plan_key = session.get("active_plan_key") or DEFAULT_PLAN_KEY
    else:
        plan_key = DEFAULT_PLAN_KEY
    runtime = load_plan_runtime(plan_key)
    if has_request_context():
        g.plan_runtime = runtime
    return runtime


def active_plan() -> Dict[str, object]:
    return active_plan_runtime().plan


def active_plan_config() -> PlanConfig:
    return active_plan_runtime().config


def active_vocab_defs() -> Dict[str, str]:
    return active_plan_runtime().vocab_defs


def active_exemplar_terms() -> Set[str]:
    return active_plan_runtime().exemplar_terms


def build_lesson_from_expectation(expectation_code: str) -> Tuple[PlanRuntime, Dict[str, object]]:
    full_code, selection = _find_expectation_entry(expectation_code)
    if not selection:
        raise ValueError("We couldn't find that expectation.")

    expectation = selection["expectation"]
    lesson_key = _normalise_lesson_code(expectation.full_code)

    reset_plan_progress()
    session.pop("selected_standard", None)
    session.pop("active_plan_key", None)

    base_plan_data, base_plan_config = load_plan_bundle(DEFAULT_CONFIG)
    plan_raw = copy.deepcopy(base_plan_data)

    metadata = plan_raw.get("metadata", {})
    title = f"{expectation.full_code}: {expectation.label}"
    metadata["title"] = title
    metadata["grade_band"] = selection.get("unit_label", metadata.get("grade_band"))
    metadata["anchor_context"] = selection["unit_label"]
    metadata["transfer_context"] = expectation.label
    metadata["teacher_intent"] = expectation.text
    metadata["focus_concepts"] = [selection["discipline_label"], expectation.code]
    metadata["disciplines"] = [selection["discipline_label"]]
    metadata["required_standards"] = [expectation.full_code]

    indicator_map_raw = plan_raw.get("indicators", {})
    indicator_map_raw["MI"] = [
        Indicator(
            code=expectation.full_code,
            label=expectation.text,
            dimension="MI",
            grade_band=metadata.get("grade_band") or base_plan_config.grade_band,
            discipline=selection["discipline_label"],
            concepts=[expectation.code],
        )
    ]
    plan_raw["indicators"] = indicator_map_raw

    questions = plan_raw.get("questions", {})
    questions["compelling"] = expectation.text
    supporting_questions = [
        f"What background knowledge helps us address {expectation.code}?",
        f"Which sources and evidence show mastery of {expectation.code}?",
        f"How will we communicate what we learned about {expectation.code}?",
    ]
    questions["supporting"] = supporting_questions

    plan_raw["metadata"] = metadata
    plan_raw["questions"] = questions
    expectation_phrase = expectation.text.rstrip(".")
    student_phrase = _student_objective_phrase(expectation.text, expectation.label)
    if not student_phrase:
        student_phrase = _to_student_phrase(expectation_phrase)
    base_objective = f"I can {student_phrase}."
    indicator_objectives, indicator_questions = _build_supporting_objectives(
        plan_raw.get("indicators", {}),
        expectation.text,
        metadata.get("anchor_context"),
        selection["discipline_label"],
    )
    plan_raw["success_criteria"] = [base_objective] + [f"I can {obj}" for obj in indicator_objectives]
    question_suggestions: List[str] = []
    question_suggestions.append(f"What sources or examples will help me {student_phrase}?")
    for question in indicator_questions:
        question_suggestions.append(question)
    cleaned_questions: List[str] = []
    seen_question_keys: Set[str] = set()
    for question in question_suggestions:
        q = question.strip()
        key = q.lower()
        if not q or key in seen_question_keys:
            continue
        seen_question_keys.add(key)
        cleaned_questions.append(q if q.endswith("?") else q + "?")
    question_seed = cleaned_questions[0] if cleaned_questions else ""
    session["question_suggestions"] = cleaned_questions
    session["question_suggestion_index"] = 1 if cleaned_questions else 0

    plan = prepare_plan(plan_raw)
    vocab_defs = build_vocab_definitions(plan)
    vocab_defs[f"{expectation.full_code.lower()}"] = f"Michigan expectation {expectation.full_code}: {expectation.text}"
    lesson_vocab = _build_expectation_vocab_entries(expectation, selection)
    for term, definition in lesson_vocab:
        vocab_defs.setdefault(term.lower(), definition)
    discipline_label = selection["discipline_label"]
    if discipline_label:
        vocab_defs.setdefault(
            discipline_label.lower(),
            f"A key disciplinary lens for this lesson: {discipline_label}.",
        )
    plan["vocabulary"] = build_vocab_list(vocab_defs, priority_terms=lesson_vocab)
    plan["standards"] = [
        {
            "code": expectation.full_code,
            "description": expectation.text,
        }
    ]
    exemplar_terms = extract_exemplar_terms(plan)

    updated_config = replace(
        base_plan_config,
        title=title,
        disciplines=[selection["discipline_label"]],
        focus_concepts=[expectation.code, selection["discipline_label"]],
        anchor_context=selection["unit_label"],
        transfer_context=expectation.label,
        teacher_intent=expectation.text,
        required_standards=[expectation.full_code],
        compelling_question=expectation.text,
        supporting_questions=supporting_questions,
    )

    runtime = PlanRuntime(
        key=lesson_key,
        plan=plan,
        config=updated_config,
        raw=plan_raw,
        vocab_defs=vocab_defs,
        exemplar_terms=exemplar_terms,
    )

    PLAN_CACHE[lesson_key] = runtime
    LESSON_ALIASES.setdefault(expectation.full_code, lesson_key)
    LESSON_ALIASES.setdefault(_normalise_expectation_code(expectation.full_code), lesson_key)

    selection_payload = {
        "full_code": expectation.full_code,
        "label": expectation.text or expectation.label,
        "unit_label": selection["unit_label"],
        "discipline_label": selection["discipline_label"],
        "lesson_title": title,
        "lesson_summary": expectation.text,
    }

    session["active_plan_key"] = lesson_key
    session["selected_standard"] = selection_payload
    session["selection_message"] = {
        "type": "success",
        "text": f"Lesson ready: {title}",
    }
    session.modified = True

    return runtime, selection_payload, question_seed, cleaned_questions


PLAN_REQUIRED_ENDPOINTS = {
    "overview",
    "objectives",
    "interest_check",
    "learning_path",
    "mastery",
    "summary",
    "api_suggest_question",
    "api_interest_suggestions",
    "api_learning_path",
    "api_learning_feedback",
    "resource_page",
}


@app.before_request
def ensure_plan_selected():
    endpoint = request.endpoint
    if not endpoint:
        return None
    if endpoint in PLAN_REQUIRED_ENDPOINTS:
        plan_key = session.get("active_plan_key")
        if not plan_key:
            return redirect(url_for("catalog"))
        try:
            active_plan_runtime()
        except ValueError:
            session["selection_message"] = {
                "type": "info",
                "text": "Let’s build a fresh lesson for your next inquiry.",
            }
            session.pop("active_plan_key", None)
            session.pop("selected_standard", None)
            session.modified = True
            return redirect(url_for("catalog"))
    elif session.get("active_plan_key"):
        try:
            active_plan_runtime()
        except ValueError:
            session.pop("active_plan_key", None)
            session.pop("selected_standard", None)
            session.modified = True
    return None


LLM_CLIENT = default_llm_client()

# Curated learning resources that can be served without relying on external APIs.
# Each entry maps to a lightweight in-app overview page so students always land on
# a working resource even if third-party links change.
CURATED_RESOURCE_LIBRARY = {
    "youth_voice": [
        {
            "title": "Youth Activism in Birmingham, 1963",
            "description": "Learn how middle school students in Birmingham forced national attention on civil rights during the Children's Crusade.",
            "url": "/resources/youth-activism-birmingham",
            "format": "article",
            "source": "C3 Resource Studio",
        },
        {
            "title": "Student Safety Movement Timeline",
            "description": "Track key moments when students organized walkouts and campaigns to improve safety in their schools.",
            "url": "/resources/student-safety-timeline",
            "format": "guide",
            "source": "C3 Resource Studio",
        },
        {
            "title": "Youth Activism Media Spotlight",
            "description": "Watch short videos and podcasts highlighting student-led advocacy on safety and civic participation.",
            "url": "/resources/youth-activism-media",
            "format": "video",
            "source": "C3 Resource Studio",
        },
        {
            "title": "Voices of Youth Civic Participation",
            "description": "Explore quotes and strategies from recent youth-led campaigns that connect to today’s civic questions.",
            "url": "/resources/voices-of-youth",
            "format": "article",
            "source": "C3 Resource Studio",
        },
    ],
    "justice": [
        {
            "title": "Youth Activism in Birmingham, 1963",
            "description": "Learn how middle school students in Birmingham forced national attention on civil rights during the Children's Crusade.",
            "url": "/resources/youth-activism-birmingham",
            "format": "article",
            "source": "C3 Resource Studio",
        },
        {
            "title": "Youth Activism Media Spotlight",
            "description": "Watch short videos and podcasts highlighting student-led advocacy on safety and civic participation.",
            "url": "/resources/youth-activism-media",
            "format": "video",
            "source": "C3 Resource Studio",
        },
        {
            "title": "Voices of Youth Civic Participation",
            "description": "Explore quotes and strategies from recent youth-led campaigns that connect to today’s civic questions.",
            "url": "/resources/voices-of-youth",
            "format": "article",
            "source": "C3 Resource Studio",
        },
    ],
    "general": [
        {
            "title": "Youth Activism in Birmingham, 1963",
            "description": "Learn how middle school students in Birmingham forced national attention on civil rights during the Children's Crusade.",
            "url": "/resources/youth-activism-birmingham",
            "format": "article",
            "source": "C3 Resource Studio",
        },
        {
            "title": "Student Safety Movement Timeline",
            "description": "Track key moments when students organized walkouts and campaigns to improve safety in their schools.",
            "url": "/resources/student-safety-timeline",
            "format": "guide",
            "source": "C3 Resource Studio",
        },
        {
            "title": "Youth Activism Media Spotlight",
            "description": "Watch short videos and podcasts highlighting student-led advocacy on safety and civic participation.",
            "url": "/resources/youth-activism-media",
            "format": "video",
            "source": "C3 Resource Studio",
        },
    ],
}

CURATED_RESOURCE_PAGES: Dict[str, Dict[str, object]] = {
    "youth-activism-birmingham": {
        "title": "Youth Activism in Birmingham, 1963",
        "summary": (
            "During the Children's Crusade, students as young as 12 skipped school to march against segregation. "
            "Their courage filled city jails, drew national television coverage, and pressured federal leaders to support the Civil Rights Act."
        ),
        "featured_resources": [
            {
                "title": "Children's Crusade of 1963 | American Freedom Stories",
                "format": "video",
                "description": "Archival footage shows how Birmingham students organized, marched, and shifted national attention toward civil rights.",
                "url": "https://www.youtube.com/watch?v=WV0k-3Hkjsw",
                "embed": "https://www.youtube.com/embed/WV0k-3Hkjsw",
                "duration": "4 min video",
            },
            {
                "title": "Children's Crusade of 1963 (newsreel)",
                "format": "video",
                "description": "Historic newsreel clips capture the intensity of the marches and the response from local officials.",
                "url": "https://www.youtube.com/watch?v=WgagrncGcss",
                "embed": "https://www.youtube.com/embed/WgagrncGcss",
                "duration": "3 min video",
            },
            {
                "title": "Timeline: Birmingham Children's Crusade",
                "format": "article",
                "description": "Primary source timeline from the Civil Rights Movement Archive detailing each day of student-led action in 1963.",
                "url": "https://www.crmvet.org/tim/tim63b.htm",
            },
        ],
        "key_points": [
            "Student leaders from the Alabama Christian Movement for Human Rights trained peers in nonviolent tactics before the marches.",
            "Police chief Eugene “Bull” Connor ordered fire hoses and police dogs on students, shocking viewers across the country.",
            "Media coverage of the violence pushed President John F. Kennedy to call civil rights a moral issue and propose new legislation.",
        ],
        "reflection_questions": [
            "Why did young people decide to risk arrest in Birmingham?",
            "How did national media attention change the impact of the Children's Crusade?",
        ],
        "further_reading": [
            {
                "label": "Smithsonian Magazine: Five Times Teens Drove Social Change",
                "url": "https://www.smithsonianmag.com/history/five-times-teens-drove-social-change-180965256/",
            },
            {
                "label": "Stanford King Institute: Children's Crusade",
                "url": "https://kinginstitute.stanford.edu/encyclopedia/childrens-crusade",
            },
        ],
    },
    "student-safety-timeline": {
        "title": "Student Safety Movement Timeline",
        "summary": (
            "From classroom walkouts in the 1960s to present-day safety campaigns, youth activists have demanded safer schools and communities."
        ),
        "featured_resources": [
            {
                "title": "Students Leading the Way on Campus Safety",
                "format": "article",
                "description": "KQED's classroom explainer traces key campaigns for safer schools and provides discussion prompts for learners.",
                "url": "https://www.kqed.org/lowdown/28974/students-leading-the-way-on-campus-safety",
            },
            {
                "title": "Student voices demand safer schools (C-SPAN)",
                "format": "video",
                "description": "Parkland survivors testify before lawmakers about the changes they want to see in school safety policy.",
                "url": "https://www.c-span.org/clip/public-affairs-event/user-clip-lifton-on-the-curve/4728755",
                "embed": "https://www.c-span.org/video/standalone/?c=4728755",
                "duration": "2 min video",
            },
            {
                "title": "March for Our Lives rally speech",
                "format": "video",
                "description": "A student organizer shares how their community mobilised after the March for Our Lives to keep safety on the agenda.",
                "url": "https://www.youtube.com/watch?v=IooAnq9n3Vg",
                "embed": "https://www.youtube.com/embed/IooAnq9n3Vg",
                "duration": "3 min video",
            },
        ],
        "key_points": [
            "1968: Chicago students organized walkouts to demand better school conditions and culturally responsive curriculum.",
            "2018: The March for Our Lives drew hundreds of thousands to Washington, D.C., amplifying demands for gun safety legislation.",
            "2023–24: Students combine social media campaigns with school board testimonies to push for safe learning environments.",
        ],
        "reflection_questions": [
            "What safety issues show up repeatedly across different decades?",
            "How do students balance immediate action (walkouts, rallies) with long-term change (policy proposals)?",
        ],
        "further_reading": [
            {
                "label": "PBS NewsHour Classroom: Student-Led Movements That Changed History",
                "url": "https://www.pbs.org/newshour/extra/lessons-plans/student-led-movements-that-changed-history/",
            },
            {
                "label": "NBC News: How Generation Z Has Led a New Wave of Protests",
                "url": "https://www.nbcnews.com/news/us-news/how-generation-z-has-led-new-wave-protests-rcna120764",
            },
        ],
    },
    "voices-of-youth": {
        "title": "Voices of Youth Civic Participation",
        "summary": (
            "Recent youth-led campaigns share strategies like storytelling, coalition building, and data collection to persuade decision makers."
        ),
        "featured_resources": [
            {
                "title": "Members of the Children's Crusade recall historic march",
                "format": "video",
                "description": "Former youth activists explain what motivated them and how young voices still influence civic action today.",
                "url": "https://www.youtube.com/watch?v=8EJ-3X4wbDA",
                "embed": "https://www.youtube.com/embed/8EJ-3X4wbDA",
                "duration": "5 min video",
            },
            {
                "title": "The United States' Children's Crusade (1963)",
                "format": "video",
                "description": "A short explainer connects the Birmingham marches with later movements led by students.",
                "url": "https://www.youtube.com/watch?v=UCpVZyGPqtU",
                "embed": "https://www.youtube.com/embed/UCpVZyGPqtU",
                "duration": "4 min video",
            },
            {
                "title": "How Young People Are Driving Change",
                "format": "article",
                "description": "KQED highlights organizers from different communities and the tactics they use to build coalitions.",
                "url": "https://www.kqed.org/education/533924/how-young-people-are-driving-change",
            },
        ],
        "key_points": [
            "Youth activists often cite personal stories to connect local experiences to wider policy debates.",
            "Digital organizing tools (hashtags, livestreams) allow students to coordinate quickly while documenting their efforts.",
            "Successful campaigns invite adult allies to share power rather than speak for students.",
        ],
        "reflection_questions": [
            "Which organizing strategies feel most useful for your question or community?",
            "How do young leaders combine evidence with personal narratives when they speak?",
        ],
        "further_reading": [
            {
                "label": "UNICEF: Youth Activists Changing the World",
                "url": "https://www.unicef.org/stories/youth-activists-who-are-changing-world",
            },
            {
                "label": "Students Rebuild: Youth Activists Making an Impact",
                "url": "https://studentsrebuild.org/blog/five-youth-activists-making-an-impact-in-2023",
            },
        ],
    },
    "youth-activism-media": {
        "title": "Youth Activism Media Spotlight",
        "summary": (
            "Use these short video spotlights to hear directly from student organizers who are working on school safety and civic change."
        ),
        "featured_resources": [
            {
                "title": "Cameron Kasky speaks at March For Our Lives",
                "format": "video",
                "description": "A Parkland survivor outlines how students moved from grief to organising for safer schools.",
                "url": "https://www.youtube.com/watch?v=rgc2il-20g8",
                "embed": "https://www.youtube.com/embed/rgc2il-20g8",
                "duration": "4 min video",
            },
            {
                "title": "Samantha Fuentes: \"Listen\"",
                "format": "video",
                "description": "This rally speech models how students blend personal story with evidence to persuade audiences.",
                "url": "https://www.youtube.com/watch?v=TEFqRTigvDQ",
                "embed": "https://www.youtube.com/embed/TEFqRTigvDQ",
                "duration": "3 min video",
            },
            {
                "title": "Children's Crusade of 1963 | American Freedom Stories",
                "format": "video",
                "description": "Pair this archival clip with modern testimonies to compare how youth have framed safety demands across decades.",
                "url": "https://www.youtube.com/watch?v=WV0k-3Hkjsw",
                "embed": "https://www.youtube.com/embed/WV0k-3Hkjsw",
                "duration": "4 min video",
            },
        ],
        "key_points": [
            "Video playlists pair historic footage from the Children's Crusade with present-day testimonies from student safety advocates.",
            "Clips model how young people frame claims, evidence, and calls to action in two minutes or less.",
            "Each media highlight includes a suggested note-taking focus so you can capture evidence quickly.",
        ],
        "reflection_questions": [
            "What persuasive techniques stand out in the videos or clips?",
            "How might you adapt one of these approaches for your own civic product?",
        ],
        "further_reading": [
            {
                "label": "PBS LearningMedia: Civil Rights and Birmingham",
                "url": "https://www.pbslearningmedia.org/resource/midlit11.soc.spl.birmlit/the-childrens-crusade/",
            },
            {
                "label": "TED: The Power of Youth Activism",
                "url": "https://www.ted.com/topics/youth+activism",
            },
        ],
    },
}
_RESOURCE_CACHE: Dict[Tuple[Tuple[str, ...], Tuple[str, ...], int], List[Dict[str, str]]] = {}


def _cache_key(terms: Iterable[str], media: Iterable[str], limit: int) -> Tuple[Tuple[str, ...], Tuple[str, ...], int]:
    term_tuple = tuple(sorted({str(term).strip().lower() for term in terms if str(term).strip()}))
    media_tuple = tuple(sorted({str(m).strip().lower() for m in media if str(m).strip()}))
    return term_tuple, media_tuple, int(limit)


def _discover_dynamic_resources(
    search_terms: Iterable[str],
    preferred_media: Iterable[str],
    limit: int,
) -> List[Dict[str, str]]:
    normalised_terms = [term for term in {str(t).strip() for t in search_terms if str(t).strip()}]
    if not normalised_terms:
        return []

    key = _cache_key(normalised_terms, preferred_media, limit)
    if key in _RESOURCE_CACHE:
        cached = _RESOURCE_CACHE[key]
        return [dict(item) for item in cached[:limit]]

    try:
        discovered = RESOURCE_FINDER.find_resources(normalised_terms, preferred_media, limit=limit)
    except Exception:  # pragma: no cover - defensive guard against upstream failures
        discovered = []

    _RESOURCE_CACHE[key] = discovered
    return [dict(item) for item in discovered[:limit]]


def _map_interest_modes_to_media(modes: Iterable[str]) -> List[str]:
    mapping = {
        "debates": "video",
        "stories": "article",
        "data": "interactive",
        "maps": "interactive",
        "design": "guide",
        "art": "interactive",
        "action": "guide",
    }
    media: List[str] = []
    for mode in modes:
        label = mapping.get(str(mode).lower())
        if label and label not in media:
            media.append(label)
    return media


_DEFAULT_STAGE_MEDIA = {
    "launch_connect": ["article", "guide", "video"],
    "investigate": ["article", "video", "interactive", "audio"],
    "create": ["guide", "interactive", "video", "audio"],
}

_STAGE_RESOURCE_TARGETS = {
    "launch_connect": 3,
    "investigate": 4,
    "create": 3,
}

_PERSONALIZED_RESOURCE_TEMPLATES = {
    "launch_connect": [
        {
            "format": "article",
            "title": "Story Starter: Why {topic} Matters",
            "description": "A short narrative that introduces real people connected to {topic} so you can connect emotionally before diving deeper.",
        },
        {
            "format": "video",
            "title": "Video Explainer on {topic}",
            "description": "A 3-minute clip highlighting key background facts about {topic} to spark questions for your inquiry notebook.",
        },
        {
            "format": "interactive",
            "title": "Question Builder for {topic}",
            "description": "An interactive prompt set that helps you jot compelling and supporting questions about {topic}.",
        },
    ],
    "investigate": [
        {
            "format": "article",
            "title": "Source Set: Evidence About {topic}",
            "description": "A curated trio of articles summarizing perspectives, timelines, and key facts you can cite when studying {topic}.",
        },
        {
            "format": "video",
            "title": "Documentary Clip on {topic}",
            "description": "A short investigative segment that shows events, voices, or data connected to {topic}.",
        },
        {
            "format": "interactive",
            "title": "Data Explorer: Trends in {topic}",
            "description": "Interactive charts that let you analyze statistics and patterns tied to {topic}.",
        },
        {
            "format": "audio",
            "title": "Student Voices Podcast on {topic}",
            "description": "A mini-podcast episode with interviews or storytelling about {topic} to use as qualitative evidence.",
        },
    ],
    "create": [
        {
            "format": "guide",
            "title": "Action Blueprint: Communicating About {topic}",
            "description": "Step-by-step guide to help you plan how to share what you learned about {topic} with an authentic audience.",
        },
        {
            "format": "interactive",
            "title": "Storyboard Planner for {topic}",
            "description": "Drag-and-drop storyboard prompts to organize visuals, data, and narration for your {topic} product.",
        },
        {
            "format": "video",
            "title": "Mini Workshop: Presenting {topic}",
            "description": "Coaching video that models how to explain findings and next steps about {topic}.",
        },
    ],
    "default": [
        {
            "format": "article",
            "title": "Background Brief: {topic}",
            "description": "Quick overview that grounds your inquiry in the key facts and debates surrounding {topic}.",
        },
        {
            "format": "guide",
            "title": "Strategy Guide: Investigating {topic}",
            "description": "Tips for collecting evidence, organizing notes, and planning next steps focused on {topic}.",
        },
        {
            "format": "video",
            "title": "Student Perspective on {topic}",
            "description": "Learner-friendly video showing how peers explore and communicate about {topic}.",
        },
    ],
}

_TEACHER_ONLY_KEYWORDS = {
    "teacher guide",
    "teacher's guide",
    "teachers guide",
    "lesson plan",
    "instructional guide",
    "educator guide",
    "professional learning",
    "teacher edition",
    "teacher notes",
    "teacher resource",
    "teacher packet",
    "curriculum guide",
}

_STAGE_QUERY_BOOST = {
    "launch_connect": [
        ["youth civic participation", "student activism community action"],
        ["student voice stories", "youth advocacy reflection"],
    ],
    "investigate": [
        ["youth protest video", "student activism documentary"],
        ["youth civic podcast", "student-led movement timeline"],
        ["youth activism evidence", "student protest data"],
        ["student walkout news clip", "youth activism YouTube"],
        ["PBS NewsHour student walkout", "March for Our Lives video"],
    ],
    "create": [
        ["youth advocacy toolkit", "student action plan template"],
        ["civic proposal guide", "youth presentation tips"],
        ["school safety action plan", "youth gun violence prevention toolkit"],
    ],
}


def _tokenise(text: str) -> List[str]:
    if not text:
        return []
    return [tok for tok in re.findall(r"[A-Za-z']+", text.lower()) if tok]


def _resource_available(url: Optional[str]) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    if not parsed.scheme:
        return True
    headers = {"User-Agent": "Mozilla/5.0 (compatible; C3ResourceBot/1.0)"}
    try:
        req = urllib.request.Request(url, method="HEAD", headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            return 200 <= getattr(resp, "status", 200) < 400
    except urllib.error.HTTPError as exc:
        if exc.code == 405:  # Method not allowed, try lightweight GET
            try:
                req = urllib.request.Request(url, method="GET", headers=headers)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    resp.read(512)
                    return 200 <= getattr(resp, "status", 200) < 400
            except Exception:
                return False
        return False
    except Exception:
        return False


_ALLOWED_RESOURCE_FORMATS = {"article", "video", "audio", "interactive", "guide"}
_VIDEO_HINTS = {"youtube.com", "youtu.be", "vimeo.com", "video", "ted.com", "pbs.org/video"}
_AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg")
_VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".webm")
_GUIDE_EXTS = (".pdf", ".doc", ".docx", ".ppt", ".pptx")


def _normalise_resource_format(url: str, declared: Optional[str]) -> str:
    fmt = (declared or "").lower().strip()
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()

    if path.endswith(_GUIDE_EXTS):
        return "guide"

    if path.endswith(_VIDEO_EXTS) or any(hint in netloc for hint in _VIDEO_HINTS):
        return "video"

    if path.endswith(_AUDIO_EXTS) or any(token in netloc for token in ["soundcloud.com", "spotify.com", "podcast", "podbean.com"]):
        return "audio"

    if fmt == "interactive" and any(keyword in (path + netloc) for keyword in ["interactive", "simulation", "game", "map"]):
        return "interactive"

    if fmt not in _ALLOWED_RESOURCE_FORMATS:
        return "article"

    if fmt == "video" and not path.endswith(_VIDEO_EXTS) and not any(hint in netloc for hint in _VIDEO_HINTS):
        return "article"

    if fmt == "audio" and not (path.endswith(_AUDIO_EXTS) or any(token in netloc for token in ["podcast", "soundcloud", "spotify.com"])):
        return "article"

    return fmt or "article"


def _normalise_resource_entry(raw: Dict[str, object]) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict):
        return None
    url = str(raw.get("url", "")).strip()
    if not url:
        return None
    title = str(raw.get("title", "")).strip()
    description = str(raw.get("description", "")).strip()
    source = str(raw.get("source", "")).strip()
    fmt = _normalise_resource_format(url, raw.get("format"))
    if not title:
        parsed = urlparse(url)
        title = parsed.netloc or "Resource"
    if not source:
        parsed = urlparse(url)
        source = parsed.netloc
    return {
        "title": title,
        "url": url,
        "description": description,
        "format": fmt,
        "source": source,
    }


def _categorise_terms(
    keywords: List[str],
    exemplar_infos: List[Dict[str, str]],
    interest_topics: str,
    interest_modes: List[str],
    additional_texts: Optional[List[str]] = None,
) -> List[str]:
    categories: set[str] = set()
    tokens = []
    for source in keywords:
        tokens.extend(_tokenise(source))
    tokens.extend(_tokenise(interest_topics))
    for info in exemplar_infos:
        tokens.extend(_tokenise(info.get("title", "")))
        tokens.extend(_tokenise(info.get("description", "")))
    if additional_texts:
        for text in additional_texts:
            tokens.extend(_tokenise(text))

    tokens_set = set(tokens)
    if any(tok in tokens_set for tok in {"climate", "carbon", "environment", "warming"}):
        categories.add("climate")
    if any(tok in tokens_set for tok in {"water", "river", "clean", "pipeline"}):
        categories.add("water")
    if any(tok in tokens_set for tok in {"hunger", "food", "nutrition", "meal"}):
        categories.add("hunger")
    if any(tok in tokens_set for tok in {"gun", "violence", "safety"}):
        categories.add("gun_violence")
    if any(tok in tokens_set for tok in {"justice", "equity", "rights"}):
        categories.add("justice")
    if any(tok in tokens_set for tok in {"community", "neighborhood", "local"}):
        categories.add("local_community")
    if any(tok in tokens_set for tok in {"youth", "student", "teen"}):
        categories.add("youth_voice")

    if interest_modes:
        if any(mode in {"design", "action", "debates", "stories"} for mode in interest_modes):
            categories.add("civic_action")

    categories.add("general")
    return list(categories)


def _gather_search_terms(
    categories: List[str],
    keywords: List[str],
    exemplar_infos: List[Dict[str, str]],
    interest_topics: str,
    additional_texts: Iterable[str],
    stage_type: str,
) -> List[str]:
    collected: List[str] = []
    seen: set[str] = set()

    def add_tokens(source: object) -> None:
        if not source:
            return
        for token in _tokenise(str(source)):
            if token not in seen:
                seen.add(token)
                collected.append(token)

    for category in categories:
        add_tokens(category)

    add_tokens(interest_topics)

    for keyword in keywords:
        add_tokens(keyword)

    for exemplar in exemplar_infos:
        add_tokens(exemplar.get("title", ""))
        add_tokens(exemplar.get("description", ""))

    for text in additional_texts:
        add_tokens(text)

    stage_keywords = {
        "launch_connect": [
            "civic participation",
            "student activism stories",
            "community organizing",
            "youth civic engagement reflection",
        ],
        "investigate": [
            "youth protest video",
            "student activism evidence",
            "youth civic podcast",
            "youth activism timeline",
        ],
        "create": [
            "youth advocacy toolkit",
            "student action plan template",
            "letter to decision makers example",
            "youth presentation guide",
        ],
    }
    for token in stage_keywords.get(stage_type, []):
        add_tokens(token)

    return collected[:20]


def _resource_relevant(entry: Dict[str, str], stage_type: str, focus_terms: Iterable[str]) -> bool:
    text = f"{entry.get('title', '')} {entry.get('description', '')}".lower()
    focus_terms = [term for term in (focus_terms or []) if term]
    focus_hit = True
    if focus_terms:
        focus_hit = any(term in text for term in focus_terms)

    stage_signals = {
        "launch_connect": {"story", "overview", "introduction", "context", "question", "community"},
        "investigate": {"evidence", "analysis", "timeline", "interview", "data", "report", "documentary", "source", "research"},
        "create": {"guide", "template", "toolkit", "plan", "presentation", "product", "communicate", "action"},
    }

    signals = stage_signals.get(stage_type)
    stage_hit = True if not signals else any(token in text for token in signals)
    return stage_hit and focus_hit


def _is_student_facing(entry: Dict[str, str]) -> bool:
    text = f"{entry.get('title', '')} {entry.get('description', '')} {entry.get('source', '')}".lower()
    url = (entry.get("url") or "").lower()
    for keyword in _TEACHER_ONLY_KEYWORDS:
        if keyword in text or keyword in url:
            return False
    if "teacher" in url and "student" not in text:
        return False
    return True


def _collect_resources(
    categories: List[str],
    search_terms: List[str],
    interest_modes: List[str],
    stage_type: str,
    exclude_titles: Optional[set[str]] = None,
    limit: int = 8,
    ensure_multimodal: bool = False,
    focus_terms: Optional[Iterable[str]] = None,
    interest_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    seen = set(exclude_titles or set())
    selected: List[Dict[str, str]] = []
    formats_seen: set[str] = set()

    def maybe_add(item: Dict[str, object], *, enforce_relevance: bool = True) -> None:
        entry = _normalise_resource_entry(item)
        if not entry:
            return
        title = entry.get("title")
        if not title or title in seen:
            return
        fmt = entry.get("format", "article").lower()
        if ensure_multimodal and len(formats_seen) < 4 and fmt in formats_seen:
            return
        if not _resource_available(entry.get("url")):
            return
        if not _is_student_facing(entry):
            return
        if enforce_relevance and not _resource_relevant(entry, stage_type, focus_terms):
            return
        selected.append(entry)
        seen.add(title)
        formats_seen.add(fmt)

    include_curated = not interest_context
    if include_curated:
        for category in categories:
            for item in CURATED_RESOURCE_LIBRARY.get(category, []):
                maybe_add(item)
                if len(selected) >= limit:
                    return selected

    if include_curated and ensure_multimodal and len(formats_seen) < 4:
        for item in CURATED_RESOURCE_LIBRARY.get("general", []):
            maybe_add(item)
            if len(formats_seen) >= 4 or len(selected) >= limit:
                break

    if include_curated and len(selected) < limit:
        for item in CURATED_RESOURCE_LIBRARY.get("general", []):
            maybe_add(item)
            if len(selected) >= limit:
                break

    preferred_media = _map_interest_modes_to_media(interest_modes)
    for default_medium in _DEFAULT_STAGE_MEDIA.get(stage_type, []):
        if default_medium not in preferred_media:
            preferred_media.append(default_medium)

    context_terms = []
    if interest_context:
        context_terms.append(interest_context)
    for term in (focus_terms or []):
        if term and term not in context_terms:
            context_terms.append(term)

    if len(selected) < limit:
        dynamic = _discover_dynamic_resources(search_terms, preferred_media, limit)
        for item in dynamic:
            maybe_add(item)
            if len(selected) >= limit:
                break

    if ensure_multimodal:
        required_formats = {"article", "video", "audio", "interactive"}
        missing_formats = required_formats - formats_seen
        for fmt in missing_formats:
            if len(selected) >= limit:
                break
            targeted = _discover_dynamic_resources(search_terms + [fmt], [fmt], limit)
            for item in targeted:
                maybe_add(item)
                if len(selected) >= limit or fmt in formats_seen:
                    break

    desired = _STAGE_RESOURCE_TARGETS.get(stage_type, limit)
    if len(selected) < desired:
        for query_group in _STAGE_QUERY_BOOST.get(stage_type, []):
            extended_terms = list(search_terms) + query_group + context_terms
            targeted = _discover_dynamic_resources(extended_terms, preferred_media, limit)
            for item in targeted:
                maybe_add(item)
                if len(selected) >= desired:
                    break
            if len(selected) >= desired:
                break

    if len(selected) < desired:
        for query_group in _STAGE_QUERY_BOOST.get(stage_type, []):
            extended_terms = list(search_terms) + query_group + context_terms
            targeted = _discover_dynamic_resources(extended_terms, preferred_media, limit)
            for item in targeted:
                maybe_add(item, enforce_relevance=False)
                if len(selected) >= desired:
                    break
            if len(selected) >= desired:
                break

    if len(selected) < desired:
        personalized = _build_personalized_resource_pack(
            stage_type,
            interest_context,
            focus_terms,
            desired - len(selected),
        )
        for item in personalized:
            maybe_add(item, enforce_relevance=False)
            if len(selected) >= desired:
                break

    return selected


def _interest_topic_label(interest_context: Optional[str], focus_terms: Optional[Iterable[str]]) -> str:
    context = str(interest_context or "").strip()
    if context:
        return context
    ordered: List[str] = []
    for term in focus_terms or []:
        token = str(term or "").strip()
        if not token:
            continue
        if token not in ordered:
            ordered.append(token)
        if len(ordered) >= 4:
            break
    if ordered:
        return " ".join(ordered)
    return "your civic question"


def _build_personalized_resource_pack(
    stage_type: str,
    interest_context: Optional[str],
    focus_terms: Optional[Iterable[str]],
    count: int,
) -> List[Dict[str, str]]:
    topic_label = _interest_topic_label(interest_context, focus_terms)
    title_topic = topic_label.title()
    description_topic = topic_label
    templates = _PERSONALIZED_RESOURCE_TEMPLATES.get(stage_type, _PERSONALIZED_RESOURCE_TEMPLATES["default"])
    generated: List[Dict[str, str]] = []
    idx = 0
    while len(generated) < count:
        template = templates[idx % len(templates)]
        generated.append(
            {
                "title": template["title"].format(topic=title_topic),
                "description": template["description"].format(topic=description_topic),
                "url": "",
                "format": template["format"],
                "source": "C3 Personalized Pack",
            }
        )
        idx += 1
    return generated


def _resolve_exemplar_details(selected_titles: List[str], ai_suggestions: List[Dict[str, str]]) -> List[Dict[str, str]]:
    selected_clean = []
    seen = set()
    for title in selected_titles:
        if title and title not in seen:
            selected_clean.append(title)
            seen.add(title)

    plan = active_plan()

    def find_match(title: str) -> Optional[Dict[str, str]]:
        for candidate in ai_suggestions:
            if candidate.get("title") == title:
                return candidate
        for candidate in plan.get("exemplars", []):
            if candidate.get("title") == title:
                return candidate
        return None

    details = []
    for title in selected_clean:
        match = find_match(title)
        if match:
            details.append(match)
    if not details and ai_suggestions:
        details = ai_suggestions[:1]
    return details


def _standard_focus_terms(plan: Dict[str, object]) -> List[str]:
    tokens: List[str] = []
    plan_questions = plan.get("questions", {}) or {}
    title = plan.get("title")
    if title:
        tokens.extend(_tokenise(title))
    compelling = plan_questions.get("compelling")
    if compelling:
        tokens.extend(_tokenise(compelling))
    for concept in plan.get("focus_concepts", []) or []:
        tokens.extend(_tokenise(concept))
    for standard in plan.get("required_standards", []) or []:
        tokens.extend(_tokenise(standard))
    ordered: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _interest_focus_terms(interests: Dict[str, object]) -> List[str]:
    topics = interests.get("topic_focus", "")
    keywords = interests.get("keywords", [])
    tokens = _tokenise(topics)
    for kw in keywords or []:
        tokens.extend(_tokenise(kw))
    ordered: List[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def _resource_matches_standard_interest(
    entry: Dict[str, str],
    standard_terms: Iterable[str],
    interest_terms: Iterable[str],
) -> bool:
    text = f"{entry.get('title', '')} {entry.get('description', '')}".lower()

    def has_terms(terms: Iterable[str]) -> bool:
        filtered = [term for term in terms if term]
        if not filtered:
            return True
        return any(term in text for term in filtered)

    return has_terms(standard_terms) and has_terms(interest_terms)


def _build_stage_resource_context(
    stage: Dict[str, object],
    plan: Dict[str, object],
    interests: Dict[str, object],
    exemplar_infos: List[Dict[str, str]],
    standard_terms: List[str],
    interest_terms: List[str],
) -> Dict[str, object]:
    stage_type = str(stage.get("type") or "").lower() or "custom"
    ensure_multimodal = stage_type == "investigate"
    limit = 6 if stage_type == "investigate" else 4
    desired = _STAGE_RESOURCE_TARGETS.get(stage_type, limit)
    keywords = interests.get("keywords", []) or []
    if isinstance(keywords, str):
        keywords = [keywords]
    interest_topics = (interests.get("topic_focus") or "").strip()
    interest_modes = interests.get("interest_modes") or []
    if isinstance(interest_modes, str):
        interest_modes = [interest_modes]
    plan_questions = plan.get("questions", {}) or {}
    additional_texts: List[str] = []
    additional_texts.append(stage.get("title", ""))
    additional_texts.append(stage.get("prompt", ""))
    additional_texts.extend(stage.get("keywords", []) or [])
    additional_texts.extend(stage.get("activities", []) or [])
    additional_texts.extend(stage.get("product_suggestions", []) or [])
    additional_texts.extend(stage.get("student_questions", []) or [])
    additional_texts.extend(plan_questions.get("supporting", []) or [])
    compelling = plan_questions.get("compelling")
    if compelling:
        additional_texts.append(compelling)

    categories = _categorise_terms(
        keywords,
        exemplar_infos,
        interest_topics,
        interest_modes,
        additional_texts=additional_texts,
    )
    search_terms = _gather_search_terms(
        categories,
        keywords,
        exemplar_infos,
        interest_topics,
        additional_texts,
        stage_type,
    )
    focus_terms = list(dict.fromkeys([*standard_terms, *interest_terms]))
    return {
        "stage_type": stage_type,
        "ensure_multimodal": ensure_multimodal,
        "limit": limit,
        "desired": desired,
        "interest_context": interest_topics,
        "categories": categories,
        "search_terms": search_terms,
        "interest_modes": interest_modes,
        "focus_terms": focus_terms,
    }


def _ensure_stage_resources_align(path: Dict[str, object], plan: Dict[str, object], interests: Dict[str, object]) -> Dict[str, object]:
    stages = path.get("stages", [])
    if not stages:
        return path
    standard_terms = _standard_focus_terms(plan)
    interest_terms = _interest_focus_terms(interests)
    selected_exemplars = interests.get("selected_exemplars", [])
    ai_suggestions = interests.get("ai_suggestions", [])
    exemplar_infos = _resolve_exemplar_details(selected_exemplars, ai_suggestions)

    for stage in stages:
        if not isinstance(stage, dict):
            continue
        context = _build_stage_resource_context(
            stage,
            plan,
            interests,
            exemplar_infos,
            standard_terms,
            interest_terms,
        )
        resources = stage.get("resources", []) or []
        valid: List[Dict[str, str]] = []
        seen_titles: set[str] = set()
        for item in resources:
            entry = _normalise_resource_entry(item)
            if not entry:
                continue
            title = entry["title"]
            if title in seen_titles:
                continue
            if not _is_student_facing(entry):
                continue
            if not _resource_matches_standard_interest(entry, standard_terms, interest_terms):
                continue
            valid.append(entry)
            seen_titles.add(title)

        original_count = len(resources)
        target = max(context["desired"], original_count)
        needed = target - len(valid)

        if needed > 0:
            replenish = _collect_resources(
                context["categories"],
                context["search_terms"],
                context["interest_modes"],
                context["stage_type"],
                exclude_titles=seen_titles,
                limit=max(context["limit"], needed + len(valid)),
                ensure_multimodal=context["ensure_multimodal"],
                focus_terms=context["focus_terms"],
                interest_context=context["interest_context"],
            )
            for item in replenish:
                if len(valid) >= target:
                    break
                if item["title"] in seen_titles:
                    continue
                if not _resource_matches_standard_interest(item, standard_terms, interest_terms):
                    continue
                valid.append(item)
                seen_titles.add(item["title"])

        if valid:
            stage["resources"] = valid
        else:
            stage["resources"] = _build_personalized_resource_pack(
                context["stage_type"],
                context["interest_context"],
                context["focus_terms"],
                context["desired"],
            )
    return path


def _personalise_learning_path(path: Dict[str, object], interests: Dict[str, object]) -> Dict[str, object]:
    if not path:
        return path

    plan = active_plan()
    plan_questions = plan.get("questions", {}) or {}

    selected_exemplars = interests.get("selected_exemplars", [])
    ai_suggestions = interests.get("ai_suggestions", [])
    interest_topics = interests.get("topic_focus", "")
    interest_modes = interests.get("interest_modes", [])
    if isinstance(interest_modes, str):
        interest_modes = [interest_modes]
    keywords = interests.get("keywords", [])

    exemplar_infos = _resolve_exemplar_details(selected_exemplars, ai_suggestions)

    stages = path.get("stages", []) or []
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue

        stage.setdefault("id", f"stage-{index + 1}")
        stage_type = (stage.get("type") or "").lower()
        title_lower = str(stage.get("title", "")).lower()
        prompt_lower = str(stage.get("prompt", "")).lower()

        if not stage_type:
            if "launch" in title_lower or "connect" in title_lower:
                stage_type = "launch_connect"
            elif "invest" in title_lower or "evidence" in prompt_lower or "source" in title_lower:
                stage_type = "investigate"
            elif "create" in title_lower or "product" in prompt_lower:
                stage_type = "create"
            elif "primer" in title_lower:
                stage_type = "primer"
            stage["type"] = stage_type

        if stage_type not in {"launch_connect", "investigate", "create"}:
            continue

        additional_texts: List[str] = []
        additional_texts.append(stage.get("title", ""))
        additional_texts.append(stage.get("prompt", ""))
        additional_texts.extend(stage.get("keywords", []) or [])
        additional_texts.extend(stage.get("activities", []) or [])
        additional_texts.extend(stage.get("product_suggestions", []) or [])
        additional_texts.extend(stage.get("student_questions", []) or [])
        additional_texts.extend(plan_questions.get("supporting", []))
        compelling_question_text = plan_questions.get("compelling")
        if compelling_question_text:
            additional_texts.append(compelling_question_text)

        categories = _categorise_terms(
            keywords,
            exemplar_infos,
            interest_topics,
            interest_modes,
            additional_texts=additional_texts,
        )

        search_terms = _gather_search_terms(
            categories,
            keywords,
            exemplar_infos,
            interest_topics,
            additional_texts,
            stage_type,
        )

        ensure_multimodal = stage_type == "investigate"
        limit = 6 if stage_type == "investigate" else 4
        existing_resources: List[Dict[str, str]] = []
        existing_titles: set[str] = set()
        for item in stage.get("resources", []) or []:
            if not isinstance(item, dict):
                continue
            entry = _normalise_resource_entry(item)
            if not entry:
                continue
            if not _resource_available(entry["url"]):
                continue
            existing_titles.add(entry["title"])
            existing_resources.append(entry)

        focus_terms = {tok.lower() for tok in keywords if tok}
        focus_terms.update(_tokenise(interest_topics))
        for exemplar in exemplar_infos:
            focus_terms.update(_tokenise(exemplar.get("title", "")))
            focus_terms.update(_tokenise(exemplar.get("description", "")))

        discovered = _collect_resources(
            categories,
            search_terms,
            interest_modes,
            stage_type,
            exclude_titles=existing_titles,
            limit=limit,
            ensure_multimodal=ensure_multimodal,
            focus_terms=list(focus_terms),
            interest_context=interest_topics,
        )

        combined: List[Dict[str, str]] = list(existing_resources)
        for item in discovered:
            if len(combined) >= limit:
                break
            combined.append(item)

        if combined:
            stage["resources"] = combined

    return path


def highlight_vocab(text: str) -> Markup:
    if not text:
        return Markup("")
    vocab_defs = active_vocab_defs()
    if not vocab_defs:
        return Markup(escape(text))
    pattern = re.compile(r"\\b(" + "|".join(map(re.escape, vocab_defs.keys())) + r")\\b", re.IGNORECASE)

    def replacer(match: re.Match[str]) -> str:
        word = match.group(0)
        lookup_key = word.lower()
        definition = vocab_defs.get(lookup_key, vocab_defs.get(word, ""))
        return f'<span class="vocab" data-definition="{escape(definition)}">{word}</span>'

    highlighted = pattern.sub(replacer, str(escape(text)))
    return Markup(highlighted)


def fallback_question(prompt: str) -> str:
    counter = session.get("question_counter", 0)
    plan = active_plan()
    concepts = plan.get("focus_concepts") or ["the concept"]
    concept = concepts[counter % len(concepts)]
    concept_text = str(concept)
    templates = [
        "How does {concept} shape choices people make in different communities?",
        "Why does understanding {concept} help us take informed action?",
        "What questions would you ask to spot {concept} in the world around you?",
        "How might {concept} look the same or different across time and place?",
    ]
    template = templates[counter % len(templates)]
    question = template.format(concept=concept_text.lower())
    session["question_counter"] = counter + 1
    return question


def fallback_exemplar_suggestions(keywords: List[str]) -> List[Dict[str, str]]:
    joined = ", ".join(keywords[:2]) if keywords else "youth civic priority issues"
    return [
        {
            "id": "exemplar.student_voice",
            "title": "Student Voice Town Hall",
            "description": (
                "Plan a student-led forum that surfaces community challenges and proposes solutions to decision makers."
                " Connect the discussion to evidence you gather about why {focus} matters."
            ).format(focus=joined),
            "era_or_setting": "Contemporary school or district community",
            "discipline_emphasis": "Civics / Public Policy",
        },
        {
            "id": "exemplar.community_audit",
            "title": "Community Change Evidence Audit",
            "description": (
                "Investigate local articles, interviews, and data to see how youth activism influences {focus}."
            ).format(focus=joined),
            "era_or_setting": "Local community investigation",
            "discipline_emphasis": "History / Civics",
        },
        {
            "id": "exemplar.compare_movements",
            "title": "Compare Two Youth Movements",
            "description": "Select two youth-led campaigns from different contexts and map how their strategies align with the lesson concepts.",
            "era_or_setting": "Cross-era comparative study",
            "discipline_emphasis": "History / Global Studies",
        },
    ]


def _decode_jsonish_block(text: str) -> Optional[object]:
    cleaned = text.strip()
    if not cleaned:
        return None
    if cleaned.startswith("```"):
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if fence:
            cleaned = fence.group(1).strip()
    cleaned = cleaned.replace("“", '"').replace("”", '"')
    attempts = [cleaned]
    without_trailing = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    if without_trailing != cleaned:
        attempts.append(without_trailing)
    for candidate in attempts:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    try:
        return ast.literal_eval(without_trailing)
    except Exception:
        return None


def _prepare_interest_suggestions(raw: Optional[Iterable[object]]) -> List[Dict[str, str]]:
    suggestions: List[Dict[str, str]] = []
    if not raw:
        return suggestions

    def _strip_quotes(value: object) -> str:
        text = str(value or "").strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            return text[1:-1].strip()
        return text

    def add_entry(entry: Dict[str, object]) -> None:
        raw_title = entry.get("title")
        raw_description = entry.get("description")

        blob_parts: List[str] = []
        for part in (raw_title, raw_description):
            text = str(part or "").strip()
            if not text:
                continue
            if text.startswith("```") or ('"id"' in text and "[" in text):
                blob_parts.append(text)
        if blob_parts:
            decoded = _decode_jsonish_block("\n".join(blob_parts))
            if decoded is not None:
                handle_candidate(decoded)
                return

        title = _strip_quotes(raw_title)
        if not title:
            return

        description = _strip_quotes(raw_description)
        era = _strip_quotes(entry.get("era_or_setting"))
        discipline = _strip_quotes(entry.get("discipline_emphasis"))

        suggestions.append(
            {
                "id": entry.get("id") or f"exemplar.ai-{len(suggestions) + 1}",
                "title": title,
                "description": description,
                "era_or_setting": era or None,
                "discipline_emphasis": discipline or None,
            }
        )

    def handle_candidate(candidate: object) -> None:
        if isinstance(candidate, dict):
            add_entry(candidate)
        elif isinstance(candidate, list):
            for item in candidate:
                handle_candidate(item)
        elif isinstance(candidate, str):
            parsed = _decode_jsonish_block(candidate)
            if parsed is None:
                return
            if isinstance(parsed, str) and parsed.strip() == candidate.strip():
                return
            handle_candidate(parsed)

    for item in raw:
        handle_candidate(item)

    return suggestions


def fallback_learning_path(interests: Dict[str, object], student_state: Dict[str, object]) -> Dict[str, object]:
    plan = active_plan()
    plan_questions = plan.get("questions", {}) or {}
    interest_topics = (interests.get("topic_focus") or "the issues you care about").strip()
    selected_exemplars = interests.get("selected_exemplars") or []
    ai_suggestions = interests.get("ai_suggestions") or []
    learning_modes = interests.get("learning_mode") or []
    if isinstance(learning_modes, str):
        learning_modes = [learning_modes]
    support_pref = interests.get("support_preference") or "balance"
    keywords = [kw for kw in interests.get("keywords", []) if kw]
    interest_modes = interests.get("interest_modes") or []
    primers = plan.get("prerequisite_status", {}).get("primers", [])
    student_questions = student_state.get("questions", [])

    exemplar_infos = _resolve_exemplar_details(selected_exemplars, ai_suggestions)

    mode_phrases = {
        "debates": "live debates",
        "stories": "story-driven examples",
        "data": "data dives",
        "maps": "maps & visuals",
        "design": "solution design",
        "art": "creative media",
        "action": "civic action planning",
    }
    preferred_modes = [mode_phrases.get(mode, mode) for mode in interest_modes]
    mode_text = ", ".join(preferred_modes) if preferred_modes else "a mix of experiences"
    learning_mode_text = ", ".join(mode_phrases.get(mode, mode) for mode in learning_modes) if learning_modes else "blended activities"

    summary = (
        "This path keeps the focus on {} while connecting what we learn to {}. "
        "You’ll explore through {} and wrap each step with a {} level of guidance.".format(
            plan_questions.get("compelling", "our compelling question"),
            interest_topics,
            learning_mode_text,
            "step-by-step" if support_pref == "structure" else ("self-directed" if support_pref == "independent" else "balanced"),
        )
    )

    base_keywords = [kw for kw in (keywords or [interest_topics]) if kw]

    stages: List[Dict[str, object]] = []

    if primers:
        stages.append(
            {
                "id": "stage-primer",
                "type": "primer",
                "title": "Quick primer",
                "purpose": "Close any prerequisite gaps before diving into your personalised path.",
                "activities": [primer for primer in primers[:3]],
                "resources": [],
                "checkpoint": "Capture one insight from the primer that will guide your analysis.",
                "prompt": "Skim these prompts so you can jump into the inquiry with confidence.",
                "student_questions": [],
                "keywords": plan.get("focus_concepts", []),
                "product_suggestions": [],
            }
        )

    stages.append(
        {
            "id": "stage-launch",
            "type": "launch_connect",
            "title": "Launch & connect",
            "purpose": "Activate what you know and set a direction based on your interests.",
            "prompt": "Choose one of your questions below and explain what you currently think or notice about it.",
            "student_questions": student_questions,
            "activities": [
                "Skim your earlier questions and highlight one you want to answer today.",
                "List what you already know about {}.".format(interest_topics if interest_topics else "this topic"),
                *("Identify a person or community story connected to your question." for _ in [1] if "stories" in interest_modes),
                *("Decide what evidence or data would convince you your answer is solid." for _ in [1] if "data" in interest_modes),
            ],
            "resources": [],
            "checkpoint": "Post a quick note describing how your question connects to your interests.",
            "keywords": base_keywords[:6],
            "product_suggestions": [],
        }
    )

    stages.append(
        {
            "id": "stage-investigate",
            "type": "investigate",
            "title": "Investigate your exemplars",
            "purpose": "Dig into the contexts you selected and collect targeted evidence.",
            "prompt": "Write a claim + evidence statement that connects your example(s) to the compelling question.",
            "activities": [
                "Use your chosen example{} to gather evidence about {}.".format(
                    "s" if len(exemplar_infos) != 1 else "",
                    plan_questions.get("compelling", "the compelling question"),
                ),
                "Capture quotes, observations, or data that stand out to you.",
                *("Sketch or map the key relationships you notice." for _ in [1] if "visual" in learning_modes or "maps" in interest_modes),
                *("Record a 60-second voice note explaining your findings so far." for _ in [1] if "debates" in interest_modes or "speaking" in learning_modes),
            ],
            "resources": [],
            "checkpoint": "Create a claim + evidence statement that answers part of your question.",
            "student_questions": [],
            "keywords": base_keywords[:6],
            "product_suggestions": [],
        }
    )

    creation_activities = [
        "Synthesize what you found into a short product that matches your style (see options below).",
    ]
    if "art" in interest_modes:
        creation_activities.append("Design a mini-poster or storyboard showing how youth drive change in your context.")
    if "design" in interest_modes or "action" in interest_modes:
        creation_activities.append("Draft a quick action idea inspired by your evidence (who, what, why).")
    if "writing" in learning_modes:
        creation_activities.append("Write a paragraph that answers your question with evidence and reasoning.")
    if "speaking" in learning_modes:
        creation_activities.append("Record an audio reflection explaining your claim and evidence.")

    product_suggestions = []
    if "art" in interest_modes:
        product_suggestions.append("Design an illustrated gallery walk or zine that explains your claim.")
    if "debates" in interest_modes or "speaking" in learning_modes:
        product_suggestions.append("Record a 60-second spoken reflection or mini-podcast highlighting your claim + evidence.")
    if "design" in interest_modes or "action" in interest_modes:
        product_suggestions.append("Draft a one-page proposal for an informed action inspired by your findings.")
    if "writing" in learning_modes:
        product_suggestions.append("Write a short op-ed paragraph that persuades your audience using your evidence.")
    if not product_suggestions:
        product_suggestions = [
            "Create a simple one-slide summary that states your claim and evidence.",
            "Build a quick infographic or timeline that shows how events connect to your claim.",
        ]

    stages.append(
        {
            "id": "stage-create",
            "type": "create",
            "title": "Create & communicate",
            "purpose": "Turn your evidence into a sharable claim or product.",
            "prompt": "Use one of the suggestions below (or your own idea) to produce a short product and explain how it answers your question.",
            "activities": creation_activities,
            "resources": [],
            "checkpoint": "Record how your product answers the compelling question and note the strongest evidence you used.",
            "student_questions": [],
            "keywords": base_keywords[:6],
            "product_suggestions": product_suggestions,
        }
    )

    path = {
        "summary": summary,
        "stages": stages,
        "mastery_tip": "Use a {} approach: pause at each checkpoint to relate new evidence back to {} and {}.".format(
            "step-by-step" if support_pref == "structure" else ("self-directed" if support_pref == "independent" else "balanced"),
            plan_questions.get("compelling", "the compelling question"),
            ", ".join(info.get("title", "your example") for info in exemplar_infos) or "your chosen examples",
        ),
        "next_focus": [],
    }

    if keywords:
        path["next_focus"].append(f"Collect additional evidence connected to {keywords[0]} and compare it with another context.")
    if exemplar_infos:
        path["next_focus"].append(
            "Explain how lessons from {} transfer to a current issue you notice.".format(exemplar_infos[0].get("title", "your exemplar"))
        )
    if not path["next_focus"]:
        path["next_focus"].append("Note one question you still have and plan how you might investigate it tomorrow.")

    return path

def generate_question_suggestion(prompt: str) -> str:
    if not LLM_CLIENT:
        return fallback_question(prompt)
    message_prompt = (
        "Suggest a student-friendly supporting inquiry question. "
        "It should focus on big ideas or concepts (not specific historical examples). "
        f"Keep it under 20 words. Compelling question: {prompt}."
    )
    try:
        suggestions = LLM_CLIENT.suggest_supporting_questions(message_prompt)
    except LLMUnavailable:
        return fallback_question(prompt)
    if not suggestions:
        return fallback_question(prompt)

    exemplar_terms = active_exemplar_terms()
    for candidate in suggestions:
        lowered = candidate.lower()
        if not any(term in lowered for term in exemplar_terms):
            return candidate
    return fallback_question(prompt)


@app.context_processor
def inject_plan_meta() -> Dict[str, object]:
    runtime = getattr(g, "plan_runtime", None)
    lesson_title = "Inquiry Planner"
    if runtime is not None:
        lesson_title = runtime.plan.get("title", lesson_title)
    elif has_request_context():
        plan_key = session.get("active_plan_key")
        if plan_key:
            runtime = active_plan_runtime()
            lesson_title = runtime.plan.get("title", lesson_title)
    return {
        "lesson_title": lesson_title,
        "highlight": highlight_vocab,
        "_prepare_interest_suggestions": _prepare_interest_suggestions,
    }


def get_student_state() -> Dict[str, object]:
    return {
        "questions": session.get("student_questions", []),
        "interests": session.get("student_interests", {}),
    }


def store_student_questions(questions: List[str]) -> None:
    session["student_questions"] = questions


def store_student_interests(data: Dict[str, object]) -> None:
    prepared = dict(data)
    prepared["ai_suggestions"] = _prepare_interest_suggestions(prepared.get("ai_suggestions"))
    session["student_interests"] = prepared


def reset_plan_progress() -> None:
    keys_to_clear = [
        "student_questions",
        "student_interests",
        "interest_suggestions",
        "interest_saved_message",
        "question_counter",
        "learning_path",
        "learning_path_source",
        "learning_feedback",
    ]
    for key in keys_to_clear:
        session.pop(key, None)
    session.modified = True


@app.route("/")
def catalog() -> str:
    catalog_data = get_michigan_catalog(MICHIGAN_ONTOLOGY_DIR)
    selected = session.get("selected_standard") or {}
    selected_code = selected.get("full_code")

    units: List[Dict[str, object]] = []
    for unit in catalog_data.units:
        discipline_map: Dict[str, Dict[str, object]] = {}
        for category in unit.categories:
            group = discipline_map.setdefault(
                category.discipline_label,
                {
                    "label": category.discipline_label,
                    "code": category.discipline_code,
                    "categories": [],
                },
            )
            group["categories"].append(category)

        discipline_entries: List[Dict[str, object]] = []
        for group in sorted(discipline_map.values(), key=lambda item: item["label"]):
            category_entries: List[Dict[str, object]] = []
            for category in group["categories"]:
                expectation_entries: List[Dict[str, object]] = []
                for expectation in category.expectations:
                    expectation_entries.append(
                        {
                            "full_code": expectation.full_code,
                            "code": expectation.code,
                            "label": expectation.text or expectation.label,
                            "is_selected": expectation.full_code == selected_code,
                        }
                    )
                category_entries.append(
                    {
                        "code": category.code,
                        "label": category.label,
                        "description": category.description,
                        "expectations": expectation_entries,
                    }
                )
            discipline_entries.append(
                {
                    "label": group["label"],
                    "code": group["code"],
                    "categories": category_entries,
                }
            )

        units.append(
            {
                "id": unit.id,
                "type": unit.type,
                "code": unit.code,
                "label": unit.label,
                "disciplines": discipline_entries,
            }
        )

    message = session.pop("selection_message", None)
    return render_template(
        "topic_catalog.html",
        catalog_units=units,
        selected_standard=selected if selected else None,
        selection_message=message,
    )


@app.post("/api/build-lesson")
def api_build_lesson():
    payload = request.get_json(silent=True) or {}
    expectation_code = str(payload.get("expectation_code", "")).strip()
    if not expectation_code:
        return jsonify({"error": "Expectation code is required."}), 400
    try:
        runtime, selection, question_seed, question_suggestions = build_lesson_from_expectation(expectation_code)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:  # pragma: no cover - defensive guard
        app.logger.exception("Failed to build lesson for %s", expectation_code)
        return jsonify({"error": "We couldn't complete that request. Please try again."}), 500

    return jsonify(
        {
            "message": f'Lesson "{runtime.plan.get("title", expectation_code)}" is ready for you.',
            "lesson_title": runtime.plan.get("title"),
            "redirect_url": url_for("overview"),
            "selection": selection,
            "question_seed": question_seed,
            "question_suggestions": question_suggestions,
        }
    )


@app.route("/resources/<slug>")
def resource_page(slug: str) -> str:
    page = CURATED_RESOURCE_PAGES.get(slug)
    if not page:
        abort(404)
    plan = active_plan()
    return render_template(
        "resource_page.html",
        page=page,
        plan=plan,
        student_state=get_student_state(),
    )


@app.route("/overview")
def overview() -> str:
    plan = active_plan()
    return render_template(
        "step_overview.html",
        plan=plan,
        student_state=get_student_state(),
    )


@app.route("/objectives", methods=["GET", "POST"])
def objectives() -> str:
    if request.method == "POST":
        raw = request.form.get("student_questions", "")
        questions = [line.strip() for line in raw.splitlines() if line.strip()]
        store_student_questions(questions)
        return redirect(url_for("interest_check"))

    plan = active_plan()
    student_state = get_student_state()
    question_suggestions = session.get("question_suggestions", [])
    first_question_seed = question_suggestions[0] if question_suggestions else ""
    return render_template(
        "step_objectives.html",
        plan=plan,
        student_state=student_state,
        question_seed=first_question_seed,
    )


@app.post("/api/suggest-question")
def api_suggest_question():
    plan = active_plan()
    prompt = request.form.get("prompt", plan.get("questions", {}).get("compelling", ""))
    suggestions = session.get("question_suggestions") or []
    if suggestions:
        index = session.get("question_suggestion_index", 0)
        question = suggestions[index % len(suggestions)]
        session["question_suggestion_index"] = index + 1
        session.modified = True
        return jsonify({"question": question})
    try:
        suggestion = generate_question_suggestion(prompt)
        return jsonify({"question": suggestion})
    except LLMUnavailable as exc:
        return jsonify({"error": str(exc)}), 503


@app.post("/api/interest-suggestions")
def api_interest_suggestions():
    payload = request.get_json(silent=True) or {}
    conversation = payload.get("conversation") or []
    keywords = payload.get("keywords") or []
    keywords = [str(item).strip() for item in keywords if str(item).strip()]

    suggestions: List[Dict[str, str]] = []
    if LLM_CLIENT:
        try:
            config = active_plan_config()
            ideas = LLM_CLIENT.suggest_exemplars(config, conversation, keywords)
            suggestions = [idea.to_dict() for idea in ideas]
        except LLMUnavailable:
            suggestions = []

    if not suggestions:
        suggestions = fallback_exemplar_suggestions(keywords)

    session["interest_suggestions"] = _prepare_interest_suggestions(suggestions)
    session.modified = True
    return jsonify({"suggestions": session["interest_suggestions"]})


@app.post("/api/learning-path")
def api_learning_path():
    payload = request.get_json(silent=True) or {}
    force_regenerate = bool(
        payload.get("force")
        or payload.get("force_regenerate")
        or payload.get("regenerate")
    )

    runtime = active_plan_runtime()
    plan = runtime.plan
    plan_config = runtime.config
    plan_questions = plan.get("questions", {}) or {}
    student_state = get_student_state()
    interests = student_state.get("interests", {})
    enriched_state = {
        **student_state,
        "plan_objectives": plan.get("objectives", []),
        "compelling_question": plan_questions.get("compelling"),
        "supporting_questions": plan_questions.get("supporting", []),
        "learning_tiles": plan.get("learning_tiles", []),
        "available_exemplars": plan.get("exemplars", []),
        "primers": plan.get("prerequisite_status", {}).get("primers", []),
    }

    existing_path = session.get("learning_path")
    if existing_path and not force_regenerate:
        source = session.get("learning_path_source", "cached")
        return jsonify({"path": existing_path, "source": source, "cached": True})

    path: Dict[str, object] = {}
    source = "fallback"

    if LLM_CLIENT:
        try:
            result = LLM_CLIENT.plan_learning_path(plan_config, enriched_state, interests)
            if result:
                path = result
                source = "llm"
        except LLMUnavailable:
            path = {}

    if not path:
        path = fallback_learning_path(interests, enriched_state)

    path = _personalise_learning_path(path, interests)

    if STAGE_AGENT:
        try:
            path = STAGE_AGENT.refine_learning_path(path, plan, interests)
            source = f"{source}+agents" if source else "langchain-agents"
        except StageAgentUnavailable as exc:  # pragma: no cover - optional dependency
            app.logger.warning("Stage agent refinement unavailable: %s", exc)

    path = _ensure_stage_resources_align(path, plan, interests)

    session["learning_path"] = path
    session["learning_path_source"] = source
    session["learning_feedback"] = {}
    session.modified = True
    return jsonify({"path": path, "source": source})


def _get_learning_stage(stage_id: str) -> Optional[Dict[str, object]]:
    path = session.get("learning_path", {})
    for stage in path.get("stages", []):
        if stage.get("id") == stage_id:
            return stage
    return None


def _derive_stage_keywords(stage: Dict[str, object], interests: Dict[str, object]) -> List[str]:
    keywords = stage.get("keywords") or []
    if not isinstance(keywords, list):
        keywords = [keywords]
    if keywords:
        seeds = keywords
    else:
        seeds = []
        seeds.extend(interests.get("keywords", []))
        if stage.get("type") == "launch_connect":
            seeds.extend(stage.get("student_questions", []))
        if stage.get("type") == "investigate":
            seeds.extend([res.get("title", "") for res in stage.get("resources", [])])
            seeds.extend(["evidence", "source", "claim", "reasoning"])
        if stage.get("type") == "create":
            seeds.extend(stage.get("product_suggestions", []))
            seeds.extend(["product", "audience", "action", "revision"])

    tokens: List[str] = []
    for seed in seeds:
        for token in re.findall(r"[A-Za-z']+", str(seed).lower()):
            if len(token) > 3 and token not in tokens:
                tokens.append(token)
            if len(tokens) >= 10:
                break
        if len(tokens) >= 10:
            break
    return tokens or ["evidence", "claim", "impact"]


MAX_ARTIFACT_BYTES = 6 * 1024 * 1024
SUPPORTED_ARTIFACT_PREFIXES = ("image/", "audio/")


def _summarise_image_bytes(data: bytes, mime_type: str) -> str:
    from PIL import Image

    with Image.open(BytesIO(data)) as img:
        width, height = img.size
        orientation = "landscape" if width >= height else "portrait"
        rgb_sample = img.convert("RGB").resize((64, 64))
        colors = rgb_sample.getcolors(64 * 64) or []
        colors_sorted = sorted(colors, reverse=True, key=lambda item: item[0])[:3]
        dominant = ["#%02x%02x%02x" % tuple(color) for _, color in colors_sorted]
        if not dominant:
            dominant = ["diverse tones"]
        grayscale = rgb_sample.convert("L")
        pixels = list(grayscale.getdata())
        avg_brightness = round(sum(pixels) / len(pixels)) if pixels else 0

    return (
        f"Image resolution {width}x{height} ({orientation}). "
        f"Dominant colors: {', '.join(dominant)}. "
        f"Average brightness: {avg_brightness}/255."
    )


def _summarise_audio_bytes(data: bytes, mime_type: str) -> str:
    extension = mimetypes.guess_extension(mime_type) or ""
    buffer = BytesIO(data)
    if extension:
        buffer.name = f"upload{extension}"
    if mime_type in {"audio/wav", "audio/x-wav"} or extension == ".wav":
        import wave as wave_module

        buffer.seek(0)
        try:
            with wave_module.open(buffer) as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                duration = frames / float(sample_rate) if sample_rate else 0
        except (wave_module.Error, ValueError):
            pass
        else:
            minutes = int(duration // 60)
            seconds = int(round(duration % 60))
            return f"Duration {minutes}m {seconds}s, {channels} channel{'s' if channels != 1 else ''}, sample rate {sample_rate} Hz"

    audio = MutagenFile(buffer)
    if not audio or not getattr(audio, "info", None):
        raise ValueError("Audio format not supported for automated feedback yet.")

    length = getattr(audio.info, "length", None)
    if not length:
        raise ValueError("Could not read audio duration.")
    minutes = int(length // 60)
    seconds = int(round(length % 60))
    sample_rate = getattr(audio.info, "sample_rate", None)
    channels = getattr(audio.info, "channels", None)
    bitrate = getattr(audio.info, "bitrate", None)

    parts = [f"Duration {minutes}m {seconds}s"]
    if channels:
        parts.append(f"{channels} channel{'s' if channels != 1 else ''}")
    if sample_rate:
        parts.append(f"sample rate {sample_rate} Hz")
    if bitrate:
        parts.append(f"bitrate {bitrate} bps")

    return ", ".join(parts)


def _analyse_uploaded_artifact(file_storage) -> Tuple[Optional[str], Optional[str]]:
    if not file_storage or not getattr(file_storage, "filename", ""):
        return None, None

    mime_type = file_storage.mimetype or mimetypes.guess_type(file_storage.filename or "")[0]
    if not mime_type or not mime_type.startswith(SUPPORTED_ARTIFACT_PREFIXES):
        raise ValueError("Please upload an image or audio file.")

    file_storage.stream.seek(0)
    data = file_storage.read()
    file_storage.stream.seek(0)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise ValueError("Uploaded file is too large (limit 6 MB).")

    if not LLM_CLIENT or not hasattr(LLM_CLIENT, "describe_artifact"):
        raise LLMUnavailable("Artifact analysis is not available right now.")

    if mime_type.startswith("image/"):
        feature_text = _summarise_image_bytes(data, mime_type)
    else:
        feature_text = _summarise_audio_bytes(data, mime_type)

    summary = LLM_CLIENT.describe_artifact(mime_type, feature_text)
    return summary.strip(), mime_type


def _evaluate_stage_response(
    stage: Dict[str, object],
    content: str,
    attempt: str,
    stage_state: Dict[str, object],
    interests: Dict[str, object],
    artifact_summary: Optional[str] = None,
) -> Dict[str, object]:
    content_lower = content.lower()
    keywords = _derive_stage_keywords(stage, interests)
    hits = [kw for kw in keywords if kw in content_lower]
    coverage_denominator = max(1, min(4, len(keywords)))
    coverage = min(1.0, len(hits) / coverage_denominator)
    positive_keyword = hits[0] if hits else (keywords[0] if keywords else None)
    positive = (
        f"I like how you highlighted {positive_keyword}."
        if positive_keyword
        else "I like how clearly you explained your thinking."
    )

    artifact_note: Optional[str] = None
    if artifact_summary:
        artifact_note = artifact_summary.strip()
        if artifact_note:
            clipped = artifact_note
            if len(clipped) > 160:
                clipped = clipped[:157].rsplit(" ", 1)[0] + "…"
            positive += f" Your uploaded work shows {clipped}."

    pending_keywords: List[str] = stage_state.get("pending_keywords", [])
    suggestions: List[str] = []
    mastery = False
    utilization = coverage

    if attempt == "draft":
        missing = [kw for kw in keywords if kw not in hits]
        stage_state["pending_keywords"] = missing[:3]
        suggestions = [f"add or clarify how {kw} shows up in your explanation" for kw in stage_state["pending_keywords"]]
        if coverage >= 0.85:
            mastery = True
            suggestions = []
        stage_state["mastery"] = mastery
    else:  # revision or later
        if not pending_keywords:
            pending_keywords = stage_state.get("pending_keywords", keywords)
        used = [kw for kw in pending_keywords if kw in content_lower]
        utilization = len(used) / max(1, min(3, len(pending_keywords)))
        utilization = min(utilization, 1.0)
        missing_after_revision = [kw for kw in pending_keywords if kw not in used]
        if coverage >= 0.85 and utilization >= 0.85:
            mastery = True
            stage_state["pending_keywords"] = []
        else:
            mastery = False
            stage_state["pending_keywords"] = missing_after_revision
            suggestions = [
                f"weave in specific detail about {kw} to show you used the feedback"
                for kw in missing_after_revision[:3]
            ]
        stage_state["mastery"] = mastery

    improvement = (
        suggestions[0].capitalize() if suggestions else "Keep building from here—this is ready for the next step."
    )
    feedback_text = f"{positive} {improvement}"
    score = round(utilization if attempt != "draft" else coverage, 2)

    return {
        "feedback": feedback_text,
        "mastery": mastery,
        "score": score,
        "positive": positive,
        "suggestions": suggestions,
        "utilization": round(utilization, 2),
        "artifact_summary": artifact_note,
    }


@app.post("/api/learning-feedback")
def api_learning_feedback():
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        stage_id = request.form.get("stage_id")
        attempt = (request.form.get("attempt") or "draft").lower()
        content = (request.form.get("content") or "").strip()
        artifact_file = request.files.get("artifact")
    else:
        payload = request.get_json(silent=True) or {}
        stage_id = payload.get("stage_id")
        attempt = (payload.get("attempt") or "draft").lower()
        content = (payload.get("content") or "").strip()
        artifact_file = None

    if not stage_id:
        return jsonify({"error": "A stage id is required."}), 400

    stage = _get_learning_stage(stage_id)
    if not stage:
        return jsonify({"error": "Selected learning step could not be found."}), 404

    interests = get_student_state().get("interests", {})
    stage_feedback_state = session.setdefault("learning_feedback", {}).setdefault(stage_id, {})

    artifact_summary = None
    artifact_mime = None
    if artifact_file and getattr(artifact_file, "filename", ""):
        try:
            artifact_summary, artifact_mime = _analyse_uploaded_artifact(artifact_file)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except LLMUnavailable as exc:
            return jsonify({"error": str(exc)}), 503

    combined_content = content
    if artifact_summary:
        combined_content = (
            f"{combined_content}\n\nArtifact insight: {artifact_summary}".strip()
            if combined_content
            else f"Artifact insight: {artifact_summary}"
        )

    if not combined_content:
        return jsonify({"error": "Add a description or upload a supported file for feedback."}), 400

    result = _evaluate_stage_response(stage, combined_content, attempt, stage_feedback_state, interests, artifact_summary)
    if artifact_summary:
        result["artifact_summary"] = artifact_summary
        if artifact_mime:
            result["artifact_mime"] = artifact_mime
    session.modified = True

    return jsonify(result)


@app.route("/interests", methods=["GET", "POST"])
def interest_check() -> str:
    if request.method == "POST":
        action = request.form.get("action", "continue")
        modes = request.form.getlist("interest_modes")
        topic_focus = request.form.get("interest_topics", "").strip()
        learning_modes = request.form.getlist("learning_mode")
        support_preference = request.form.get("support_preference")
        selected_exemplars = list(dict.fromkeys(request.form.getlist("selected_exemplars")))

        keywords = [piece.strip() for piece in re.split(r"[,\n]", topic_focus) if piece.strip()]
        interests = {
            "interest_modes": modes,
            "topic_focus": topic_focus,
            "learning_mode": learning_modes or [],
            "support_preference": support_preference,
            "selected_exemplars": selected_exemplars,
            "keywords": keywords,
            "ai_suggestions": session.get("interest_suggestions", []),
        }

        store_student_interests(interests)
        session.pop("learning_path", None)
        session.pop("learning_feedback", None)
        session.modified = True

        if action == "save":
            session["interest_saved_message"] = "Selections saved."
            session.modified = True
            return redirect(url_for("interest_check"))

        return redirect(url_for("learning_path"))

    student_state = get_student_state()
    interests_snapshot = student_state.get("interests", {})
    topic_focus_value = (interests_snapshot.get("topic_focus") or "").strip()
    can_generate_examples = bool(
        interests_snapshot.get("interest_modes")
        and topic_focus_value
        and interests_snapshot.get("learning_mode")
        and interests_snapshot.get("support_preference")
    )
    stored_exemplars = student_state["interests"].get("selected_exemplars", [])
    if isinstance(stored_exemplars, str):
        stored_exemplars = [stored_exemplars]
    legacy_choice = student_state["interests"].get("scenario")
    if legacy_choice and legacy_choice not in stored_exemplars:
        stored_exemplars = stored_exemplars + [legacy_choice]

    current_suggestions_raw = session.get("interest_suggestions", [])
    prepared_suggestions = _prepare_interest_suggestions(current_suggestions_raw)
    if prepared_suggestions != current_suggestions_raw:
        session["interest_suggestions"] = prepared_suggestions
        session.modified = True

    raw_saved_message = session.pop("interest_saved_message", None)
    saved_message = raw_saved_message if isinstance(raw_saved_message, str) else None
    if raw_saved_message and not isinstance(raw_saved_message, str):  # pragma: no cover - defensive
        app.logger.debug("Dropped non-string interest_saved_message payload: %s", type(raw_saved_message).__name__)
    plan = active_plan()
    return render_template(
        "step_interests.html",
        plan=plan,
        student_state=student_state,
        interest_suggestions=prepared_suggestions,
        saved_exemplars=stored_exemplars,
        saved_message=saved_message,
        can_generate_examples=can_generate_examples,
    )


@app.route("/learn")
def learning_path() -> str:
    plan = active_plan()
    return render_template(
        "step_learn.html",
        plan=plan,
        student_state=get_student_state(),
    )


@app.route("/mastery", methods=["GET", "POST"])
def mastery() -> str:
    if request.method == "POST":
        # In a full implementation, results would be submitted and evaluated here.
        return redirect(url_for("summary"))

    plan = active_plan()
    return render_template(
        "step_mastery.html",
        plan=plan,
        student_state=get_student_state(),
    )


@app.route("/summary")
def summary() -> str:
    plan = active_plan()
    return render_template(
        "step_summary.html",
        plan=plan,
        student_state=get_student_state(),
    )


@app.route("/reset")
def reset() -> str:
    session.clear()
    session["selection_message"] = {
        "type": "info",
        "text": "Session reset. Choose a new topic to begin.",
    }
    return redirect(url_for("catalog"))


if __name__ == "__main__":
    app.run(debug=True)
