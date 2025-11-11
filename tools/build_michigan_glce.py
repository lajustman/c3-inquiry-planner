#!/usr/bin/env python3
"""
Generate Turtle representations for the Michigan Social Studies GLCE set.

This script parses the source PDFs for K-8 and 9-12 standards and emits a root ontology
alongside modular grade and course files that align with the local ontology schema.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_K8_PDF = (
    PROJECT_ROOT / "Background Information" / "Standards" / "Michigan" / "K-8_SS_Standards.pdf"
)
DEFAULT_HS_PDF = (
    PROJECT_ROOT / "Background Information" / "Standards" / "Michigan" / "9-12_SS_Standards.pdf"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "Curriculum-Ontology" / "michigan" / "mi-standards.ttl"

GRADES_DIR_NAME = "grades"
COURSES_DIR_NAME = "courses"

FOOTERS = {
    "GRADES K-8 SOCIAL STUDIES CONTENT EXPECTATIONS",
    "MICHIGAN DEPARTMENT OF EDUCATION",
    "MICHIGAN K-12 SOCIAL STUDIES STANDARDS",
    "THE MICHIGAN K-12 SOCIAL STUDIES STANDARDS",
}

IGNORE_LINES = {
    "SOCIAL STUDIES CONTENT EXPECTATIONS",
    "THIS DOCUMENT IS FOR DRAFT REVIEW PURPOSES",
}

GRADE_ORDER = ["K", "1", "2", "3", "4", "5", "6", "7", "8"]
COURSE_ORDER = ["WHG", "USHG", "CIVICS", "ECON", "CG"]

HS_COURSE_HEADERS: Dict[str, Tuple[str, str]] = {
    "WORLD HISTORY AND GEOGRAPHY": ("WHG", "World History and Geography"),
    "UNITED STATES HISTORY AND GEOGRAPHY": ("USHG", "United States History and Geography"),
    "CIVICS": ("CIVICS", "Civics"),
    "ECONOMICS": ("ECON", "Economics"),
    "CONTEMPORARY GLOBAL ISSUES": ("CG", "Contemporary Global Issues"),
}

COURSE_DISCIPLINES = {
    "WHG": "W",
    "USHG": "U",
    "CIVICS": "C",
    "ECON": "E",
    "CG": "W",
}

DISCIPLINES = {
    "H": "History",
    "G": "Geography",
    "C": "Civics and Government",
    "E": "Economics",
    "P": "Public Discourse, Decision Making, and Citizen Involvement",
    "U": "U.S. History and Geography",
    "W": "World History and Geography",
}

GRADE_WORD_TO_CODE = {
    "Kindergarten": "K",
    "One": "1",
    "Two": "2",
    "Three": "3",
    "Four": "4",
    "Five": "5",
    "Six": "6",
    "Seven": "7",
    "Eight": "8",
}

EXAMPLE_PATTERN = re.compile(
    r"(?:^|[.;])\s*(?:Examples?(?:\s+[A-Za-z/-]+)*|These\s+[A-Za-z\s]+?|Analysis|Evaluation|Considerations?)\s+(?:(?:of|for)\s+[^:]+?\s+)?(?:may\s+)?include(?:s)?(?:\s+but\s+are\s+not\s+limited\s+to)?[:]?[\s]*(.*)",
    re.IGNORECASE | re.DOTALL,
)
SPILLOVER_HEADING_PATTERN = re.compile(r"\b(WHG|USHG|CG)\s+ERA\b", re.IGNORECASE)
EXAMPLE_PHRASE_CLEAN = re.compile(
    r"(?:examples?|analysis|evaluation|considerations?)\s+(?:(?:of|for)\s+[^:]+?\s+)?(?:may\s+)?include(?:s)?(?:\s+but\s+are\s+not\s+limited\s+to)?[:]?",
    re.IGNORECASE,
)


CASE_PATTERN = re.compile(r"[A-Z][A-Za-z0-9.&'() ]* v\. [A-Z][A-Za-z0-9.&'() ]*")

def is_spillover_example(text: str) -> bool:
    """Determine if a captured example fragment likely contains non-example spillover text."""
    if len(text) > 200:
        return True
    if SPILLOVER_HEADING_PATTERN.search(text):
        return True
    lowered = text.lower()
    if "michigan k-12 social studies standards" in lowered or "the arc of inquiry" in lowered:
        return True
    if re.search(r"dimension\s+\d", lowered):
        return True
    if "social studies process" in lowered or "high school" in lowered:
        return True
    return False


def split_examples(raw: str) -> List[str]:
    """Break an example clause into individual example statements."""
    if not raw:
        return []
    cleaned = raw.strip()
    if not cleaned:
        return []
    cleaned = EXAMPLE_PHRASE_CLEAN.sub(
        "",
        cleaned,
    )
    examples: List[str] = []
    case_matches = CASE_PATTERN.findall(cleaned)
    for case in case_matches:
        case_clean = case.strip(" ,;.")
        if case_clean:
            examples.append(case_clean)
    cleaned = CASE_PATTERN.sub(' ', cleaned)
    cleaned = re.sub(r"\.\s+(?=[a-z])", "\n", cleaned)
    cleaned = re.sub(r"\*\s*:", "\n", cleaned)
    cleaned = cleaned.replace(":", "\n")
    # Normalize bullet characters to line breaks.
    cleaned = cleaned.replace("•", "\n")
    cleaned = cleaned.replace(" - ", "\n")
    cleaned = re.sub(r',', ' ', cleaned)
    parts = re.split(r";|\n|•", cleaned)
    for part in parts:
        candidate = part.strip()
        if not candidate:
            continue
        # Remove leading conjunctions for readability.
        if candidate.lower().startswith("and "):
            candidate = candidate[4:].strip()
        candidate = candidate.lstrip("*:- ").strip()
        candidate = candidate.strip(',;')
        if candidate.endswith("."):
            candidate = candidate.rstrip(".").strip()
        if candidate:
            candidate = EXAMPLE_PHRASE_CLEAN.sub(
                "",
                candidate,
            ).strip()
            lowered_candidate = candidate.lower()
            if " include" in lowered_candidate or lowered_candidate.startswith("citizens as well"):
                continue
            if candidate:
                examples.append(candidate)
    if not examples and cleaned:
        examples.append(cleaned.strip())
    return examples


def extract_examples(text: str) -> Tuple[str, List[str]]:
    """Separate example statements from a description or official text."""
    if not text:
        return text.strip(), []
    working = text
    examples: List[str] = []
    while True:
        match = re.search(EXAMPLE_PATTERN, working)
        if not match:
            break
        start = match.start()
        example_chunk = match.group(1).strip()
        before = working[:start].rstrip(" ;,")
        parts = split_examples(example_chunk)
        spillover_segments: List[str] = []
        filtered_parts: List[str] = []
        for part in parts:
            if is_spillover_example(part):
                spillover_segments.append(part)
            else:
                filtered_parts.append(part)
        if spillover_segments:
            spillover_text = " ".join(spillover_segments).strip()
            if spillover_text:
                before = (before + " " + spillover_text).strip()
        examples = filtered_parts + examples
        working = before
    return working.strip(), examples


def cleanup_statement(text: str) -> Tuple[str, List[str]]:
    """Remove spillover headings and capture residual list-style examples."""
    if not text:
        return text.strip(), []
    extra_examples: List[str] = []
    working = text.strip()
    spillover_markers = [
        "THE ARC OF INQUIRY",
        "Dimension 1:",
        "Dimension 2:",
        "Dimension 3:",
        "Dimension 4:",
        "Michigan K-12 Social Studies Standards",
        "SOCIAL STUDIES PROCESS AND SKILLS",
    ]
    for marker in spillover_markers:
        idx = working.find(marker)
        if idx != -1:
            working = working[:idx].strip()
            break
    working = re.sub(r"\s+\d{2,3}\b.*$", "", working).strip()
    sentences = re.split(r"(?<!\bv)\.\s+", working)
    if len(sentences) > 1:
        first_sentence = sentences[0].strip()
        rest = ". ".join(sentences[1:]).strip()
        if rest:
            upper = sum(1 for c in rest if c.isupper())
            lower = sum(1 for c in rest if c.islower())
            if lower > 0 and upper <= lower / 2 + 1:
                extra_examples.extend(split_examples(rest))
                working = first_sentence + "."
    working = working.strip()
    return working, extra_examples


@dataclass
class Category:
    unit: str
    unit_type: str  # "grade" or "course"
    code: str
    label: str
    description: str
    discipline: str
    examples: List[str] = field(default_factory=list)


@dataclass
class Expectation:
    unit: str
    unit_type: str
    code: str
    full_code: str
    text: str
    category_code: str
    discipline: str
    examples: List[str] = field(default_factory=list)


def normalize_literal(text: str) -> str:
    """Collapse whitespace and convert typographic glyphs to ASCII."""
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2014": "-",
        "\u2013": "-",
        "\u00a0": " ",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return " ".join(text.split())


def escape_literal(text: str) -> str:
    """Escape a literal value for Turtle output."""
    return normalize_literal(text).replace("\\", "\\\\").replace('"', '\\"')


def read_pdf_layout(pdf_path: Path) -> str:
    """Render the PDF to a layout-preserving text stream via pdftotext."""
    try:
        result = subprocess.run(
            ["pdftotext", "-layout", str(pdf_path), "-"],
            capture_output=True,
            check=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("pdftotext command is required but was not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"pdftotext failed for {pdf_path}: {exc.stderr}") from exc
    return result.stdout.replace("\u2013", "-").replace("\u2014", "-")


def derive_category_code(expectation_code: str) -> str:
    parts = expectation_code.split(".")
    if len(parts) <= 1:
        return expectation_code
    if len(parts) >= 2 and parts[1] == "0":
        return parts[0]
    return ".".join(parts[:-1])


def discipline_from_code(code: str) -> str:
    match = re.match(r"([A-Z]+)", code)
    if not match:
        return ""
    return match.group(1)[0]


def parse_k8(text: str) -> Tuple[Dict[str, str], List[Category], List[Expectation]]:
    lines = text.splitlines()
    current_grade: Optional[str] = None
    grade_map: Dict[str, str] = {}
    raw_categories: Dict[Tuple[str, str], Dict[str, str]] = {}
    expectations: List[Expectation] = []

    category_regex = re.compile(r"^([A-Z][A-Z0-9]*(?:\.[0-9]+)?)\s+(.*)$")
    expectation_regex = re.compile(r"^\s*(K|[1-8])\s*-\s*([A-Z][A-Z0-9]*(?:\.[0-9]+){1,3})\s+(.*)$")

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        normalized = " ".join(stripped.split())

        if not stripped or normalized in FOOTERS or normalized.isdigit():
            i += 1
            continue

        if normalized.startswith("Social Studies Content Expectations"):
            remainder = normalized[len("Social Studies Content Expectations") :].strip()
            if remainder and not remainder.startswith("Grade") and f"Grade {remainder}" in GRADE_WORD_TO_CODE:
                remainder = f"Grade {remainder}"
            grade_code = None
            if remainder.startswith("Grade "):
                possible = remainder.split(" ", 1)[1]
                grade_code = GRADE_WORD_TO_CODE.get(possible, possible)
            elif remainder == "Kindergarten":
                grade_code = "K"
            if grade_code:
                current_grade = grade_code
                if current_grade not in grade_map:
                    label = (
                        "Kindergarten"
                        if grade_code == "K"
                        else f"Grade {grade_code}"
                    )
                    grade_map[grade_code] = label
            i += 1
            continue

        match_exp = expectation_regex.match(raw)
        if match_exp:
            grade_code, code, text_init = match_exp.groups()
            text_lines = [text_init.strip()]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_strip = nxt.strip()
                if not nxt_strip:
                    j += 1
                    break
                if expectation_regex.match(nxt):
                    break
                nxt_lstrip = nxt.lstrip()
                if category_regex.match(nxt_lstrip):
                    break
                text_lines.append(nxt_strip)
                j += 1
            text_value = " ".join(text_lines)
            text_value, cleanup_examples = cleanup_statement(text_value)
            text_value, text_examples = extract_examples(text_value)
            text_examples.extend(cleanup_examples)
            category_code = derive_category_code(code)
            discipline_code = discipline_from_code(code)
            expectations.append(
                Expectation(
                    unit=grade_code,
                    unit_type="grade",
                    code=code,
                    full_code=f"{grade_code}-{code}",
                    text=text_value,
                    category_code=category_code,
                    discipline=discipline_code,
                    examples=text_examples,
                )
            )
            i = j
            continue

        cat_line = raw.lstrip()
        match_cat = category_regex.match(cat_line)
        if match_cat and current_grade:
            code, label = match_cat.groups()
            code = code.strip()
            if not re.match(r"^[A-Z][A-Z0-9]*(?:\.[0-9]+)?$", code):
                i += 1
                continue
            label = label.strip()
            j = i + 1
            label_lines = [label]
            desc_lines: List[str] = []
            desc_started = False

            while j < len(lines):
                nxt_raw = lines[j]
                nxt_strip = nxt_raw.strip()
                if not nxt_strip:
                    j += 1
                    break
                if expectation_regex.match(nxt_raw):
                    break
                nxt_lstrip = nxt_raw.lstrip()
                if category_regex.match(nxt_lstrip):
                    break
                first_word = nxt_strip.split()[0].lower().strip("(")
                if not desc_started and first_word in {
                    "about",
                    "and",
                    "or",
                    "of",
                    "for",
                    "with",
                    "in",
                    "on",
                    "to",
                    "by",
                    "the",
                    "a",
                    "an",
                    "from",
                    "using",
                }:
                    label_lines.append(nxt_strip)
                else:
                    desc_started = True
                    desc_lines.append(nxt_strip)
                j += 1

            description_text = " ".join(desc_lines)
            description_text, cleanup_examples = cleanup_statement(description_text)
            description_text, description_examples = extract_examples(description_text)
            description_examples.extend(cleanup_examples)
            raw_categories[(current_grade, code)] = {
                "label": " ".join(label_lines),
                "description": description_text,
                "examples": description_examples,
            }
            i = j
            continue

        i += 1

    categories: Dict[Tuple[str, str], Category] = {}
    for exp in expectations:
        key = (exp.unit, exp.category_code)
        if key not in categories:
            cat_info = raw_categories.get(
                key, {"label": exp.category_code, "description": "", "examples": []}
            )
            categories[key] = Category(
                unit=exp.unit,
                unit_type="grade",
                code=exp.category_code,
                label=cat_info["label"],
                description=cat_info["description"],
                discipline=exp.discipline,
                examples=cat_info.get("examples", []),
            )

    return grade_map, list(categories.values()), expectations


def match_course_heading(normalized_upper: str) -> Optional[Tuple[str, str]]:
    for header, (code, label) in HS_COURSE_HEADERS.items():
        if normalized_upper == header or normalized_upper.endswith(header):
            return code, label
        if header == "CONTEMPORARY GLOBAL ISSUES" and header in normalized_upper:
            return code, label
    return None


def parse_high_school(text: str) -> Tuple[Dict[str, str], List[Category], List[Expectation]]:
    lines = text.splitlines()
    in_high_school = False
    current_course: Optional[str] = None
    course_map: Dict[str, str] = {}
    categories: Dict[Tuple[str, str], Category] = {}
    expectations: List[Expectation] = []
    pending_category: Optional[Tuple[str, str]] = None  # (course, code)
    pending_label: List[str] = []
    pending_desc: List[str] = []

    digit_expectation = re.compile(r"^(\d+(?:\.\d+){2,})(?:\s+(.*))?$")
    letter_expectation = re.compile(r"^([A-Z]{1,3})\s*[–-]\s*([0-9]+(?:\.[0-9]+)+)(?:\s+(.*))?$")
    alpha_digit_expectation = re.compile(r"^([A-Z]{1,3}\d+(?:\.[0-9]+)*)(?:\s+(.*))?$")
    category_pattern = re.compile(r"^([A-Z]{1,3}\d+(?:\.\d+)*|\d+\.\d+)\s+(.*)$")

    def finalize_pending():
        nonlocal pending_category, pending_label, pending_desc
        if not pending_category:
            return
        unit, code = pending_category
        discipline = COURSE_DISCIPLINES.get(unit, "")
        label = " ".join(pending_label).strip()
        description = " ".join(pending_desc).strip()
        description, cleanup_examples = cleanup_statement(description)
        description, examples = extract_examples(description)
        examples.extend(cleanup_examples)
        if (unit, code) not in categories:
            categories[(unit, code)] = Category(
                unit=unit,
                unit_type="course",
                code=code,
                label=label,
                description=description,
                discipline=discipline,
                examples=examples,
            )
        else:
            # Merge description if category already exists.
            existing = categories[(unit, code)]
            merged_desc = " ".join(filter(None, [existing.description, description])).strip()
            combined_examples = list(existing.examples)
            for ex in examples:
                if ex not in combined_examples:
                    combined_examples.append(ex)
            categories[(unit, code)] = Category(
                unit=unit,
                unit_type="course",
                code=code,
                label=existing.label or label,
                description=merged_desc,
                discipline=existing.discipline or discipline,
                examples=combined_examples,
            )
        pending_category = None
        pending_label = []
        pending_desc = []

    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        normalized = " ".join(stripped.split())
        upper = normalized.upper()

        if "(9-12)" in normalized:
            in_high_school = True
        if not in_high_school:
            i += 1
            continue

        if not stripped or normalized in FOOTERS or normalized in IGNORE_LINES or normalized.isdigit():
            i += 1
            continue

        heading = match_course_heading(upper)
        if heading:
            finalize_pending()
            course_code, course_label = heading
            current_course = course_code
            course_map[course_code] = course_label
            i += 1
            continue

        if current_course is None:
            i += 1
            continue

        if normalized.startswith("CG ") and normalized.split()[0] == "CG":
            finalize_pending()
            pending_category = (current_course, "CG")
            pending_label = [normalize_literal(normalized[3:])] if len(normalized) > 3 else []
            pending_desc = []
            i += 1
            continue

        # Letter expectations like "C – 2.1.1 ..."
        match_letter = letter_expectation.match(normalized)
        if match_letter:
            finalize_pending()
            prefix = match_letter.group(1)
            digits = match_letter.group(2).replace(" ", "")
            text_lines: List[str] = []
            if match_letter.group(3):
                text_lines.append(normalize_literal(match_letter.group(3)))
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_strip = nxt.strip()
                nxt_norm = " ".join(nxt_strip.split())
                if not nxt_strip:
                    j += 1
                    continue
                if match_course_heading(nxt_norm.upper()):
                    break
                if letter_expectation.match(nxt_norm) or digit_expectation.match(nxt_norm) or alpha_digit_expectation.match(nxt_norm):
                    break
                if category_pattern.match(nxt_norm):
                    break
                if nxt_norm in FOOTERS or nxt_norm in IGNORE_LINES:
                    j += 1
                    continue
                text_lines.append(nxt_norm)
                j += 1

            code = f"{prefix}{digits}"
            text_value = " ".join(text_lines).strip()
            text_value, cleanup_examples = cleanup_statement(text_value)
            text_value, text_examples = extract_examples(text_value)
            text_examples.extend(cleanup_examples)
            category_code = derive_category_code(code)
            expectations.append(
                Expectation(
                    unit=current_course,
                    unit_type="course",
                    code=code,
                    full_code=f"{current_course}-{code}",
                    text=text_value,
                    category_code=category_code,
                    discipline=COURSE_DISCIPLINES.get(current_course, ""),
                    examples=text_examples,
                )
            )
            i = j
            continue

        # Numeric expectation like "4.1.1 ..."
        match_digit = digit_expectation.match(normalized)
        if match_digit:
            finalize_pending()
            code = match_digit.group(1)
            text_lines: List[str] = []
            if match_digit.group(2):
                text_lines.append(normalize_literal(match_digit.group(2)))
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                nxt_strip = nxt.strip()
                nxt_norm = " ".join(nxt_strip.split())
                if not nxt_strip:
                    j += 1
                    continue
                if match_course_heading(nxt_norm.upper()):
                    break
                if digit_expectation.match(nxt_norm) or letter_expectation.match(nxt_norm) or alpha_digit_expectation.match(nxt_norm):
                    break
                if category_pattern.match(nxt_norm):
                    break
                if nxt_norm in FOOTERS or nxt_norm in IGNORE_LINES:
                    j += 1
                    continue
                text_lines.append(nxt_norm)
                j += 1

            text_value = " ".join(text_lines).strip()
            text_value, cleanup_examples = cleanup_statement(text_value)
            text_value, text_examples = extract_examples(text_value)
            text_examples.extend(cleanup_examples)
            category_code = derive_category_code(code)
            expectations.append(
                Expectation(
                    unit=current_course,
                    unit_type="course",
                    code=code,
                    full_code=f"{current_course}-{code}",
                    text=text_value,
                    category_code=category_code,
                    discipline=COURSE_DISCIPLINES.get(current_course, ""),
                    examples=text_examples,
                )
            )
            i = j
            continue

        match_alpha = alpha_digit_expectation.match(normalized)
        if match_alpha:
            potential_code = match_alpha.group(1)
            rest_text = match_alpha.group(2)
            prefix_letters_match = re.match(r"^([A-Z]+)", potential_code)
            prefix_letters = prefix_letters_match.group(1) if prefix_letters_match else ""
            treat_as_expectation = False
            if potential_code.startswith("CG"):
                treat_as_expectation = True
            elif "." in potential_code and prefix_letters in {"F", "P"}:
                treat_as_expectation = True
            if treat_as_expectation:
                finalize_pending()
                text_lines: List[str] = []
                if rest_text:
                    text_lines.append(normalize_literal(rest_text))
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    nxt_strip = nxt.strip()
                    nxt_norm = " ".join(nxt_strip.split())
                    if not nxt_strip:
                        j += 1
                        continue
                    if match_course_heading(nxt_norm.upper()):
                        break
                    if letter_expectation.match(nxt_norm) or digit_expectation.match(nxt_norm) or alpha_digit_expectation.match(nxt_norm):
                        break
                    if category_pattern.match(nxt_norm):
                        break
                    if nxt_norm in FOOTERS or nxt_norm in IGNORE_LINES:
                        j += 1
                        continue
                    text_lines.append(nxt_norm)
                    j += 1

                text_value = " ".join(text_lines).strip()
                text_value, cleanup_examples = cleanup_statement(text_value)
                text_value, text_examples = extract_examples(text_value)
                text_examples.extend(cleanup_examples)
                category_code = derive_category_code(potential_code)
                expectations.append(
                    Expectation(
                        unit=current_course,
                        unit_type="course",
                        code=potential_code,
                        full_code=f"{current_course}-{potential_code}",
                        text=text_value,
                        category_code=category_code,
                        discipline=COURSE_DISCIPLINES.get(current_course, ""),
                        examples=text_examples,
                    )
                )
                i = j
                continue

        match_cat = category_pattern.match(normalized)
        if match_cat:
            finalize_pending()
            code, label = match_cat.groups()
            pending_category = (current_course, code)
            pending_label = [label.strip()]
            pending_desc = []
            i += 1
            continue

        if pending_category:
            # Append to the current category description if it is meaningful text.
            if normalized not in FOOTERS and normalized not in IGNORE_LINES:
                pending_desc.append(normalized)

        i += 1

    finalize_pending()

    # Ensure categories referenced by expectations exist.
    for exp in expectations:
        key = (exp.unit, exp.category_code)
        if key not in categories:
            categories[key] = Category(
                unit=exp.unit,
                unit_type="course",
                code=exp.category_code,
                label=exp.category_code,
                description="",
                discipline=exp.discipline,
            )

    # Promote standalone categories (no direct expectations and no subcategories)
    categories_by_unit: Dict[str, List[str]] = defaultdict(list)
    for cat in categories.values():
        categories_by_unit[cat.unit].append(cat.code)

    expectations_by_category: Dict[Tuple[str, str], int] = defaultdict(int)
    for exp in expectations:
        expectations_by_category[(exp.unit, exp.category_code)] += 1

    for cat in list(categories.values()):
        key = (cat.unit, cat.code)
        has_expectations = expectations_by_category[key] > 0
        has_children = any(
            other != cat.code and other.startswith(f"{cat.code}.")
            for other in categories_by_unit[cat.unit]
        )
        if not has_expectations and not has_children:
            text = cat.description or cat.label
            expectations.append(
                Expectation(
                    unit=cat.unit,
                    unit_type="course",
                    code=cat.code,
                    full_code=f"{cat.unit}-{cat.code}",
                    text=text,
                    category_code=cat.code,
                    discipline=cat.discipline,
                )
            )
            expectations_by_category[key] += 1

    return course_map, list(categories.values()), expectations


def grade_id(code: str) -> str:
    safe = code.replace("-", "_")
    return f"mi:Grade_{safe}"


def course_id(code: str) -> str:
    safe = code.replace("-", "_")
    return f"mi:Course_{safe}"


def category_id(unit: str, code: str) -> str:
    safe = code.replace(".", "_").replace("-", "_")
    return f"mi:Cat_{unit}_{safe}"


def expectation_id(unit: str, code: str) -> str:
    safe = code.replace(".", "_").replace("-", "_")
    return f"mi:Exp_{unit}_{safe}"


def example_id(unit: str, code: str, index: int, scope: str) -> str:
    safe_unit = unit.replace("-", "_")
    safe_code = code.replace(".", "_").replace("-", "_")
    return f"mi:Example_{scope}_{safe_unit}_{safe_code}_{index + 1}"


def render_root_ttl(
    grade_map: Dict[str, str],
    course_map: Dict[str, str],
    source_label: str,
) -> str:
    lines: List[str] = []

    lines.append("@prefix mi:      <urn:mi:ss:> .")
    lines.append("@prefix dcterms: <http://purl.org/dc/terms/> .")
    lines.append("@prefix owl:     <http://www.w3.org/2002/07/owl#> .")
    lines.append("@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    lines.append("@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .")
    lines.append("@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .")
    lines.append("@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .")
    lines.append("")
    lines.append("@base <urn:mi:ss:> .")
    lines.append("")

    imports = ["<urn:mi:ss:ontology>"]
    imports.extend(f"<urn:mi:ss:grade:{code}>" for code in sorted(grade_map, key=lambda g: GRADE_ORDER.index(g)))
    imports.extend(f"<urn:mi:ss:course:{code}>" for code in COURSE_ORDER if code in course_map)
    lines.append("<urn:mi:ss:data> a owl:Ontology ;")
    lines.append('  rdfs:label "Michigan Social Studies GLCE Dataset" ;')
    lines.append("  owl:imports")
    for idx, ref in enumerate(imports):
        sep = " ;" if idx == len(imports) - 1 else " ,"
        lines.append(f"    {ref}{sep}")
    lines.append(f'  dcterms:source "{escape_literal(source_label)}" .')
    lines.append("")

    lines.append("mi:MichiganGLCEFramework a mi:MichiganGLCE ;")
    lines.append('  rdfs:label "Michigan Social Studies GLCE" ;')
    lines.append(f'  dcterms:source "{escape_literal(source_label)}" ;')

    if grade_map:
        grade_refs = [grade_id(code) for code in sorted(grade_map, key=lambda g: GRADE_ORDER.index(g))]
        lines.append("  mi:hasGrade")
        for idx, ref in enumerate(grade_refs):
            sep = " ;" if idx == len(grade_refs) - 1 else " ,"
            lines.append(f"    {ref}{sep}")
        if not course_map:
            lines[-1] = lines[-1].replace(" ;", " .")

    if course_map:
        course_refs = [course_id(code) for code in COURSE_ORDER if code in course_map]
        lines.append("  mi:hasCourse")
        for idx, ref in enumerate(course_refs):
            sep = " ." if idx == len(course_refs) - 1 else " ,"
            lines.append(f"    {ref}{sep}")
    elif not grade_map:
        lines[-1] = lines[-1].replace(" ;", " .")

    lines.append("")

    lines.append("#################################################################")
    lines.append("# Disciplines")
    lines.append("#################################################################")
    for code in sorted(DISCIPLINES):
        disc_id = f"mi:Discipline_{code}"
        label = escape_literal(DISCIPLINES[code])
        lines.append(f"{disc_id} a mi:Discipline ;")
        lines.append(f'  skos:prefLabel "{label}" ;')
        lines.append(f'  mi:disciplineCode "{code}" .')
        lines.append("")

    return "\n".join(line for line in lines if line.strip()) + "\n"


def render_grade_ttl(
    grade_code: str,
    grade_label: str,
    categories: List[Category],
    expectations: List[Expectation],
    source_label: str,
) -> str:
    lines: List[str] = []
    gid = grade_id(grade_code)
    order = GRADE_ORDER.index(grade_code) if grade_code in GRADE_ORDER else 99

    lines.append("@prefix mi:      <urn:mi:ss:> .")
    lines.append("@prefix dcterms: <http://purl.org/dc/terms/> .")
    lines.append("@prefix owl:     <http://www.w3.org/2002/07/owl#> .")
    lines.append("@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    lines.append("@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .")
    lines.append("@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .")
    lines.append("@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .")
    lines.append("")
    lines.append("@base <urn:mi:ss:> .")
    lines.append("")

    lines.append(f"<urn:mi:ss:grade:{grade_code}> a owl:Ontology ;")
    lines.append(f'  rdfs:label "Michigan Social Studies GLCE - {escape_literal(grade_label)}" ;')
    lines.append("  owl:imports <urn:mi:ss:ontology> ;")
    lines.append(f'  dcterms:source "{escape_literal(source_label)}" .')
    lines.append("")

    sorted_categories = sorted(categories, key=lambda c: c.code)
    cat_refs = [category_id(grade_code, cat.code) for cat in sorted_categories]
    example_records: List[Tuple[str, str]] = []

    lines.append(f"{gid} a mi:Grade ;")
    lines.append(f'  skos:prefLabel "{escape_literal(grade_label)}" ;')
    if cat_refs:
        lines.append("  mi:hasCategory")
        for idx, ref in enumerate(cat_refs):
            sep = " ;" if idx == len(cat_refs) - 1 else " ,"
            lines.append(f"    {ref}{sep}")
    lines.append("  mi:isGradeOf mi:MichiganGLCEFramework ;")
    lines.append(f'  mi:gradeCode "{grade_code}" ;')
    lines.append(f"  mi:gradeOrder {order} .")
    lines.append("")

    lines.append("#################################################################")
    lines.append("# Categories")
    lines.append("#################################################################")
    exp_by_category: Dict[str, List[Expectation]] = defaultdict(list)
    for exp in expectations:
        exp_by_category[exp.category_code].append(exp)

    for cat in sorted_categories:
        cid = category_id(cat.unit, cat.code)
        lines.append(f"{cid} a mi:StandardCategory ;")
        lines.append(f'  mi:categoryCode "{cat.code}" ;')
        lines.append(f'  skos:prefLabel "{escape_literal(cat.label or cat.code)}" ;')
        if cat.description.strip():
            lines.append(f'  mi:categoryDescription "{escape_literal(cat.description)}" ;')
        lines.append(f"  mi:inGrade {gid} ;")
        if cat.discipline:
            lines.append(f"  mi:inDiscipline mi:Discipline_{cat.discipline} ;")
        if cat.examples:
            lines.append("  mi:hasExample")
            for idx, example_text in enumerate(cat.examples):
                ex_id = example_id(cat.unit, cat.code, idx, "cat")
                example_records.append((ex_id, example_text))
                sep = " ;" if idx == len(cat.examples) - 1 else " ,"
                lines.append(f"    {ex_id}{sep}")
        linked = sorted(exp_by_category.get(cat.code, []), key=lambda e: e.code)
        if linked:
            lines.append("  mi:hasExpectation")
            for idx, exp in enumerate(linked):
                ref = expectation_id(exp.unit, exp.code)
                sep = " ;" if idx == len(linked) - 1 else " ,"
                lines.append(f"    {ref}{sep}")
        lines.append(f"  mi:isCategoryOf {gid} .")
        lines.append("")

    lines.append("#################################################################")
    lines.append("# Expectations")
    lines.append("#################################################################")
    for exp in sorted(expectations, key=lambda e: e.code):
        eid = expectation_id(exp.unit, exp.code)
        cid = category_id(exp.unit, exp.category_code)
        lines.append(f"{eid} a mi:Expectation ;")
        lines.append(f'  mi:expectationCode "{exp.code}" ;')
        lines.append(f'  mi:fullCode "{exp.full_code}" ;')
        lines.append(f'  mi:officialText "{escape_literal(exp.text)}" ;')
        lines.append(f'  skos:prefLabel "{escape_literal(exp.text)}" ;')
        lines.append(f"  skos:broader {cid} ;")
        lines.append(f"  mi:inCategory {cid} ;")
        lines.append(f"  mi:inGrade {gid} ;")
        if exp.discipline:
            lines.append(f"  mi:inDiscipline mi:Discipline_{exp.discipline} ;")
        if exp.examples:
            lines.append("  mi:hasExample")
            for idx, example_text in enumerate(exp.examples):
                ex_id = example_id(exp.unit, exp.code, idx, "exp")
                example_records.append((ex_id, example_text))
                sep = " ;" if idx == len(exp.examples) - 1 else " ,"
                lines.append(f"    {ex_id}{sep}")
        lines.append(f"  mi:isExpectationOf {cid} ;")
        lines.append(f'  dcterms:source "{escape_literal(source_label)}" .')
        lines.append("")

    if example_records:
        lines.append("#################################################################")
        lines.append("# Examples")
        lines.append("#################################################################")
        for ex_id, ex_text in example_records:
            lines.append(f"{ex_id} a mi:Example ;")
            lines.append(f'  skos:prefLabel "{escape_literal(ex_text)}" ;')
            lines.append(f'  mi:exampleText "{escape_literal(ex_text)}" .')
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_course_ttl(
    course_code: str,
    course_label: str,
    categories: List[Category],
    expectations: List[Expectation],
    source_label: str,
) -> str:
    lines: List[str] = []
    cid = course_id(course_code)

    lines.append("@prefix mi:      <urn:mi:ss:> .")
    lines.append("@prefix dcterms: <http://purl.org/dc/terms/> .")
    lines.append("@prefix owl:     <http://www.w3.org/2002/07/owl#> .")
    lines.append("@prefix rdf:     <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    lines.append("@prefix rdfs:    <http://www.w3.org/2000/01/rdf-schema#> .")
    lines.append("@prefix skos:    <http://www.w3.org/2004/02/skos/core#> .")
    lines.append("@prefix xsd:     <http://www.w3.org/2001/XMLSchema#> .")
    lines.append("")
    lines.append("@base <urn:mi:ss:> .")
    lines.append("")

    lines.append(f"<urn:mi:ss:course:{course_code}> a owl:Ontology ;")
    lines.append(f'  rdfs:label "Michigan Social Studies GLCE - {escape_literal(course_label)}" ;')
    lines.append("  owl:imports <urn:mi:ss:ontology> ;")
    lines.append(f'  dcterms:source "{escape_literal(source_label)}" .')
    lines.append("")

    sorted_categories = sorted(categories, key=lambda c: c.code)
    cat_refs = [category_id(course_code, cat.code) for cat in sorted_categories]
    example_records: List[Tuple[str, str]] = []

    lines.append(f"{cid} a mi:Course ;")
    lines.append(f'  skos:prefLabel "{escape_literal(course_label)}" ;')
    if cat_refs:
        lines.append("  mi:hasCategory")
        for idx, ref in enumerate(cat_refs):
            sep = " ;" if idx == len(cat_refs) - 1 else " ,"
            lines.append(f"    {ref}{sep}")
    lines.append("  mi:isCourseOf mi:MichiganGLCEFramework ;")
    lines.append(f'  mi:courseCode "{course_code}" .')
    lines.append("")

    exp_by_category: Dict[str, List[Expectation]] = defaultdict(list)
    for exp in expectations:
        exp_by_category[exp.category_code].append(exp)

    lines.append("#################################################################")
    lines.append("# Categories")
    lines.append("#################################################################")
    for cat in sorted_categories:
        cid_cat = category_id(cat.unit, cat.code)
        lines.append(f"{cid_cat} a mi:StandardCategory ;")
        lines.append(f'  mi:categoryCode "{cat.code}" ;')
        lines.append(f'  skos:prefLabel "{escape_literal(cat.label or cat.code)}" ;')
        if cat.description.strip():
            lines.append(f'  mi:categoryDescription "{escape_literal(cat.description)}" ;')
        lines.append(f"  mi:inCourse {cid} ;")
        if cat.discipline:
            lines.append(f"  mi:inDiscipline mi:Discipline_{cat.discipline} ;")
        if cat.examples:
            lines.append("  mi:hasExample")
            for idx, example_text in enumerate(cat.examples):
                ex_id = example_id(cat.unit, cat.code, idx, "cat")
                example_records.append((ex_id, example_text))
                sep = " ;" if idx == len(cat.examples) - 1 else " ,"
                lines.append(f"    {ex_id}{sep}")
        linked = sorted(exp_by_category.get(cat.code, []), key=lambda e: e.code)
        if linked:
            lines.append("  mi:hasExpectation")
            for idx, exp in enumerate(linked):
                ref = expectation_id(exp.unit, exp.code)
                sep = " ;" if idx == len(linked) - 1 else " ,"
                lines.append(f"    {ref}{sep}")
        lines.append(f"  mi:isCategoryOf {cid} .")
        lines.append("")

    lines.append("#################################################################")
    lines.append("# Expectations")
    lines.append("#################################################################")
    for exp in sorted(expectations, key=lambda e: e.code):
        eid = expectation_id(exp.unit, exp.code)
        cid_cat = category_id(exp.unit, exp.category_code)
        lines.append(f"{eid} a mi:Expectation ;")
        lines.append(f'  mi:expectationCode "{exp.code}" ;')
        lines.append(f'  mi:fullCode "{exp.full_code}" ;')
        lines.append(f'  mi:officialText "{escape_literal(exp.text)}" ;')
        lines.append(f'  skos:prefLabel "{escape_literal(exp.text)}" ;')
        lines.append(f"  skos:broader {cid_cat} ;")
        lines.append(f"  mi:inCategory {cid_cat} ;")
        lines.append(f"  mi:inCourse {cid} ;")
        if exp.discipline:
            lines.append(f"  mi:inDiscipline mi:Discipline_{exp.discipline} ;")
        if exp.examples:
            lines.append("  mi:hasExample")
            for idx, example_text in enumerate(exp.examples):
                ex_id = example_id(exp.unit, exp.code, idx, "exp")
                example_records.append((ex_id, example_text))
                sep = " ;" if idx == len(exp.examples) - 1 else " ,"
                lines.append(f"    {ex_id}{sep}")
        lines.append(f"  mi:isExpectationOf {cid_cat} ;")
        lines.append(f'  dcterms:source "{escape_literal(source_label)}" .')
        lines.append("")

    if example_records:
        lines.append("#################################################################")
        lines.append("# Examples")
        lines.append("#################################################################")
        for ex_id, ex_text in example_records:
            lines.append(f"{ex_id} a mi:Example ;")
            lines.append(f'  skos:prefLabel "{escape_literal(ex_text)}" ;')
            lines.append(f'  mi:exampleText "{escape_literal(ex_text)}" .')
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Michigan GLCE ontology slices in Turtle.")
    parser.add_argument("--k8-pdf", type=Path, default=DEFAULT_K8_PDF, help="Path to the K-8 standards PDF")
    parser.add_argument("--hs-pdf", type=Path, default=DEFAULT_HS_PDF, help="Path to the 9-12 standards PDF")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Location for the root TTL file")
    parser.add_argument(
        "--source-label",
        default="Michigan K-12 Social Studies Standards (Michigan Department of Education)",
        help="Literal value for dcterms:source annotations",
    )
    args = parser.parse_args(argv)

    all_categories: List[Category] = []
    all_expectations: List[Expectation] = []
    grade_map: Dict[str, str] = {}
    course_map: Dict[str, str] = {}

    if args.k8_pdf and args.k8_pdf.exists():
        k8_text = read_pdf_layout(args.k8_pdf)
        k8_grade_map, k8_categories, k8_expectations = parse_k8(k8_text)
        grade_map.update(k8_grade_map)
        all_categories.extend(k8_categories)
        all_expectations.extend(k8_expectations)
    else:
        print(f"Warning: K-8 PDF not found at {args.k8_pdf}, skipping.", file=sys.stderr)

    if args.hs_pdf and args.hs_pdf.exists():
        hs_text = read_pdf_layout(args.hs_pdf)
        hs_course_map, hs_categories, hs_expectations = parse_high_school(hs_text)
        course_map.update(hs_course_map)
        all_categories.extend(hs_categories)
        all_expectations.extend(hs_expectations)
    else:
        print(f"Warning: 9-12 PDF not found at {args.hs_pdf}, skipping.", file=sys.stderr)

    if not all_expectations:
        raise RuntimeError("No expectations parsed from the input PDFs; aborting.")

    categories_by_unit: Dict[str, List[Category]] = defaultdict(list)
    for cat in all_categories:
        categories_by_unit[cat.unit].append(cat)

    expectations_by_unit: Dict[str, List[Expectation]] = defaultdict(list)
    for exp in all_expectations:
        expectations_by_unit[exp.unit].append(exp)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    root_ttl = render_root_ttl(grade_map, course_map, args.source_label)
    args.output.write_text(root_ttl, encoding="utf-8")

    grades_dir = args.output.parent / GRADES_DIR_NAME
    courses_dir = args.output.parent / COURSES_DIR_NAME
    written_grade_modules: List[Path] = []
    written_course_modules: List[Path] = []

    if grade_map:
        grades_dir.mkdir(parents=True, exist_ok=True)
        for grade_code in sorted(grade_map, key=lambda g: GRADE_ORDER.index(g)):
            module_path = grades_dir / f"mi-grade-{grade_code}.ttl"
            module_ttl = render_grade_ttl(
                grade_code,
                grade_map[grade_code],
                categories_by_unit.get(grade_code, []),
                expectations_by_unit.get(grade_code, []),
                args.source_label,
            )
            module_path.write_text(module_ttl, encoding="utf-8")
            written_grade_modules.append(module_path)

    if course_map:
        courses_dir.mkdir(parents=True, exist_ok=True)
        for course_code in COURSE_ORDER:
            if course_code not in course_map:
                continue
            module_path = courses_dir / f"mi-course-{course_code.lower()}.ttl"
            module_ttl = render_course_ttl(
                course_code,
                course_map[course_code],
                categories_by_unit.get(course_code, []),
                expectations_by_unit.get(course_code, []),
                args.source_label,
            )
            module_path.write_text(module_ttl, encoding="utf-8")
            written_course_modules.append(module_path)

    total_expectations = len(all_expectations)
    total_categories = len(all_categories)
    print(
        f"Wrote {args.output} "
        f"({len(written_grade_modules)} grade modules, {len(written_course_modules)} course modules, "
        f"{total_expectations} expectations, {total_categories} categories)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
